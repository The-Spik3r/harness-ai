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
from chat_ui.components.chat import chat_input, message_list
from chat_ui.components.shell import empty_state, header, user_id_gate
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


app = rx.App(
    api_transformer=fastapi_app,
    stylesheets=[theme.FONTS_HREF],
    style={"background_color": theme.PAPER, "font_family": theme.FONT_BODY},
)
app.add_page(index)

# Same api_transformer lifespan bypass as init_db() above: app.main's lifespan —
# and so STORY-002's pii_redactor.load() — never fires under Reflex. Registered as
# a lifespan task (not called at import) so `reflex export --frontend-only` in the
# Dockerfile's builder stage still never touches the spaCy model. load() is
# zero-arg, sync and PII_REDACTION_ENABLED-aware, so Reflex runs it as-is.
app.register_lifespan_task(pii_redactor.load)
