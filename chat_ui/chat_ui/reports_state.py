"""State for the Reports section: read-only, public, and unrelated to the chat.

**No authentication, deliberately.** The section renders the delivery record of
an open-source repository -- PRDs, stories and implementation reports that are
already public in the repo -- so it takes no token and reads nothing from
`ChatState` or `AdminState`. This module imports neither, and nothing here
reaches the database.

**Every read goes through `app.services.reports`.** The state never lists a
directory or opens a file; it asks the service and turns dataclasses into the
finished view models `components/reports.py` renders. That keeps the "where do
reports come from" question in exactly one module.

**The URL is the filter.** `?status=` and `?q=` are read on load, so a filtered
feed is a link someone can share. Changing a filter re-filters in place and
rewrites the address with `history.replaceState` rather than navigating: the
search field keeps its focus and its caret, and Back leaves the section instead
of undoing keystrokes one at a time.

**States are decided here, once, as a key.** `feed_state` and `detail_state`
name exactly one arm for the component to render. The fault is decided first,
for the reason `session_rail.py` gives about its own three states: a read that
failed also leaves the list empty, and rendering "nothing yet" for it would tell
a reader of a project with eight shipped PRDs that nothing has shipped.
"""

import json
import logging
from datetime import date
from urllib.parse import urlencode

import reflex as rx

from app.services import reports

# Relative, as `state.py` imports its neighbours: the module is then importable
# both as Reflex loads it (`chat_ui.reports_state`) and from the repo root, which
# is how `tests/test_reports_pages.py` drives its handlers in-process.
from . import reports_copy
from .reports_models import (
    CriterionView,
    FileRow,
    PrdNavItem,
    StoryCardView,
    StoryDetailView,
    ValidationItem,
)

logger = logging.getLogger(__name__)

ROUTE_REPORTS = "/reports"

FEED_LOADING = "loading"
FEED_FAULT = "fault"
FEED_PRD_MISSING = "prd_missing"
FEED_EMPTY = "empty"
FEED_EMPTY_PRD = "empty_prd"
FEED_NO_MATCH = "no_match"
FEED_CARDS = "cards"

DETAIL_LOADING = "loading"
DETAIL_FAULT = "fault"
DETAIL_MISSING = "missing"
DETAIL_FOUND = "found"

STATUS_ALL = "all"


def prd_href(prd_slug: str) -> str:
    return f"{ROUTE_REPORTS}/{prd_slug}"


def story_href(prd_slug: str, story_slug: str) -> str:
    return f"{ROUTE_REPORTS}/{prd_slug}/{story_slug}"


def date_label(iso: str) -> str:
    """ "2026-09-07" -> "7 sep 2026"; anything unparseable is shown as written."""
    try:
        day = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or reports_copy.NO_DATE
    return f"{day.day} {reports_copy.MONTHS[day.month - 1]} {day.year}"


def status_label(status: str) -> str:
    return reports_copy.STATUS_LABELS.get(status, status)


def _card_view(card: reports.StoryCard) -> StoryCardView:
    return StoryCardView(
        key=f"{card.prd_slug}/{card.slug}",
        heading=f"{card.story_id}{reports_copy.TITLE_SEPARATOR}{card.title}",
        prd_id=card.prd_id,
        status=card.status,
        status_label=status_label(card.status),
        date_label=date_label(card.date),
        commit=card.commit,
        summary=card.summary or reports_copy.CARD_NO_SUMMARY,
        href=story_href(card.prd_slug, card.slug),
    )


def _nav_item(prd: reports.PrdSummary, query_suffix: str) -> PrdNavItem:
    if prd.total == 0:
        progress = "none"
    elif prd.done == prd.total:
        progress = "complete"
    else:
        progress = "partial"
    return PrdNavItem(
        slug=prd.slug,
        name=prd.name,
        href=prd_href(prd.slug) + query_suffix,
        done_label=(
            reports_copy.NAV_DONE_TEMPLATE.format(done=prd.done, total=prd.total)
            if prd.total
            else reports_copy.NAV_NO_STORIES
        ),
        bar_width=f"{prd.pct}%",
        progress=progress,
    )


