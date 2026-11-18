"""The balancer Caddyfile and docker-compose.lb.yml keep PRD-019's contract (F3, F4).

`deploy/lb/Caddyfile` and `docker-compose.lb.yml` are the shipped two-instance
topology. Every directive in the Caddyfile guards a decision: sticky cookie
affinity (D2), the `/ready` probe (D3, D5), the timeout invariant (D6, Section
9.3), no replay of a request (D9). A harmless-looking edit (an `encode`, a
`retry_match`, a shorter header timeout) silently breaks one of them, so this
module pins the directive set.

The expected values are restated here on purpose: a test that derived them
from the file would only assert that the file equals itself (same reasoning as
tests/test_caddyfile_routes.py). Only the two numbers that must track the
application are read from the settings model: `OPENROUTER_TIMEOUT_SECONDS`
and `READY_DB_TIMEOUT_SECONDS`.

No Docker and no storage: this runs under `-m "not db"`. The last test runs
`caddy validate` when a Caddy binary is found (`CADDY_BIN` or `PATH`) and is
skipped otherwise.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from app.config import Settings

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CADDYFILE = _ROOT / "deploy" / "lb" / "Caddyfile"
_COMPOSE_LB = _ROOT / "docker-compose.lb.yml"
_COMPOSE_SINGLE = _ROOT / "docker-compose.yml"

# PRD-019 F3: the one upstream line. STORY-007 substitutes it textually, so it
# must stay one literal line with no `{$X:default}` form.
_UPSTREAM_LINE = "reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {"

# PRD-019 F3 (amended after STORY-004): the two fixed 503 bodies.
_V1_BODY = (
    '{"error":{"message":"Service unavailable. Retry after the Retry-After '
    'interval.","type":"api_error","param":null,"code":"service_unavailable"}}'
)
_DETAIL_BODY = '{"detail":"Service unavailable"}'

# PRD-019 Section 8: the balancer image, pinned by digest (STORY-004).
_LB_IMAGE = (
    "caddy:2.11.7@sha256:"
    "36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e"
)

# PRD-018 AUDIT_BUFFER_DIR, as docker-compose.yml mounts it.
_JOURNAL_VOLUME = "harness-audit-buffer:/var/lib/harness/audit-buffer"

# PRD-019 F3: directives the balancer must never carry. `encode` and `log`
# sit in the streaming path; `unhealthy_status` would let a breaker-open 503
# mark an instance dead passively; `retry_match` would replay a request (D9).
_FORBIDDEN_DIRECTIVES = ("encode", "log", "unhealthy_status", "retry_match")


def _raw() -> str:
    # splitlines() below tolerates CRLF checkouts on Windows.
    return _CADDYFILE.read_text(encoding="utf-8")


def _lines() -> list[str]:
    """Directive lines: comments and blank lines dropped, indentation stripped."""
    out = []
    for line in _raw().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


def _seconds(token: str) -> float:
    """Parse a Caddy duration of the form `<n>s` or `<n>m`."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([sm])", token)
    assert match, f"unsupported duration {token!r} in {_CADDYFILE}"
    return float(match.group(1)) * (60 if match.group(2) == "m" else 1)


def _value(directive: str) -> str:
    """The single argument of a one-argument directive, asserted to appear once."""
    found = [ln.split(None, 1)[1] for ln in _lines() if ln.split(None, 1)[0] == directive]
    assert len(found) == 1, f"{_CADDYFILE}: expected one `{directive}`, got {found}"
    return found[0]


