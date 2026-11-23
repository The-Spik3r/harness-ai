"""The gateway's visible catalogue: what `tools/list` returns (PRD-023 Section 6.5, F5, D6, D7, D12).

`visible_catalogue(identity)` starts from `mcp_config.visible_tools(identity)`
(the union of the held skills' tools), fetches each server's cached upstream
list through `mcp_upstream.list_tools` (the only upstream call here; no second
cache), keeps the tools that are both held and listed, injection-inspects them
and returns the northbound tool dicts plus the `callable` map. STORY-013's call
path reuses `callable`: a withheld or unlisted tool is not callable (-32602).

Inspection (D12, T3, O6). D12 names one list, `injection`. It runs over the
tool's `description`, its `title`, and every string value under a `description`
key anywhere inside `inputSchema` (a nested property, `items`, `oneOf`, ...).
Property names, `default` and `enum` values are not inspected. A tool is
withheld, with a WARNING naming the server, the tool and the matched list
names (never the text, a pattern or a phrase), on a `block` hit, on a `flag`
hit, or when any text is longer than `PATTERN_MAX_SCAN_CHARACTERS` (the text
past the ceiling would go unscanned, so it fails closed). If a deployment's
pattern file defines no `injection` list, the built-in one is used.

Nothing is written to the database (O4): `tools/list` is not an action. The
gateway never raises for an unreachable server; that server contributes no
tool and one WARNING with the exception class name only (T16).

This module imports no `mcp` package (T17); only `app/services/mcp_upstream.py`
does.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping

from app.config import settings
from app.services import mcp_config, mcp_upstream, pattern_config, pattern_detector
from app.services.identity import Identity

logger = logging.getLogger(__name__)

#: Module attribute so tests drive the once-per-period INFO expiry with an injected clock.
_now = time.monotonic

#: (kind, server, tool) -> expiry, for the INFO lines logged once per cache period.
_unlisted_logged: dict[tuple, float] = {}

_MAX_SCHEMA_DEPTH = 64
_INSPECTED_ROLE = "tool"


@dataclass(frozen=True)
class Catalogue:
    """What one identity may see and call (PRD-023 Section 6.5).

    `tools` is sorted by prefixed name. `callable` is server id -> the bare
    tool names actually emitted (held, listed and not withheld); a server with
    none is absent.
    """

    tools: tuple[dict, ...] = ()
    callable: Mapping[str, frozenset[str]] = field(default_factory=lambda: MappingProxyType({}))


def _log_once(key: tuple, message: str, *args: Any) -> None:
    """INFO once per `MCP_TOOLS_CACHE_SECONDS` for `key`; `0` logs every time."""
    ttl = settings.MCP_TOOLS_CACHE_SECONDS
    now = _now()
    for stale in [k for k, expiry in _unlisted_logged.items() if expiry <= now]:
        del _unlisted_logged[stale]
    if ttl > 0:
        if key in _unlisted_logged:
            return
        _unlisted_logged[key] = now + ttl
    logger.info(message, *args)


def _schema_descriptions(schema: Any, depth: int = 0) -> list[str]:
    """Every string value of a `description` key anywhere inside `schema`."""
    found: list[str] = []
    if depth > _MAX_SCHEMA_DEPTH:
        return found
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "description" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_schema_descriptions(value, depth + 1))
    elif isinstance(schema, list):
        for item in schema:
            found.extend(_schema_descriptions(item, depth + 1))
    return found


def _injection_profile() -> pattern_config.Profile:
    lists = pattern_config.get_policy().lists
    injection = lists.get("injection") or pattern_config.BUILT_IN_POLICY.lists["injection"]
    return pattern_config.Profile(
        name="mcp-catalogue", lists=(injection,), roles={_INSPECTED_ROLE: "block"}
    )


def _withheld_by(tool: mcp_upstream.UpstreamTool) -> tuple[str, ...]:
    """The list names that withhold `tool`; empty means it is clean."""
    texts = [tool.description]
    if tool.title:
        texts.append(tool.title)
    texts.extend(_schema_descriptions(tool.input_schema))
    turns = [SimpleNamespace(role=_INSPECTED_ROLE, content=t) for t in texts if t]
    result = pattern_detector.inspect(
        turns, _injection_profile(), max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS
    )
    names: list[str] = []
    if result.block is not None:
        names.append(result.block.list_name)
    names.extend(h.list_name for h in result.flags)
    if result.truncated and not names:
        names.append("scan_ceiling")
    return tuple(dict.fromkeys(names))


def _northbound(server: str, tool: mcp_upstream.UpstreamTool) -> dict:
    """One tool as `tools/list` shows it. `inputSchema` is verbatim (`x-mcp-header`
    survives). `icons` and `_meta` are dropped (STORY-002 safe default)."""
    entry: dict = {
        "name": f"{server}__{tool.name}",
        "description": tool.description,
        "inputSchema": tool.input_schema,
    }
    if tool.title is not None:
        entry["title"] = tool.title
    if tool.output_schema is not None:
        entry["outputSchema"] = tool.output_schema
    if tool.annotations is not None:
        entry["annotations"] = tool.annotations
    return entry


async def visible_catalogue(identity: Identity) -> Catalogue:
    """The tools `identity` may see and call, prefixed and inspected (D6, D7, D12)."""
    visible = mcp_config.visible_tools(identity)
    if not visible:
        return Catalogue()
    server_ids = sorted(visible)
    listed = await asyncio.gather(
        *(mcp_upstream.list_tools(sid, identity.user_id) for sid in server_ids),
        return_exceptions=True,
    )
    entries: list[dict] = []
    callable_by_server: dict[str, frozenset[str]] = {}
    for sid, upstream in zip(server_ids, listed):
        if isinstance(upstream, BaseException) and not isinstance(upstream, Exception):
            raise upstream  # CancelledError and friends are never swallowed
        if isinstance(upstream, Exception):
            # The class name only: an exception's text may carry a URL or a header (T16).
            logger.warning(
                "mcp tools/list: server=%s failed (%s)", sid, type(upstream).__name__
            )
            continue
        by_name = {t.name: t for t in upstream}
        emitted: set[str] = set()
        for bare in sorted(visible[sid]):
            tool = by_name.get(bare)
            if tool is None:
                _log_once(
                    ("unlisted", sid, bare),
                    "mcp tools/list: server=%s tool=%s is in a held skill but not listed upstream",
                    sid, bare,
                )
                continue
            matched = _withheld_by(tool)
            if matched:
                logger.warning(
                    "mcp tools/list: withheld server=%s tool=%s lists=%s",
                    sid, bare, ",".join(matched),
                )
                continue
            if tool.input_schema.get("type") != "object":
                _log_once(
                    ("schema", sid, bare),
                    "mcp tools/list: server=%s tool=%s inputSchema is not type=object; passed through",
                    sid, bare,
                )
            entries.append(_northbound(sid, tool))
            emitted.add(bare)
        if emitted:
            callable_by_server[sid] = frozenset(emitted)
    entries.sort(key=lambda e: e["name"])
    return Catalogue(tools=tuple(entries), callable=MappingProxyType(callable_by_server))