def _detail_view(detail: reports.StoryDetail) -> StoryDetailView:
    card = detail.card
    passed = sum(1 for row in detail.validation if row.passed)
    return StoryDetailView(
        heading=f"{card.story_id}{reports_copy.TITLE_SEPARATOR}{card.title}",
        story_id=card.story_id,
        prd_id=card.prd_id,
        prd_name=card.prd_name,
        prd_href=prd_href(card.prd_slug),
        view_prd_label=reports_copy.VIEW_PRD_TEMPLATE.format(prd=card.prd_id),
        status=card.status,
        status_label=status_label(card.status),
        date_label=date_label(card.date),
        commit=" ".join(card.commits),
        commit_url=reports.commit_url(card.commit),
        commit_link_label=reports_copy.COMMIT_LINK_LABEL.format(sha=card.commit),
        plan=detail.plan,
        has_report=detail.has_report,
        no_report_body=reports_copy.NO_REPORT_TEMPLATE.format(status=status_label(card.status)),
        summary=list(detail.summary),
        acceptance=[CriterionView(text=c.text, checked=c.checked) for c in detail.acceptance],
        files=[FileRow(path=f.path, action=f.action, detail=f.detail) for f in detail.files],
        files_label=(
            reports_copy.FILES_SINGLE
            if len(detail.files) == 1
            else reports_copy.FILES_TEMPLATE.format(count=len(detail.files))
        ),
        validation=[
            ValidationItem(
                check=v.check,
                result=v.result,
                outcome="pass" if v.passed else "fail" if v.passed is False else "unknown",
            )
            for v in detail.validation
        ],
        validation_label=(
            reports_copy.VALIDATION_TEMPLATE.format(passed=passed, total=len(detail.validation))
            if detail.validation
            else reports_copy.VALIDATION_EMPTY
        ),
        prev_href=story_href(card.prd_slug, detail.prev.slug) if detail.prev else "",
        prev_label=(
            reports_copy.PREV_TEMPLATE.format(
                label=f"{detail.prev.story_id}{reports_copy.TITLE_SEPARATOR}{detail.prev.title}"
            )
            if detail.prev
            else ""
        ),
        next_href=story_href(card.prd_slug, detail.next.slug) if detail.next else "",
        next_label=(
            reports_copy.NEXT_TEMPLATE.format(
                label=f"{detail.next.story_id}{reports_copy.TITLE_SEPARATOR}{detail.next.title}"
            )
            if detail.next
            else ""
        ),
    )


