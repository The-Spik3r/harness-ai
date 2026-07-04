from fastapi import FastAPI

app = FastAPI(title="Harness IA")

# Routers are registered here by later stories:
#   - app.routers.query   (POST /query)          -> STORY-008
#   - app.routers.admin   (GET /audit, GET /stats) -> STORY-010, STORY-011


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
