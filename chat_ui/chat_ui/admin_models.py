"""Typed row and figure models for the admin console.

`AuditRow` is a deliberate **projection** of `app/db/models.py:AuditLog`, not a
copy of it. The console reads the audit table in-process, which brings the two
raw preview columns into the process — one binding away from the screen. PRD-006
Risk 2 fixes the boundary here, verbatim: "the row model (`AuditRow`) is a
deliberate projection that has no field for either preview". So there is no
`prompt_preview` field and no `response_preview` field, and adding either one
"for completeness" would remove the mitigation rather than improve the model.
`tests/test_admin_models.py` fails if they come back.

Every displayed value is a plain, already-formatted field. Like `formatting.py`
does for the chat, `admin_formatting.py` computes these once when the row is
built: component functions receive Reflex Vars (JS references), not concrete
values, so Python control flow and datetime math cannot run at render time.
Components read fields; they do not compute. Since PRD-013 `tokens_used` is
the register's tokens cell rather than the raw total: "input / output" when the
row recorded a split, the total otherwise. `UsageRow` (PRD-013 STORY-016) is
the Usage table's row, and follows the same rule.

`pydantic.BaseModel`, not `rx.Base`: `rx.Base` does not exist in the pinned
`reflex==0.9.6.post1` (it was the pydantic-v1 shim, and Reflex 0.9.x is
pydantic-v2 based). `models.py:ChatMessage` subclasses `pydantic.BaseModel` for
the same reason and renders fine under `rx.foreach`.
"""

import pydantic


class AuditRow(pydantic.BaseModel):
    """One register row: every field the audit table and its disclosure render."""

    audit_id: int = 0
    timestamp_absolute: str = ""
    # Pre-formatted in admin_formatting.py, never at render: the relative time
    # needs datetime math, and the three below need a placeholder when their
    # source column is NULL — neither can run against a Var.
    timestamp_relative: str = ""
    user_id: str = ""
    # One of the four verdict constants (cleared / held / denied / fault).
    # Defaults to "" rather than "cleared": an unpopulated row must not claim
    # it passed. The register's rx.match therefore needs a default arm.
    verdict: str = ""
    model_used: str = ""
    # PRD-020 D13: the provider that served the call; "" renders as VALUE_ABSENT.
    provider: str = ""
    tokens_used: str = ""
    pii_indicator: bool = False
    # PRD-021 F7: the row was delivered in real time (`streamed_realtime=1`).
    # Named `live`, not `streamed_realtime`, so no `row.streamed` substring
    # appears beside the disclosure's SSE `streamed` field.
    live: bool = False
    device_short: str = ""
    # Disclosure-only fields below.
    device_full: str = ""
    prompt_hash: str = ""
    error_message: str = ""
    pii_entities: list[str] = []
    # Shown combined as pii_indicator in-row, split on disclosure.
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    suspicious_pattern: str = ""
    # PRD-011 D6: which role the matched message had, and whether the policy
    # blocked or flagged it. Disclosure-only, like the pattern they qualify;
    # the absent mark on every row without a pattern and every pre-PRD-011 row.
    pattern_role: str = ""
    pattern_action: str = ""
    # PRD-012 D9: the profile that ran, as recorded. Disclosure-only, beside
    # the PII lines it qualifies; the absent mark on every pre-PRD-012 row.
    profile: str = ""
    # PRD-013 (STORY-015): disclosure-only, pre-formatted; the absent mark on
    # every pre-PRD-013 row. The two flags are words too ("yes" / "no"), so
    # no component branches on a boolean to say them.
    ingress: str = ""
    message_count: str = ""
    conversation_key: str = ""
    streamed: str = ""
    has_tool_calls: str = ""
    limit_exceeded: str = ""
    # PRD-022 STORY-016 (F8): the attempt number is a Register column ("2" is a
    # fallback answer); the request id is disclosure-only and searchable, shared
    # by every attempt row of one request. The absent mark on rows before it.
    attempt: str = ""
    request_id: str = ""


class SummaryFigure(pydantic.BaseModel):
    """One figure on the summary tally sheet: what it counts, and over what window."""

    label: str = ""
    value: str = ""
    # Scope is required copy on every figure, not a nicety: the summary's
    # all-time totals sit beside the register's last-100 window (PRD-006 Risk 4).
    scope: str = ""
    # Share of total_queries for the blocked counts, from format_share() — which
    # returns a placeholder rather than raising when the total is 0.
    share: str = ""
    # Pre-formatted rank lines for the three ranked figures (top_models,
    # top_users, top_pii_entities), so those render as figures rather than as
    # ad-hoc tuples. Empty for scalar figures.
    items: list[str] = []


