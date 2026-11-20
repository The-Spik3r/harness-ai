"""The fallback-chain runner (PRD-022 6.1-6.4, 6.9, F4, F7, D6-D9, D15, T3).

`run()` walks one `chain_config.Chain`: it skips a candidate that may not or
cannot take this request (with a closed-vocabulary reason), asks the caller's
`prepare(route)` what that candidate may receive, calls the caller's
`attempt(route, sent, timeout)`, records the outcome with `health`, and decides
whether the next candidate is tried from `UpstreamError.fallback_eligible` and
the caller's `released()`. It returns a `ChainOutcome` or raises the failing
error or `ChainExhausted`. STORY-012 wires it into the pipeline; nothing calls it
yet.

**Pure.** Stdlib, `chain_config`, `health` and `upstream.types` only: no settings,
no I/O, no authz or registry import. What the request is and what a candidate is
allowed are injected: `resolve(model_id)` returns the request's registry route,
`permitted(model_id)` wraps `authz.authorize_route` (D7), `prepare` redacts per
route (D16), `attempt` makes the call. Sync, like the pipeline that calls it.

**Availability never outranks the data boundary.** Every candidate passes RBAC,
capability and BYOK on every request, and a refusal, a deterministic 4xx,
`shape` and `incompatible` never fall back (D8). After the first release to the
sink (`released()`) nothing is retried (D9).

**Nothing here carries text.** Skips and outcomes hold provider names, reason
words and `kind` words; an error is passed through, never rendered (T10).
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Optional

from app.services.upstream import health
from app.services.upstream.chain_config import Candidate, Chain, ChainLimits, trust_lowered
from app.services.upstream.types import ChainExhausted, UpstreamError


class _RedactionLimit:
    """The sentinel `prepare` returns when the redacted text breaches a `code` size limit."""

    def __repr__(self) -> str:
        return "REDACTION_LIMIT"


REDACTION_LIMIT = _RedactionLimit()

# What a provider name reads as when a candidate's model id is not in the registry
# snapshot (the skip is `forbidden`: fail closed, PRD-022 6.1).
_UNKNOWN_PROVIDER = "unknown"
_UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class RequestNeeds:
    """What this request demands of any candidate (PRD-022 6.1).

    `estimate(route)` is the PRD-020 D9 input-token estimate for that route (it
    depends on the provider's chars-per-token). It is evaluated only when the
    route sets `max_context_tokens`.
    """

    tools: bool = False
    forced_tool_choice: bool = False
    streaming: bool = False
    estimate: Optional[Callable[[Any], int]] = None


@dataclass(frozen=True)
class ChainOutcome:
    """A successful run: the result, who answered, and what the audit row needs (PRD-022 F8)."""

    result: Any
    candidate: Candidate
    route: Any
    attempt: int  # calls made, 1-based; a skip consumes no number (D10)
    fallback_reason: Optional[str]  # `status_503`, `timeout`, ..., `;trust_lowered`; None on a clean first answer
    skipped: Optional[str]  # "provider:reason,provider:reason" or None


def _capability_gap(route: Any, needs: RequestNeeds) -> bool:
    caps = route.capabilities
    if needs.tools and not caps.tools:
        return True
    if needs.forced_tool_choice and not caps.forced_tool_choice:
        return True
    if needs.streaming and not caps.streaming:
        return True
    if caps.max_context_tokens is not None and needs.estimate is not None:
        return needs.estimate(route) > caps.max_context_tokens
    return False


def _base_reason(error: UpstreamError) -> str:
    if error.upstream_status is not None:
        return f"status_{error.upstream_status}"
    return error.kind or _UNCLASSIFIED


def run(
    chain: Chain,
    *,
    primary: Any,
    limits: Optional[ChainLimits],
    needs: RequestNeeds,
    byok: bool,
    policy: Hashable,
    resolve: Callable[[str], Any],
    permitted: Callable[[str], bool],
    prepare: Callable[[Any], Any],
    attempt: Callable[[Any, Any, Optional[float]], Any],
    on_attempt_failed: Callable[..., None],
    released: Callable[[], bool],
    clock: Callable[[], float] = time.monotonic,
) -> ChainOutcome:
    """Try the chain's candidates in order until one answers (PRD-022 6.1-6.4).

    Per candidate, in this order: `forbidden`, `capability`, `byok`, `deadline`,
    `prepare` (`redaction_limit`), `health.admit` (`open` / `half_open_busy`).
    `admit` is last because an admitted half-open trial that is never attempted
    blocks the provider until its lease lapses. `limits=None` means no chain
    deadline and no per-attempt timeout (today's single call).

    `prepare(route)` is cached per `(policy, route.relaxes_input())` (T3): two
    candidates that may receive the same text share one redaction. A
    `PiiRedactorError` from it, or any exception that is not an `UpstreamError`,
    propagates unchanged and is not recorded (fail closed). A half-open trial
    claimed by an attempt that then raises such an exception stays
    `half_open_busy` until the breaker's lease lapses: there is no release API,
    and recording a success would falsely close the breaker.

    An `UpstreamError` from `attempt` is recorded and reported through
    `on_attempt_failed(candidate, error, attempt=n)`; the next candidate runs only
    if `error.fallback_eligible` and `not released()` (read live, after the
    callback), otherwise the error is raised. If every candidate is skipped or
    failed, `ChainExhausted` is raised.
    """
    start = clock()
    deadline: Optional[float] = None
    if limits is not None:
        deadline = (
            limits.deadline_seconds
            if limits.deadline_seconds is not None
            else primary.provider.timeout_seconds
        )

    skips: list[tuple[str, str]] = []
    retry_afters: list[int] = []
    cache: dict[tuple[Hashable, bool], Any] = {}
    attempts = 0
    last_error: Optional[UpstreamError] = None

    def skip(provider: str, reason: str, retry_after: Optional[int] = None) -> None:
        health.count_skipped(provider, reason)
        skips.append((provider, reason))
        if retry_after is not None:
            retry_afters.append(retry_after)

    for index, candidate in enumerate(chain.candidates):
        is_primary = index == 0
        route = primary if is_primary else resolve(candidate.model_id)
        if route is None:
            skip(_UNKNOWN_PROVIDER, "forbidden")
            continue
        name = route.provider.name

        # The primary was ruled by step 2 (RBAC), so only a fallback is asked (D7).
        if not is_primary and not permitted(candidate.model_id):
            skip(name, "forbidden")
            continue
        if _capability_gap(route, needs):
            skip(name, "capability")
            continue
        # D15: the caller's own key never reaches a provider it did not name.
        if byok and not is_primary:
            skip(name, "byok")
            continue

        timeout: Optional[float] = None
        if deadline is not None:
            remaining = deadline - (clock() - start)
            if remaining < limits.min_attempt_seconds:
                skip(name, "deadline")
                continue
            timeout = min(route.provider.timeout_seconds, remaining)

        key = (policy, route.relaxes_input())
        if key not in cache:
            cache[key] = prepare(route)
        sent = cache[key]
        if sent is REDACTION_LIMIT:
            skip(name, "redaction_limit")
            continue

        admission = health.admit(name)
        if not admission.admitted:
            skip(name, admission.reason, admission.retry_after_seconds)
            continue

        attempts += 1
        try:
            result = attempt(route, sent, timeout)
        except UpstreamError as error:
            health.record(name, error)
            on_attempt_failed(candidate, error, attempt=attempts)
            if not error.fallback_eligible or released():
                raise
            last_error = error
            continue

        health.record(name, None)
        if attempts > 1:
            health.count_fallback_answer()
        reason = _base_reason(last_error) if last_error is not None else None
        if trust_lowered(primary.provider, route.provider):
            reason = f"{reason};trust_lowered" if reason else "trust_lowered"
        return ChainOutcome(
            result=result,
            candidate=candidate,
            route=route,
            attempt=attempts,
            fallback_reason=reason,
            skipped=",".join(f"{p}:{r}" for p, r in skips) or None,
        )

    retry_after = max(1, min(retry_afters)) if retry_afters else None
    raise ChainExhausted(skips, last_error=last_error, retry_after_seconds=retry_after)
