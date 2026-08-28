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
Components read fields; they do not compute.

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
    tokens_used: str = ""
    pii_indicator: bool = False
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
