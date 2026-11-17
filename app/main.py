from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import journal_drainer
from app.db.database import init_db
from app.routers import admin as admin_router
from app.routers import query as query_router
from app.routers import v1 as v1_router
from app.services import action_config, authz, pattern_config, pii_policy, pii_redactor, pipeline_executor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    authz.load()
    pattern_config.load()
    pii_policy.load()
    action_config.load()
    authz.check_bootstrap()
    # PRD-018 D11/D17: the journal opens only after init_db() succeeded and every
    # fail-fast check passed, so a refused startup leaks no journal or thread.
    journal_drainer.start(
        settings.AUDIT_BUFFER_DIR, settings.AUDIT_BUFFER_MAX_BYTES, settings.PIPELINE_MAX_WORKERS
    )
    yield
    # The executor first (it waits for in-flight calls, which may still journal
    # their rows), then the journal.
    pipeline_executor.shutdown()
    journal_drainer.stop()


app = FastAPI(title="Harness IA", lifespan=lifespan)

app.include_router(query_router.router)
app.include_router(admin_router.router)

# PRD-015 Section 9.3: off means the routes are not mounted and /v1/* is 404.
# Read once, at import, like every other route decision here. Off also leaves
# out the /v1-scoped error handlers, so the app is exactly as before PRD-015.
if settings.V1_ENABLED:
    app.include_router(v1_router.router)
    v1_router.install_error_handlers(app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
