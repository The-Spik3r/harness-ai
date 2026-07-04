from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import init_db
from app.routers import admin as admin_router
from app.routers import query as query_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Harness IA", lifespan=lifespan)

app.include_router(query_router.router)
app.include_router(admin_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
