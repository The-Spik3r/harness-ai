from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Harness IA", lifespan=lifespan)

# Routers are registered here by later stories:
#   - app.routers.query   (POST /query)          -> STORY-008
#   - app.routers.admin   (GET /audit, GET /stats) -> STORY-010, STORY-011


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
