"""STORY-021 (PRD-023) -- the MCP gateway documentation is checked against the code.

A renamed setting, a stale rule count, a link that no longer resolves or a
reworded promise must fail the suite, so nothing here compares against a
hand-copied list where the code can answer. Setting names and defaults are read
from `Settings.model_fields`; the rule counts from `RULE_IDS` and
`NON_GRANTABLE_RULES`; every relative link of the user-facing docs is resolved
against the repository, and so is every `#anchor` against the headings of its
target. Content assertions are substance, not sentences (the rule of
`tests/test_admin_copy.py`): a required substring, never a whole paragraph.
"""

import re
from pathlib import Path

import pytest

from app.config import Settings
from app.services.action_classifiers import RULE_IDS
from app.services.action_config import NON_GRANTABLE_RULES

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / "docs" / "features.md"
ROADMAP = ROOT / "docs" / "roadmap.md"
CONFIGURATION = ROOT / "docs" / "configuration.md"
API = ROOT / "docs" / "api.md"
README = ROOT / "README.md"
ENV_EXAMPLE = ROOT / ".env.example"

_MCP_SETTINGS = (
    "MCP_ENABLED",
    "MCP_CONFIG_FILE",
    "MCP_CALL_TIMEOUT_SECONDS",
    "MCP_MAX_REQUEST_BYTES",
    "MCP_MAX_RESULT_BYTES",
    "MCP_TOOLS_CACHE_SECONDS",
    "MCP_UPSTREAM_SESSION_IDLE_SECONDS",
    "MCP_LINK_WINDOW_SECONDS",
    "MCP_ALLOWED_ORIGINS",
)
_DOCS_CHECKED = (FEATURES, ROADMAP, CONFIGURATION, API, README)
_NUMBER_WORDS = {10: "Ten", 11: "Eleven", 12: "Twelve"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, heading: str, level: str = "###") -> str:
    """Text from `{level} {heading}` to the next heading of that level; the heading must exist."""
    text = _read(path)
    match = re.search(rf"^{level} {re.escape(heading)}\s*$", text, re.MULTILINE)
    assert match, f"{path.name} has no '{level} {heading}' heading"
    rest = text[match.end():]
    nxt = re.search(rf"^{level} ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _row(name: str) -> str:
    rows = [ln for ln in _read(CONFIGURATION).splitlines() if ln.startswith(f"| `{name}` |")]
    assert len(rows) == 1, f"docs/configuration.md needs exactly one row for {name}"
    return rows[0]


# --- settings ---------------------------------------------------------------


def test_mcp_settings_documented():
    """Nine settings, each a real field, a configuration row with the code's default, an `.env.example` line, and named in the README."""
    env_names = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", _read(ENV_EXAMPLE), re.MULTILINE))
    readme_section = _section(README, "MCP gateway and skills", level="##")
    features_section = _section(FEATURES, "MCP gateway and skills")
    for name in _MCP_SETTINGS:
        assert name in Settings.model_fields, f"{name} is documented but is not a setting"
        assert name in env_names, f".env.example has no {name}= line"
        assert name in readme_section, f"the README section does not name {name}"
        assert f"`{name}`" in features_section, f"docs/features.md does not name {name}"
        default = Settings.model_fields[name].default
        cells = [c.strip() for c in _row(name).split("|")]
        # | `NAME` | No | default | purpose |
        documented = cells[3]
        if default in ("", None):
            assert documented.startswith("—"), f"{name}: the documented default {documented!r} is not empty"
        elif isinstance(default, bool):
            assert documented == f"`{str(default).lower()}`", f"{name}: documented {documented!r}, code {default!r}"
        else:
            assert documented == f"`{default}`", f"{name}: documented {documented!r}, code {default!r}"
    # PRD-023 Section 9.3 was amended to the shipped defaults; pin the two that moved.
    assert Settings.model_fields["MCP_TOOLS_CACHE_SECONDS"].default == 60
    assert Settings.model_fields["MCP_LINK_WINDOW_SECONDS"].default == 300


# --- rule counts and the reworded promise -----------------------------------


@pytest.mark.parametrize("path", [FEATURES, ROADMAP], ids=lambda p: p.name)
def test_rule_counts_match_the_engine(path):
    """The documented rule counts are the engine's (PRD-023 D7 added the 26th, non-grantable)."""
    text = _read(path)
    assert f"{len(RULE_IDS)} rules" in text or f"{len(RULE_IDS)} of them" in text
    assert "25 rules" not in text and "25 of them" not in text
    if path == FEATURES:
        assert f"{_NUMBER_WORDS[len(NON_GRANTABLE_RULES)]} of them (`NON_GRANTABLE_RULES`" in text
        assert "Ten of them" not in text
        for rule in RULE_IDS:
            assert re.search(rf"^\| `{re.escape(rule)}` \|", text, re.MULTILINE), f"the rules table lacks {rule}"
        for rule in NON_GRANTABLE_RULES:
            assert f"`{rule}`" in _section(FEATURES, "Action policy rules").split("A rule with no grant")[1]


def test_never_executes_sentence_reworded():
    """The harness no longer claims it never executes tools: for MCP tools it forwards an allowed call (PRD-023 scope note)."""
    pattern = re.compile(r"never executes (a |any )?tools?", re.IGNORECASE)
    for path in (*_DOCS_CHECKED, *sorted((ROOT / "docs").glob("*.md"))):
        assert not pattern.search(_read(path)), f"{path.name} still says the harness never executes tools"


# --- links ------------------------------------------------------------------

_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)


def _slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
    heading = heading.lower()
    heading = re.sub(r"[^\w\- ]", "", heading)
    return heading.replace(" ", "-")


def _anchors(path: Path) -> set:
    text = _FENCE.sub("", _read(path))
    return {_slug(h) for h in _HEADING.findall(text)}


def _broken_links(path: Path, text: str = None) -> list:
    text = _read(path) if text is None else text
    text = _INLINE_CODE.sub("", _FENCE.sub("", text))
    broken = []
    for target in _LINK.findall(text):
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):  # http(s):, mailto:
            continue
        file_part, _, anchor = target.partition("#")
        dest = path if not file_part else (path.parent / file_part).resolve()
        if not dest.exists():
            broken.append(target)
            continue
        if anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
            broken.append(target)
    return broken


@pytest.mark.parametrize("path", _DOCS_CHECKED, ids=lambda p: p.name)
def test_relative_links_resolve(path):
    """Every relative link and `#anchor` of the user-facing docs resolves (STORY-021 AC)."""
    assert _broken_links(path) == []


def test_link_checker_is_not_vacuous():
    """A made-up file and a made-up anchor are both reported, so the check above can fail."""
    text = "[a](docs/no-such-file.md) [b](features.md#no-such-heading-anywhere) [c](features.md#mcp-gateway-and-skills)"
    assert _broken_links(FEATURES, text) == ["docs/no-such-file.md", "features.md#no-such-heading-anywhere"]
    assert _slug("`GET /audit/actions` (requires `audit:read:all` or `audit:read:own`)") == (
        "get-auditactions-requires-auditreadall-or-auditreadown"
    )


# --- substance --------------------------------------------------------------


def test_features_mcp_section_substance():
    section = _section(FEATURES, "MCP gateway and skills")
    for needle in (
        "codemode",
        "streamableHttp",
        "v1_aliases",
        "55",
        "correlation",
        "not proof",
        "unverified",
        "does not cover",
        "tool.not_in_skill",
        "may have run",
        "never stored",
        "MCP_ENABLED",
        *_MCP_SETTINGS,
    ):
        assert needle in section, f"the MCP section of docs/features.md lacks {needle!r}"
