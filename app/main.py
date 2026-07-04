from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import init_db
from app.routers import query as query_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Harness IA", lifespan=lifespan)

app.include_router(query_router.router)

# Remaining routers registered by later stories:
#   - app.routers.admin   (GET /audit, GET /stats) -> STORY-010, STORY-011


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