def _compose(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_affinity_policy_and_site_address():
    # PRD-019 D2: cookie affinity named harness_lb, signed by a placeholder
    # (never a literal secret); the site listens on the instances' $PORT.
    assert _lines()[0] == ":{$PORT}"
    assert "lb_policy cookie harness_lb {$LB_COOKIE_SECRET}" in _lines()
    # PRD-019 D9: only a bounded wait for a healthy upstream, 5 s.
    assert _value("lb_try_duration") == "5s"


def test_upstream_line_is_the_literal_one_story_007_substitutes():
    # PRD-019 F3 / STORY-004: an env default does not parse, so the live test
    # replaces this exact line. It must appear once, with no default form.
    lines = [ln for ln in _raw().splitlines() if ln.strip().startswith("reverse_proxy")]
    assert [ln.strip() for ln in lines] == [_UPSTREAM_LINE]


def test_active_and_passive_health_directives():
    # PRD-019 D3/D5: active probe on /ready, 5 s interval, 3 s timeout, 200 only.
    assert _value("health_uri") == "/ready"
    assert _value("health_interval") == "5s"
    assert _value("health_timeout") == "3s"
    assert _value("health_status") == "200"
    # Passive: a dead upstream is out for 30 s; no unhealthy_status (see below).
    assert _value("fail_duration") == "30s"


def test_timeouts_and_stream_close_delay():
    # PRD-019 D6: dial 3 s; the header timeout is OPENROUTER_TIMEOUT_SECONDS + 30 s.
    assert _value("dial_timeout") == "3s"
    openrouter_default = int(Settings.model_fields["OPENROUTER_TIMEOUT_SECONDS"].default)
    assert _seconds(_value("response_header_timeout")) == openrouter_default + 30 == 150
    # Websockets survive a balancer config reload.
    assert _value("stream_close_delay") == "5m"


def test_ready_db_timeout_is_below_the_health_timeout():
    # PRD-019 Section 9.3: /ready must answer before the balancer gives up on
    # the probe, or a slow database would read as a dead instance.
    ready_timeout = Settings.model_fields["READY_DB_TIMEOUT_SECONDS"].default
    assert ready_timeout < _seconds(_value("health_timeout"))


def test_forbidden_directives_are_absent():
    # PRD-019 F3 / D9: no encode, access log, unhealthy_status or retry_match,
    # no env-default form in the upstream, and no global options block (the
    # STORY-007 harness adds its own `admin`).
    first_tokens = [ln.split(None, 1)[0] for ln in _lines()]
    for directive in _FORBIDDEN_DIRECTIVES:
        assert directive not in first_tokens, f"{_CADDYFILE} must not use `{directive}`"
    assert not re.search(r"\{\$[A-Za-z_]+:", "\n".join(_lines())), (
        f"{_CADDYFILE}: no {{$VAR:default}} form (it does not parse inside the upstream line)"
    )
    # A global options block is a bare `{` line before the site address.
    assert _lines()[0] != "{"


def test_handle_errors_answers_one_503_with_retry_after():
    # PRD-019 F3 / D9: balancer-raised 502, 503 and 504 become one 503 with
    # Retry-After 10 (PRD-018's breaker interval).
    lines = _lines()
    assert [ln for ln in lines if ln.startswith("handle_errors")] == ["handle_errors 502 503 504 {"]
    assert "header Retry-After 10" in lines
    assert "@v1 path /v1/*" in lines
    assert f"respond @v1 `{_V1_BODY}` 503" in lines
    assert f"respond `{_DETAIL_BODY}` 503" in lines
    assert len([ln for ln in lines if ln.startswith("respond")]) == 2

    v1 = json.loads(_V1_BODY)["error"]
    assert v1["code"] == "service_unavailable"
    assert v1["type"] == "api_error"
    assert v1["param"] is None
    assert v1["message"] == "Service unavailable. Retry after the Retry-After interval."
    assert json.loads(_DETAIL_BODY) == {"detail": "Service unavailable"}


def test_compose_instances_match_the_upstreams_and_only_lb_publishes_ports():
    # PRD-019 F4 / D7: two named services, the same ones the Caddyfile proxies
    # to; only lb publishes the (build-time) $PORT.
    services = _compose(_COMPOSE_LB)["services"]
    instances = {name for name in services if name != "lb"}
    assert instances == {"harness-a", "harness-b"}

    upstream_line = [ln for ln in _lines() if ln.startswith("reverse_proxy")][0]
    hosts = re.findall(r"(\S+?):\{\$PORT\}", upstream_line)
    assert len(hosts) == 2 and set(hosts) == instances

    for name in instances:
        assert "ports" not in services[name], f"{name} must publish no port"
    assert services["lb"]["ports"] == ["${PORT:-8000}:${PORT:-8000}"]


def test_compose_instances_share_one_definition_and_the_journal_volume():
    # PRD-019 F4: one YAML anchor (same build, env_file, PORT) and the named
    # volume at AUDIT_BUFFER_DIR, identical to docker-compose.yml's.
    compose = _compose(_COMPOSE_LB)
    a, b = compose["services"]["harness-a"], compose["services"]["harness-b"]
    assert a == b
    assert a["build"] == {"context": ".", "args": {"PORT": "${PORT:-8000}"}}
    assert a["env_file"] == [".env"]
    assert "AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer" in a["environment"]
    assert "PORT=${PORT:-8000}" in a["environment"]
    assert a["volumes"] == [_JOURNAL_VOLUME]
    assert "harness-audit-buffer" in compose["volumes"]

    # The two compose files cannot drift apart on the journal mount.
    single = _compose(_COMPOSE_SINGLE)["services"]["harness-ai"]
    assert single["volumes"] == a["volumes"]
    assert "AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer" in single["environment"]


def test_compose_lb_service():
    # PRD-019 F4 / Section 8: digest-pinned image, the Caddyfile mounted
    # read-only, a required secret, and both instances healthy before start.
    compose = _compose(_COMPOSE_LB)
    lb = compose["services"]["lb"]
    assert lb["image"] == _LB_IMAGE
    assert lb["volumes"] == ["./deploy/lb/Caddyfile:/etc/caddy/Caddyfile:ro"]

    env = lb["environment"]
    secret = [e for e in env if e.startswith("LB_COOKIE_SECRET=")]
    assert len(secret) == 1
    # `:?` makes compose fail when unset; a `:-` default would ship a known secret.
    assert "${LB_COOKIE_SECRET:?" in secret[0] and ":-" not in secret[0]
    assert "PORT=${PORT:-8000}" in env

    assert lb["depends_on"] == {
        "harness-a": {"condition": "service_healthy"},
        "harness-b": {"condition": "service_healthy"},
    }
    # Decision recorded in the plan: a project of its own, so this stack's
    # journal volume is not the single-instance stack's.
    assert compose["name"] == "harness-ai-lb"


def test_caddy_validate_accepts_the_file():
    # PRD-019 F3 (verified in STORY-004): the shipped file is accepted by the
    # pinned Caddy. Optional: skipped when no binary is available.
    caddy = shutil.which(os.environ.get("CADDY_BIN") or "caddy")
    if caddy is None:
        pytest.skip("no caddy binary (set CADDY_BIN or put caddy on PATH)")
    env = {
        **os.environ,
        "PORT": "8000",
        "LB_COOKIE_SECRET": "test-secret",
        "CADDY_ADMIN": "localhost:0",
    }
    result = subprocess.run(
        [caddy, "validate", "--config", str(_CADDYFILE), "--adapter", "caddyfile"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
