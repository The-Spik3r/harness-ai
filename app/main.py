from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import init_db
from app.routers import admin as admin_router
from app.routers import query as query_router
from app.services import authz, pii_redactor, pipeline_executor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pii_redactor.load()
    authz.load()
    authz.check_bootstrap()
    yield
    pipeline_executor.shutdown()


app = FastAPI(title="Harness IA", lifespan=lifespan)

app.include_router(query_router.router)
app.include_router(admin_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
