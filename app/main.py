from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db.database import init_db
from app.routers import admin as admin_router
from app.routers import query as query_router
from app.routers import v1 as v1_router
from app.services import authz, pattern_config, pii_policy, pii_redactor, pipeline_executor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    authz.load()
    pattern_config.load()
    pii_policy.load()
    authz.check_bootstrap()
    yield
    pipeline_executor.shutdown()


app = FastAPI(title="Harness IA", lifespan=lifespan)

app.include_router(query_router.router)
app.include_router(admin_router.router)

# PRD-015 Section 9.3: off means the routes are not mounted and /v1/* is 404.
# Read once, at import, like every other route decision here.
if settings.V1_ENABLED:
    app.include_router(v1_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
