import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from app.main import app

# Reserved by Reflex >=0.8 (chat_ui/ pins reflex==0.9.6.post1); see PRD-002 Section 9.
REFLEX_RESERVED_ROUTES = {"/ping", "/_event", "/_upload"}


def _harness_route_paths():
    # FastAPI wraps app.include_router(...) results in _IncludedRouter (lazy
    # router) instead of flattening into APIRoute objects directly on
    # app.routes; descend into original_router.routes to reach real paths.
    paths = set()
    for route in app.routes:
        if type(route).__name__ == "_IncludedRouter":
            paths.update(r.path for r in route.original_router.routes)
        elif hasattr(route, "path"):
            paths.add(route.path)
    return paths


def test_no_route_collides_with_reflex_reserved_routes():
    collisions = _harness_route_paths() & REFLEX_RESERVED_ROUTES
    assert not collisions, f"Harness routes collide with Reflex reserved routes: {collisions}"


def test_expected_harness_routes_present():
    assert {"/query", "/audit", "/stats", "/health"} <= _harness_route_paths()
