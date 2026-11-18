"""The pinned Caddy is one version everywhere (PRD-019 D8, Section 8, Section 11).

Three places name the version: `tests/_caddy.py`, the image tag in
`docker-compose.lb.yml` and the install step in `.github/workflows/ci.yml`.
The static tests here cross-check them so a bump cannot touch one and miss the
others; the live test asserts the binary actually on the machine is the pinned
one. The SHA-256 is restated here on purpose (not derived from ci.yml): the
upstream release publishes SHA-512 only, so this one is ours from STORY-004.

The static tests need no binary and run under `-m "not db"`. The live test
skips locally without a binary and fails in CI (`HARNESS_REQUIRE_CADDY=1`).
"""

import pathlib
import re
import subprocess

import pytest
import yaml

from tests._caddy import PINNED_CADDY_VERSION, caddy_binary, caddy_env

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_COMPOSE_LB = _ROOT / "docker-compose.lb.yml"

# PRD-019 STORY-004: SHA-256 of caddy_2.11.7_linux_amd64.tar.gz.
_LINUX_SHA256 = "727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b"


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_compose_image_tag_is_the_pinned_version():
    image = _load(_COMPOSE_LB)["services"]["lb"]["image"]
    prefix = f"caddy:{PINNED_CADDY_VERSION}@sha256:"
    assert image.startswith(prefix), image
    assert re.fullmatch(r"[0-9a-f]{64}", image[len(prefix):]), image


def test_ci_installs_the_pinned_caddy():
    # PRD-019 D8: CI downloads the pinned release, verifies it, puts it on
    # PATH, and the test step turns a missing binary into a failure.
    steps = _load(_CI)["jobs"]["test"]["steps"]
    names = [s.get("name", "") for s in steps]
    install = next(s for s in steps if "Caddy" in s.get("name", ""))
    run_tests = next(s for s in steps if s.get("name") == "Run tests")

    assert install["env"]["CADDY_VERSION"] == PINNED_CADDY_VERSION
    assert install["env"]["CADDY_SHA256"] == _LINUX_SHA256
    script = install["run"]
    for needle in ("sha256sum -c", "GITHUB_PATH", "CADDY_VERSION", "CADDY_SHA256"):
        assert needle in script, needle
    # `caddy version` runs by full path: GITHUB_PATH only reaches later steps.
    assert re.search(r'caddy"? version', script), script
    assert steps.index(install) < steps.index(run_tests), names
    assert str(run_tests["env"]["HARNESS_REQUIRE_CADDY"]) == "1"


def test_helper_skips_or_fails_when_caddy_is_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("CADDY_BIN", str(tmp_path / "missing-caddy"))
    monkeypatch.setenv("PATH", str(tmp_path))

    monkeypatch.delenv("HARNESS_REQUIRE_CADDY", raising=False)
    with pytest.raises(pytest.skip.Exception, match="caddy"):
        caddy_binary()

    monkeypatch.setenv("HARNESS_REQUIRE_CADDY", "1")
    with pytest.raises(pytest.fail.Exception, match="caddy"):
        caddy_binary()


def test_caddy_env_gives_each_child_its_own_admin_port(monkeypatch):
    monkeypatch.setenv("SOME_EXISTING_VAR", "kept")
    env = caddy_env(8123, 9123, EXTRA="x")
    assert env["PORT"] == "8123"
    assert env["LB_COOKIE_SECRET"]
    assert env["CADDY_ADMIN"] == "localhost:9123"
    assert env["EXTRA"] == "x"
    assert env["SOME_EXISTING_VAR"] == "kept"


def test_caddy_version_is_the_pinned_one():
    result = subprocess.run(
        [caddy_binary(), "version"], capture_output=True, text=True, timeout=30
    )
    assert result.stdout.startswith(f"v{PINNED_CADDY_VERSION} "), result.stdout
