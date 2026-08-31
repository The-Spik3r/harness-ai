import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import reflex as rx

from app.db.database import init_db
from app.main import app as fastapi_app
from app.services import pii_redactor

from chat_ui import theme
from chat_ui.components.admin_shell import (
    ROUTE_REGISTER,
    ROUTE_SUMMARY,
    VIEW_REGISTER,
    VIEW_SUMMARY,
    admin_page,
)
from chat_ui.components.chat import chat_input, message_list
from chat_ui.components.register import register
from chat_ui.components.shell import empty_state, header, user_id_gate
from chat_ui.components.summary import summary
from chat_ui.state import ChatState

# Reflex's api_transformer mounts fastapi_app as a Starlette sub-app under a
# new outer Starlette app whose own lifespan runs instead of fastapi_app's —
# app.main's `lifespan` (and its init_db() call) never fires when mounted this
# way, so we call it eagerly here. CREATE TABLE IF NOT EXISTS makes this safe
# to call on every reload.
init_db()


def index() -> rx.Component:
    return rx.fragment(
        rx.el.style(theme.GLOBAL_CSS),
        rx.cond(
            ChatState.user_id != "",
            rx.vstack(
                header(),
                rx.cond(
                    ChatState.has_messages,
                    message_list(),
                    empty_state(),
                ),
                chat_input(),
                height="100vh",
                width="100%",
                spacing="0",
                background_color=theme.PAPER,
            ),
            user_id_gate(),
        ),
    )


# The console's two views. `admin_page()` (STORY-009) supplies the frame around
# both: the token gate, or the masthead over `content`. The register fills that
# `content` slot with the audit table; the summary fills it with the tally sheet
# (STORY-015), which is what the two-view switch in the masthead moves between.
#
# Neither function re-emits `rx.el.style(theme.GLOBAL_CSS)` the way `index()`
# does: `admin_page()` already carries it, and a second copy on the page is what
# its docstring tells these functions not to add.
def admin_register_page() -> rx.Component:
    return admin_page(register(), VIEW_REGISTER)


def admin_summary_page() -> rx.Component:
    return admin_page(summary(), VIEW_SUMMARY)


# Radix resolves its own colour tokens from the theme's appearance, and Reflex
# defaults to following the OS. On a machine set to dark mode every Radix
# control (both inputs, the model selector) painted dark-mode gray-12 — near
# white — on top of this deliberately light design, leaving typed text
# invisible. The design is committed to one palette, so the appearance is
# pinned to match it rather than left to the visitor's OS.
app = rx.App(
    api_transformer=fastapi_app,
    stylesheets=[theme.FONTS_HREF],
    style={"background_color": theme.PAPER, "font_family": theme.FONT_BODY},
    theme=rx.theme(
        appearance="light",
        has_background=False,
        accent_color="gray",
        gray_color="slate",
        radius="small",
        scaling="100%",
    ),
)
app.add_page(index)

# The console, registered as Reflex pages and nothing else — no route reaches the
# FastAPI app, so `POST /query`, `GET /audit`, `GET /stats` and `GET /health` keep
# their exact contracts and `tests/test_route_reservations.py` holds unmodified.
#
# One level down from `/audit` and `/stats`, which are taken three times over: by
# `app/routers/admin.py`, by that reserved-route test, and by the Caddyfile's
# `@backend_routes` matcher. `/admin/*` is deliberately absent from that matcher
# and falls through to the static `file_server` like every other Reflex page, so
# no Caddyfile change is needed (PRD-006 Section 6, routing constraint).
#
# The routes themselves are imported from `admin_shell`, never retyped: the same
# constants drive the masthead's two-view switch, so a moved page cannot leave
# the switch pointing at a path nothing is registered at.
#
# `context={"sitemap": None}` opts each page out of `SitemapPlugin` (rxconfig.py),
# which would otherwise write all three admin routes into the `public/sitemap.xml`
# that Caddy serves publicly. The gate is what protects the data; not advertising
# the console's paths is the posture PRD-006 Section 9 asks for on top of it.
app.add_page(
    admin_register_page,
    route=ROUTE_REGISTER,
    context={"sitemap": None},
)
app.add_page(
    admin_summary_page,
    route=ROUTE_SUMMARY,
    context={"sitemap": None},
)
# /admin is a landing route, not a third view: it renders the same shell (so an
# unauthenticated visitor gets the gate rather than a blank frame while the
# redirect is in flight) and redirects to the register on load. replace=True keeps
# it out of history, so Back does not bounce straight into the redirect again.
# Reflex has no route alias, and registering the register at two paths would leave
# the masthead's aria-current right on one path and quietly wrong on the other.
app.add_page(
    admin_register_page,
    route="/admin",
    on_load=rx.redirect(ROUTE_REGISTER, replace=True),
    context={"sitemap": None},
)

# Same api_transformer lifespan bypass as init_db() above: app.main's lifespan —
# and so STORY-002's pii_redactor.load() — never fires under Reflex. Registered as
# a lifespan task (not called at import) so `reflex export --frontend-only` in the
# Dockerfile's builder stage still never touches the spaCy model. load() is
# zero-arg, sync and PII_REDACTION_ENABLED-aware, so Reflex runs it as-is.
app.register_lifespan_task(pii_redactor.load)