class UsageRow(pydantic.BaseModel):
    """One row of the Usage table: one user's use today against their budget.

    A projection of `app/db/models.py:UsageDay` plus the budget
    `usage_limits.limits_for` resolved for that user (PRD-013 STORY-016). Every
    value is a pre-formatted string, the `AuditRow` rule: the component reads
    fields and computes nothing. `used` is the absent mark, never a share, when
    the budget is unlimited.
    """

    user_id: str = ""
    role: str = ""
    requests: str = ""
    input_tokens: str = ""
    output_tokens: str = ""
    budget: str = ""
    used: str = ""
    denied: str = ""


class ActionRow(pydantic.BaseModel):
    """One row of the Actions view: one tool call and what the policy decided.

    A projection of `app/db/models.py:ActionDecisionRow` (PRD-016 F11), the
    `AuditRow` rule: every value is a pre-formatted string and the component
    reads fields and computes nothing. Like `AuditRow` it has **no** field for
    `arguments_preview`, `arguments_hash`, `session_id` or `classifications`:
    they are storage aids (`ActionDecisionEntry` omits them for the same
    reason), and a field here is one binding from the screen.
    `tests/test_actions_view.py` fails if one comes back.
    """

    timestamp_relative: str = ""
    timestamp_absolute: str = ""
    user_id: str = ""
    role: str = ""
    tool_name: str = ""
    operation_kind: str = ""
    # As stored: already redacted at write by `action_audit.record`.
    target: str = ""
    rule: str = ""
    reason: str = ""
    # One of the `admin_formatting.DECISIONS` keys. Defaults to "" rather than
    # "allow": an unpopulated row must not claim it passed, so the component's
    # `rx.match` needs a default arm (the `AuditRow.verdict` rule).
    decision: str = ""
    # The permission that lifted the rule (`granted_by`), or the absent mark.
    allowed_by: str = ""
    # PRD-023 STORY-018 (D21): the gateway columns, shown only with MCP on. Every
    # one a string defaulting to "" (the field rule above). `row_id` is the DOM
    # anchor's id; `linked_id` is the `/v1` decision id the gateway call claimed
    # ("" when none), `linked` the cell's text: `#<id>`, "unlinked" or the absent
    # mark.
    row_id: str = ""
    mcp_server: str = ""
    skills: str = ""
    outcome: str = ""
    linked: str = ""
    linked_id: str = ""


class StorageFact(pydantic.BaseModel):
    """One label and value of the Storage view (PRD-018 STORY-012).

    The `AuditRow` rule: both are pre-formatted strings; the component reads
    fields and computes nothing.
    """

    label: str = ""
    value: str = ""


class StorageCounterRow(pydantic.BaseModel):
    """One `<operation>:<class>` count of the Storage view's retry tables."""

    operation: str = ""
    failure_class: str = ""
    count: str = ""


class StorageView(pydantic.BaseModel):
    """Everything the Storage view shows, as strings, from one `StorageStatus`."""

    verdict: str = ""
    caption: str = ""
    notice: str = ""
    breaker: list[StorageFact] = []
    journal: list[StorageFact] = []
    counters: list[StorageFact] = []
    retries: list[StorageCounterRow] = []
    exhausted: list[StorageCounterRow] = []


class ProviderFact(pydantic.BaseModel):
    """One label and value of a provider's block (PRD-022 STORY-016).

    The `StorageFact` rule, kept separate so the views do not share a model.
    """

    label: str = ""
    value: str = ""


class ProviderCard(pydantic.BaseModel):
    """One provider's circuit breaker: its name over its facts."""

    name: str = ""
    facts: list[ProviderFact] = []


class ProviderCounterRow(pydantic.BaseModel):
    """One `<provider>:<kind or reason>` count of the Providers view's tables."""

    provider: str = ""
    reason: str = ""
    count: str = ""


class ProvidersView(pydantic.BaseModel):
    """Everything the Providers view shows, as strings, from one `ProvidersStatus`."""

    verdict: str = ""
    caption: str = ""
    cards: list[ProviderCard] = []
    counters: list[ProviderFact] = []
    failed: list[ProviderCounterRow] = []
    skipped: list[ProviderCounterRow] = []


class SkillRow(pydantic.BaseModel):
    """One configured skill of the Skills view (PRD-023 STORY-018, D21).

    The `ProviderFact` rule: every value is a string, the component reads and
    computes nothing. `tools` and `requires` are comma-joined, `roles` is the
    roles holding `skill:<id>` or the absent mark.
    """

    id: str = ""
    version: str = ""
    description: str = ""
    tools: str = ""
    requires: str = ""
    roles: str = ""


class SkillsView(pydantic.BaseModel):
    """Everything the Skills view shows, from `mcp_config` and `authz`."""

    caption: str = ""
    skills: list[SkillRow] = []
