"""Shared helpers for tests that need a Caddy binary (PRD-019 D8, Section 11).

Caddy is a binary, never a pip package, and is never committed. Tests find it
through `CADDY_BIN` or `PATH`. Locally a missing binary skips the test; CI sets
`HARNESS_REQUIRE_CADDY=1`, so a missing binary there FAILS ("a missing binary
fails in CI, never skips"): a silently skipped balancer test proves nothing.

`PINNED_CADDY_VERSION` is the one version constant. It must equal the tag of
the image in `docker-compose.lb.yml` and `CADDY_VERSION` in the CI install
step; `tests/test_caddy_pin.py` cross-checks all three.
"""

import os
import shutil
import socket

import pytest

PINNED_CADDY_VERSION = "2.11.7"

_TEST_COOKIE_SECRET = "test-secret"


def caddy_binary() -> str:
    """Return the Caddy binary path, or skip (fail under HARNESS_REQUIRE_CADDY=1).

    The flag is read at call time so tests can monkeypatch it. A `CADDY_BIN`
    that does not resolve falls through to `PATH`.
    """
    for candidate in (os.environ.get("CADDY_BIN"), "caddy"):
        if candidate:
            found = shutil.which(candidate)
            if found:
                return found
    reason = (
        "no caddy binary: set CADDY_BIN or put caddy "
        f"{PINNED_CADDY_VERSION} on PATH"
    )
    if os.environ.get("HARNESS_REQUIRE_CADDY") == "1":
        pytest.fail(reason + " (HARNESS_REQUIRE_CADDY=1)")
    pytest.skip(reason)


def caddy_env(port: int, admin_port: int, **extra: str) -> dict:
    """Environment for one `caddy` child.

    Every caddy process needs its own admin port (STORY-004 finding): two
    children sharing the default :2019 collide.
    """
    return {
        **os.environ,
        "PORT": str(port),
        "LB_COOKIE_SECRET": _TEST_COOKIE_SECRET,
        "CADDY_ADMIN": f"localhost:{admin_port}",
        **extra,
    }


def free_port() -> int:
    """A port the OS reports free on 127.0.0.1 right now."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
