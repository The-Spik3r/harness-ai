"""tests/e2e/docker/compose.lb-e2e.yml: static guard, no Docker (PRD-019 STORY-010).

The Docker E2E itself is opt-in; this file runs everywhere and catches the
overlay drifting from the shipped stack: the instances must run the locally
built image without rebuilding or reading `.env`, the command they run must end
with the image's CMD, and the test-only keys must not leak into the shipped
docker-compose.lb.yml.
"""

from __future__ import annotations

import pathlib
import re

import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_OVERLAY = _ROOT / "tests" / "e2e" / "docker" / "compose.lb-e2e.yml"
_SHIPPED = _ROOT / "docker-compose.lb.yml"
_DOCKERFILE = _ROOT / "Dockerfile"
_INSTANCES = ("harness-a", "harness-b")


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps compose's `!reset` / `!override` tags as marker strings."""


def _tagged(loader, tag_suffix, node):
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    return (f"!{tag_suffix}", value)


_Loader.add_multi_constructor("!", _tagged)


def _overlay() -> dict:
    return yaml.load(_OVERLAY.read_text(encoding="utf-8"), Loader=_Loader)


def _image_cmd() -> str:
    """The Dockerfile CMD, whitespace-normalised and without line continuations."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    start = re.search(r"^CMD (.+?)(?=\n\s*\n|\Z)", text, re.M | re.S)
    assert start, "Dockerfile has no shell-form CMD"
    body = start.group(1).replace("\\\n", " ")
    return " ".join(body.split())


def test_overlay_parses_and_names_the_services():
    services = _overlay()["services"]
    assert set(services) == {"libsql", *_INSTANCES, "lb"}


def test_instances_share_the_local_image_and_never_build_or_pull():
    services = _overlay()["services"]
    for name in _INSTANCES:
        spec = services[name]
        assert spec["image"] == "harness-lb-e2e:local", name
        assert spec["pull_policy"] == "never", name
        # `up --force-recreate` (rolling_restart.sh) must not rebuild.
        assert spec["build"] == ("!reset", "null"), name  # scalars load as text
        # A developer's .env must not reach the test.
        assert spec["env_file"] == ("!reset", []), name
        assert "libsql" in spec["depends_on"], name
    assert services["harness-a"]["command"] == services["harness-b"]["command"]


def test_instance_command_ends_with_the_image_cmd():
    # The overlay restates the CMD to background the stub first; a Dockerfile
    # change must fail here, not silently test a different start command.
    command = _overlay()["services"]["harness-a"]["command"]
    assert command[:2] == ["sh", "-c"] and len(command) == 3
    script = " ".join(command[2].split()).replace("$$", "$")
    cmd = _image_cmd()
    assert script.endswith(cmd), f"overlay command {script!r} does not end with the image CMD {cmd!r}"
    head = script[: -len(cmd)]
    assert head.startswith("python scripts/stub_openrouter.py ") and head.rstrip().endswith("&")
    assert "--script tests/e2e/scripts/docker_smoke.json" in head
    assert (_ROOT / "tests" / "e2e" / "scripts" / "docker_smoke.json").is_file()


def test_instances_use_loopback_stub_and_a_throwaway_database():
    env = _overlay()["services"]["harness-a"]["environment"]
    assert env["OPENROUTER_BASE_URL"] == "http://127.0.0.1:9100/v1"
    assert env["DATABASE_URL"] == "http://libsql:8080"
    assert env["TURSO_AUTH_TOKEN"] == ""
    # The admin token is required from the caller, never a literal.
    assert env["ADMIN_TOKEN"].startswith("${HARNESS_LB_E2E_ADMIN_TOKEN:?")


def test_only_the_host_side_of_the_balancer_port_is_remapped():
    # PRD-019 D7: lb keeps the build-time port inside the network (8000, the
    # shipped $PORT default); only the loopback host side moves.
    ports = _overlay()["services"]["lb"]["ports"]
    assert ports[0] == "!override"
    assert len(ports[1]) == 1
    assert re.fullmatch(r"127\.0\.0\.1:\$\{HARNESS_LB_E2E_PORT:\?[^}]+\}:8000", ports[1][0]), ports


def test_shipped_lb_file_carries_no_test_only_keys():
    text = _SHIPPED.read_text(encoding="utf-8")
    for needle in ("harness-lb-e2e", "HARNESS_LB_E2E", "stub_openrouter", "pull_policy", "libsql", "!reset", "!override"):
        assert needle not in text, f"docker-compose.lb.yml must stay free of test-only {needle!r}"
    shipped = yaml.safe_load(text)["services"]
    assert shipped["lb"]["image"].startswith("caddy:")
    assert "build" in shipped["harness-a"] and "build" in shipped["harness-b"]
