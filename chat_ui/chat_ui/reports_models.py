"""View models for the Reports section: what a component reads, already finished.

Components only ever see Vars, so every label, href and date string is composed
in `reports_state.py` from the service's dataclasses and arrives here complete.
None of these carry a colour: a status is carried as its key and
`components/reports.py` owns the one status-to-ink mapping.
"""

import pydantic


class PrdNavItem(pydantic.BaseModel):
    slug: str = ""
    name: str = ""
    href: str = ""
    done_label: str = ""
    bar_width: str = "0%"
    # "complete", "partial" or "none" -- the progress bar's tone key.
    progress: str = "none"


class StoryCardView(pydantic.BaseModel):
    key: str = ""
    heading: str = ""  # "STORY-019 · The rail in the shell"
    prd_id: str = ""
    status: str = ""
    status_label: str = ""
    date_label: str = ""
    commit: str = ""
    summary: str = ""
    href: str = ""


class CriterionView(pydantic.BaseModel):
    text: str = ""
    checked: bool = False


class FileRow(pydantic.BaseModel):
    path: str = ""
    action: str = ""
    detail: str = ""


class ValidationItem(pydantic.BaseModel):
    check: str = ""
    result: str = ""
    # "pass", "fail" or "unknown".
    outcome: str = "unknown"


class StoryDetailView(pydantic.BaseModel):
    heading: str = ""
    story_id: str = ""
    prd_id: str = ""
    prd_name: str = ""
    prd_href: str = ""
    view_prd_label: str = ""
    status: str = ""
    status_label: str = ""
    date_label: str = ""
    commit: str = ""
    commit_url: str = ""
    commit_link_label: str = ""
    plan: str = ""
    has_report: bool = False
    no_report_body: str = ""
    summary: list[str] = []
    acceptance: list[CriterionView] = []
    files: list[FileRow] = []
    files_label: str = ""
    validation: list[ValidationItem] = []
    validation_label: str = ""
    prev_href: str = ""
    prev_label: str = ""
    next_href: str = ""
    next_label: str = ""
