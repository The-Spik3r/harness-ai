import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import reflex as rx

from app.db.database import init_db
from app.main import app as fastapi_app

from chat_ui.components.chat import chat_input, message_list

# Reflex's api_transformer mounts fastapi_app as a Starlette sub-app under a
# new outer Starlette app whose own lifespan runs instead of fastapi_app's —
# app.main's `lifespan` (and its init_db() call) never fires when mounted this
# way, so we call it eagerly here. CREATE TABLE IF NOT EXISTS makes this safe
# to call on every reload.
init_db()


def index() -> rx.Component:
    return rx.vstack(
        message_list(),
        chat_input(),
        height="100vh",
        width="100%",
        spacing="0",
    )


app = rx.App(api_transformer=fastapi_app)
app.add_page(index)