class ReportsState(rx.State):
    prds: list[PrdNavItem] = []
    cards: list[StoryCardView] = []
    detail: StoryDetailView = StoryDetailView()

    feed_state: str = FEED_LOADING
    detail_state: str = DETAIL_LOADING

    # "prd-008" on a PRD's feed or a story's detail, "" on the whole feed.
    active_prd: str = ""
    active_prd_name: str = ""
    status_filter: str = STATUS_ALL
    query: str = ""

    # The navigation column below the collapse width, as `ChatState.rail_expanded`
    # is for the session rail.
    nav_expanded: bool = False

    # "Todos los reports", carrying the current filters like every PRD link.
    all_href: str = ROUTE_REPORTS

    @rx.var
    def empty_prd_body(self) -> str:
        return reports_copy.EMPTY_PRD_TEMPLATE.format(prd=self.active_prd_name or self.active_prd)

    # --- Loading ----------------------------------------------------------

    def _route(self) -> tuple[list[str], dict[str, str]]:
        """(segments after `/reports`, query parameters) of the current URL.

        Read from `router.url` -- `router.page.params` is deprecated -- and by
        position rather than by name: `/reports/{prd}/{story}` has exactly one
        shape, and a configured frontend prefix before `reports` is skipped.
        """
        url = self.router.url if self.router else None
        if not url:
            return [], {}
        segments = [s for s in url.path.split("/") if s]
        anchor = ROUTE_REPORTS.strip("/")
        after = segments[segments.index(anchor) + 1 :] if anchor in segments else []
        return after, dict(url.query_parameters)

    def _query_suffix(self) -> str:
        pairs = {}
        if self.status_filter != STATUS_ALL:
            pairs["status"] = self.status_filter
        if self.query.strip():
            pairs["q"] = self.query.strip()
        return f"?{urlencode(pairs)}" if pairs else ""

    def _load_nav(self) -> list[reports.PrdSummary]:
        prds = reports.list_prds()
        suffix = self._query_suffix()
        self.prds = [_nav_item(prd, suffix) for prd in prds]
        self.all_href = ROUTE_REPORTS + suffix
        return prds

    def _refilter(self) -> None:
        """Recompute the cards and the state key from the current filters."""
        prd = self.active_prd or None
        try:
            prds = self._load_nav()
            scope = reports.list_stories(prd_id=prd)
            status = None if self.status_filter == STATUS_ALL else self.status_filter
            matches = reports.list_stories(prd_id=prd, status=status, q=self.query)
        except Exception:  # noqa: BLE001 -- any read failure is the fault arm
            logger.exception("reports: feed read failed")
            self.cards = []
            self.feed_state = FEED_FAULT
            return

        known = {p.slug: p for p in prds}
        if prd and prd not in known:
            self.active_prd_name = ""
            self.feed_state = FEED_PRD_MISSING
        elif not scope:
            self.active_prd_name = known[prd].name if prd else ""
            self.feed_state = FEED_EMPTY_PRD if prd else FEED_EMPTY
        else:
            self.active_prd_name = known[prd].name if prd else ""
            self.feed_state = FEED_CARDS if matches else FEED_NO_MATCH
        self.cards = [_card_view(card) for card in matches]

    def _replace_url(self):
        path = (prd_href(self.active_prd) if self.active_prd else ROUTE_REPORTS) + self._query_suffix()
        return rx.call_script(f"window.history.replaceState(null, '', {json.dumps(path)})")

    @rx.event
    def load_feed(self):
        """`/reports`, `/reports/{prd_id}`, with `?status=` and `?q=` applied."""
        segments, params = self._route()
        self.active_prd = segments[0].lower() if segments else ""
        self.status_filter = reports.normalize_status(params.get("status")) or STATUS_ALL
        self.query = params.get("q", "")
        self.nav_expanded = False
        self._refilter()

    @rx.event
    def load_detail(self):
        """`/reports/{prd_id}/{story_id}`."""
        segments = self._route()[0] + ["", ""]
        self.active_prd = segments[0].lower()
        self.status_filter = STATUS_ALL
        self.query = ""
        self.nav_expanded = False
        try:
            self._load_nav()
            found = reports.get_story_detail(self.active_prd, segments[1])
        except Exception:  # noqa: BLE001 -- any read failure is the fault arm
            logger.exception("reports: detail read failed")
            self.detail = StoryDetailView()
            self.detail_state = DETAIL_FAULT
            return
        if found is None:
            self.detail = StoryDetailView()
            self.detail_state = DETAIL_MISSING
        else:
            self.detail = _detail_view(found)
            self.detail_state = DETAIL_FOUND

    # --- Filters ----------------------------------------------------------

    @rx.event
    def set_query(self, value: str):
        self.query = value
        self._refilter()
        return self._replace_url()

    @rx.event
    def set_status_filter(self, value: str):
        self.status_filter = reports.normalize_status(value) or STATUS_ALL
        self._refilter()
        return self._replace_url()

    @rx.event
    def clear_filters(self):
        self.query = ""
        self.status_filter = STATUS_ALL
        self._refilter()
        return self._replace_url()

    @rx.event
    def toggle_nav(self):
        self.nav_expanded = not self.nav_expanded
