"""Usage limits: which limits apply, and whether an attempt is admitted (PRD-013 F9).

Sections 6.5-6.7. The pipeline asks one question -- `admit(identity, ...)` --
and gets back either an admission carrying the counted `day` or a refusal
carrying the one limit that was broken. How limits are configured (settings,
per-user overrides) and stored (`usage_daily`) stays behind this module.

What this module does **not** do: read `USAGE_LIMITS_ENABLED`. That switch is
the pipeline's (STORY-011): with it off, neither `admit` nor `charge` is called
and no counter row is touched. Nor does it know about BYOK; the caller says
whether the budget applies through `charges_budget` (Decision D8).

Failure rules, deliberately opposite (PRD Section 9.2):

- `admit` fails **closed** (T7): a storage error becomes `UsageLimitError`,
  which the router maps to 500, and nothing is sent upstream. A counter
  outage must not be a bypass. Same choice as `DuplicateCheckError`.
- `charge` fails **open** (T8): the model has already answered, so a storage
  error is logged at ERROR and swallowed. The audit row's token columns
  remain the record of what was spent.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from app.config import settings
from app.db.database import admit_usage, charge_usage
from app.db.errors import StorageError
from app.services.identity import Identity

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_DAY_FORMAT = "%Y-%m-%d"
_DEFAULT_ROLE = "*"

UsageLimit = Literal["requests", "tokens"]


class UsageLimitError(Exception):
    pass


@dataclass(frozen=True)
class UsageLimits:
    token_budget_daily: Optional[int]  # None = unlimited
    requests_per_minute: Optional[int]  # None = unlimited


@dataclass(frozen=True)
class UsageRefusal:
    """The one limit an attempt broke (PRD Section 6.7).

    Field for field what `QueryBlockedUsageLimitResponse` carries. `actual` is
    the window count for `requests` and tokens used today for `tokens`.
    """

    limit: UsageLimit
    maximum: int
    actual: int
    resets_at: str  # UTC, _TIMESTAMP_FORMAT


@dataclass(frozen=True)
class Admission:
    """The outcome of one `admit` call.

    `refusal` is None exactly when the attempt was admitted, so the refusal
    fields cannot be read off an admitted result by accident. `day` is set
    either way: it is the day `admit_usage` counted the attempt against, and
    the day `charge` must be given (PRD Section 6.5), so a request that
    straddles midnight is charged to the day it was admitted.
    """

    day: str
    refusal: Optional[UsageRefusal] = None

    @property
    def admitted(self) -> bool:
        return self.refusal is None


def _resolve(
    override: Optional[int], role: str, table: dict[str, Optional[int]]
) -> Optional[int]:
    """One limit: the override, else the role's entry, else `*`.

    Membership, not `.get(role) or ...`: a role entry of `unlimited` parses to
    None, and must win over `*` rather than fall through to it.
    """
    if override is not None:
        return override
    if role in table:
        return table[role]
    return table[_DEFAULT_ROLE]


def limits_for(identity: Identity) -> UsageLimits:
    """The limits `identity` is held to, each resolved independently (Section 6.6).

    Both maps are read off `settings` **here, per call**, for the reason
    `_context_limit_exceeded` gives: a value captured at import would ignore a
    reconfiguration and every `monkeypatch.setattr(settings, ...)` in the suite.

    The break-glass identity needs no special case: it has no `users` row, so
    no overrides, and its role is `admin`, so it gets the `admin` entry (or
    `*`) like any admin. It is not exempt.
    """
    return UsageLimits(
        token_budget_daily=_resolve(
            identity.token_budget_daily,
            identity.role,
            settings.usage_daily_token_budget_map,
        ),
        requests_per_minute=_resolve(
            identity.requests_per_minute,
            identity.role,
            settings.usage_requests_per_minute_map,
        ),
    )


def _end_of_minute(window_start: int) -> str:
    """When the rate window `window_start` (a unix minute) closes: the instant
    the next one opens and the user may send again."""
    return datetime.fromtimestamp((window_start + 1) * 60, tz=timezone.utc).strftime(
        _TIMESTAMP_FORMAT
    )


def _next_utc_midnight(day: str) -> str:
    """00:00 UTC after `day`, when that day's budget row stops being today's."""
    start = datetime.strptime(day, _DAY_FORMAT).replace(tzinfo=timezone.utc)
    return (start + timedelta(days=1)).strftime(_TIMESTAMP_FORMAT)


def admit(identity: Identity, charges_budget: bool) -> Admission:
    """Count one authorized attempt and decide whether it may proceed.

    One statement, one round trip: `admit_usage` increments the counters and
    reads back everything both checks need. The attempt is counted even when
    it is then refused (Section 6.5); the window is fixed, so that does not
    extend a lockout.

    Only one limit is reported, the rate first and the budget only if the rate
    passed, the same rule as `_context_limit_exceeded`. The rate is strict `>`
    (the Nth of N is admitted); the budget is `>=` (at the budget you are out).
    The budget is skipped when `charges_budget` is False (BYOK, Decision D8).

    `resets_at` is derived only from the `window_start` and `day` the database
    returned, never from this instance's clock.

    Raises `UsageLimitError` on a storage failure (fail closed, T7).
    """
    limits = limits_for(identity)

    try:
        usage = admit_usage(identity.user_id)
    except StorageError as exc:
        raise UsageLimitError(f"Usage admission failed: {exc}") from exc

    rate = limits.requests_per_minute
    if rate is not None and usage.window_requests > rate:
        return Admission(
            day=usage.day,
            refusal=UsageRefusal(
                limit="requests",
                maximum=rate,
                actual=usage.window_requests,
                resets_at=_end_of_minute(usage.window_start),
            ),
        )

    budget = limits.token_budget_daily
    if charges_budget and budget is not None and usage.tokens_today >= budget:
        return Admission(
            day=usage.day,
            refusal=UsageRefusal(
                limit="tokens",
                maximum=budget,
                actual=usage.tokens_today,
                resets_at=_next_utc_midnight(usage.day),
            ),
        )

    return Admission(day=usage.day)


def charge(
    user_id: str,
    day: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: int,
) -> None:
    """Add one call's reported tokens to the `day` that `admit` returned.

    When the provider reported the split, both halves are charged; otherwise
    `total_tokens` goes to `unsplit_tokens`, so the day's total is still right
    (PRD F11).

    Never raises for storage (fail open, T8): the user already has the answer
    they paid for. A failure, or a charge that matched no row (which a
    successful admit rules out), is logged at ERROR with the user id, the day
    and the counts, and the call returns.
    """
    if input_tokens is not None and output_tokens is not None:
        charged = (input_tokens, output_tokens, 0)
    else:
        charged = (0, 0, total_tokens)

    try:
        matched = charge_usage(user_id, day, *charged)
    except StorageError as exc:
        logger.error(
            "usage charge failed: user_id=%s day=%s input_tokens=%s output_tokens=%s"
            " total_tokens=%s error=%s",
            user_id,
            day,
            input_tokens,
            output_tokens,
            total_tokens,
            exc,
        )
        return

    if not matched:
        logger.error(
            "usage charge matched no row: user_id=%s day=%s input_tokens=%s"
            " output_tokens=%s total_tokens=%s",
            user_id,
            day,
            input_tokens,
            output_tokens,
            total_tokens,
        )
