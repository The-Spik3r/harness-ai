"""The Caddyfile's @backend_routes matcher covers every harness route (PRD-015 STORY-018).

In the Docker deployment Caddy is the only front door: a path in
`@backend_routes` is proxied to the backend, and every other path falls through
to the static `file_server`, where an API route is a 404. A router added
without a matching Caddy entry therefore works under `uvicorn` and in every
in-process test, and is silently missing in production. This module turns that
into a test failure.

It reads the routes from `app.main.app` itself, so a new route is checked
without anyone remembering to list it here. Only the matcher's own token list
is restated (`EXPECTED_MATCHER`), on purpose: a test that derived it from the
file would only assert that the file equals itself. The same restating is done
by tests/test_admin_shell.py and tests/test_route_reservations.py.

No Docker and no storage: this runs under `-m "not db"`.
"""

import os
import pathlib
import re

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from app.main import app

_CADDYFILE = pathlib.Path(__file__).resolve().parents[1] / "Caddyfile"

# The matcher as STORY-018 leaves it: PRD-002's Reflex and harness routes, plus
# `/v1/*` for the OpenAI-compatible ingress (PRD-015 Section 6.1).
EXPECTED_MATCHER = (
    "/_event/*",
    "/ping",
    "/_upload",
    "/_upload/*",
    "/query",
    "/audit",
    "/stats",
    "/health",
    "/v1/*",
)

# Reserved by Reflex >=0.8, restated as in tests/test_route_reservations.py.
# Concrete request paths, since `/_event` and `/_upload/...` take a suffix.
REFLEX_PATHS = ("/ping", "/_event/abc", "/_upload", "/_upload/abc")

# FastAPI's own documentation routes. They have never been in the matcher, so
# Caddy does not expose them publicly; this story keeps it that way.
FASTAPI_DOC_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

# Paths that must reach the static file server: Reflex pages (the chat at `/`,
# the console under `/admin/`, the Reports section) and near-misses of `/v1/*`.
STATIC_PATHS = ("/", "/admin/audit", "/admin/usage", "/reports", "/v1", "/v1x", "/v10/models")

# Sample values for path parameters, so `/v1/models/{model_id:path}` is checked
# with a slash in the id, as a real model id has.
_PARAM_SAMPLES = {"model_id": "openai/gpt-4o"}


def _matcher_tokens() -> tuple:
    lines = [
        line.strip()
        for line in _CADDYFILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("@backend_routes ")
    ]
    assert len(lines) == 1, f"expected one @backend_routes line in the Caddyfile, found {len(lines)}"
    name, kind, *tokens = lines[0].split()
    assert kind == "path", f"@backend_routes is a {kind!r} matcher, expected 'path'"
    return tuple(tokens)


def _caddy_path_matches(pattern: str, path: str) -> bool:
    """The subset of Caddy's `path` matcher this Caddyfile uses.

    An exact path, or a single trailing `*`, which matches any suffix, slashes
    included. Any other wildcard placement is refused rather than mis-modelled:
    `test_the_matcher_uses_only_modelled_wildcards` fails first.
    """
    if pattern.endswith("*"):
        return path.startswith(pattern[:-1])
    return path == pattern


def _matched(path: str, tokens: tuple) -> bool:
    return any(_caddy_path_matches(pattern, path) for pattern in tokens)


def _concrete(path: str) -> str:
    def sample(match: re.Match) -> str:
        name = match.group(1).split(":", 1)[0]
        return _PARAM_SAMPLES.get(name, name)

    return re.sub(r"\{([^}]+)\}", sample, path)


def _harness_route_paths() -> set:
    # Mirrors tests/test_route_reservations.py: include_router() results are
    # _IncludedRouter wrappers, whose real routes sit on original_router.
    paths = set()
    for route in app.routes:
        if type(route).__name__ == "_IncludedRouter":
            paths.update(r.path for r in route.original_router.routes)
        elif hasattr(route, "path"):
            paths.add(route.path)
    return paths - FASTAPI_DOC_ROUTES


def test_the_matcher_is_exactly_the_expected_list():
    assert _matcher_tokens() == EXPECTED_MATCHER


def test_the_matcher_uses_only_modelled_wildcards():
    for pattern in _matcher_tokens():
        assert pattern.startswith("/"), pattern
        assert "*" not in pattern[:-1], f"{pattern}: only a trailing * is modelled by this test"


def test_every_harness_route_is_proxied_by_caddy():
    tokens = _matcher_tokens()
    paths = sorted(_harness_route_paths())
    # The /v1 routes are the reason this test exists; make sure they are seen.
    assert {"/v1/chat/completions", "/v1/models", "/v1/models/{model_id:path}"} <= set(paths)
    unmatched = [path for path in paths if not _matched(_concrete(path), tokens)]
    assert not unmatched, f"routes Caddy would send to the static file server: {unmatched}"


def test_reflex_reserved_routes_are_proxied_by_caddy():
    tokens = _matcher_tokens()
    unmatched = [path for path in REFLEX_PATHS if not _matched(path, tokens)]
    assert not unmatched, unmatched


def test_static_paths_fall_through_to_the_file_server():
    tokens = _matcher_tokens()
    proxied = [path for path in STATIC_PATHS if _matched(path, tokens)]
    assert not proxied, f"paths that must stay static but are proxied: {proxied}"


def test_the_path_model_matches_caddy_semantics():
    assert _caddy_path_matches("/v1/*", "/v1/models/openai/gpt-4o")
    assert _caddy_path_matches("/v1/*", "/v1/")
    assert not _caddy_path_matches("/v1/*", "/v1")
    assert _caddy_path_matches("/health", "/health")
    assert not _caddy_path_matches("/health", "/health/x")
    assert _concrete("/v1/models/{model_id:path}") == "/v1/models/openai/gpt-4o"
