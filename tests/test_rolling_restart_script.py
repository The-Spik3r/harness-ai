"""scripts/rolling_restart.sh: static contract plus control flow against a fake `docker`.

PRD-019 STORY-009, acting on F6 and D4. No Docker, no DB: the script runs
against two bash shims (`docker`, `sleep`) that keep one readiness file per
service. The live run against real containers is STORY-010.

Nothing here restates a number the script derives: the drain window is checked
against `HEALTH_INTERVAL_S` (parsed from deploy/lb/Caddyfile by
tests/_balancer_stack.py), the 120 s fallback against `Settings`, the service
list against docker-compose.lb.yml.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest
import yaml

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from app.config import Settings
from tests._balancer_stack import HEALTH_INTERVAL_S

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "rolling_restart.sh"
_COMPOSE_LB = _ROOT / "docker-compose.lb.yml"


def _find_bash() -> str | None:
    """A usable bash. On Windows, Git Bash: `bash` on PATH may be WSL's System32 one."""
    candidates: list[str] = []
    if sys.platform == "win32":
        git = shutil.which("git")
        if git:
            root = pathlib.Path(git).resolve().parents[1]
            candidates += [str(root / "bin" / "bash.exe"), str(root / "usr" / "bin" / "bash.exe")]
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(str(pathlib.Path(base) / "Git" / "bin" / "bash.exe"))
    else:
        found = shutil.which("bash")
        if found:
            candidates.append(found)
    for cand in candidates:
        if not pathlib.Path(cand).is_file():
            continue
        try:
            out = subprocess.run(
                [cand, "-c", "echo ok"], capture_output=True, text=True, timeout=20
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0 and out.stdout.strip() == "ok":
            return cand
    return None


_BASH = _find_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no usable bash")


def _text() -> str:
    return _SCRIPT.read_bytes().decode("utf-8")


# --------------------------------------------------------------------- static


def test_lf_and_executable_bit():
    # PRD-019 STORY-009: LF only (.gitattributes forces *.sh), mode 100755.
    assert b"\r" not in _SCRIPT.read_bytes()
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available")
    out = subprocess.run(
        [git, "ls-files", "-s", "scripts/rolling_restart.sh"],
        cwd=_ROOT, capture_output=True, text=True,
    ).stdout
    if not out.strip():
        pytest.skip("script not in the index yet")
    assert out.startswith("100755 "), out


def test_strict_mode():
    assert "set -euo pipefail" in _text().splitlines()


@needs_bash
def test_bash_syntax():
    out = subprocess.run([_BASH, "-n", _SCRIPT.as_posix()], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_service_list_matches_compose():
    # PRD-019 F6: the instances are the compose services that carry `build`
    # (the `*harness-instance` anchor); `lb` is an image and must not be restarted.
    services = yaml.safe_load(_COMPOSE_LB.read_text(encoding="utf-8"))["services"]
    built = [name for name, spec in services.items() if "build" in spec]
    assert built == ["harness-a", "harness-b"]
    m = re.search(r"^SERVICES=\(([^)]*)\)\s*$", _text(), re.M)
    assert m, "SERVICES=(...) must be one line"
    assert m.group(1).split() == built
    assert "lb" not in m.group(1).split()


def test_readiness_runs_in_container_with_python_urllib():
    # Instances publish no port and the image has no curl (Dockerfile:49,86-87).
    text = _text()
    assert re.search(r'exec -T "\$svc" python -c', text)
    assert "urllib.request" in text and "urllib.error" in text
    assert not re.search(r"\b(curl|wget)\b", text.replace("no curl", ""))


def test_fallback_literals_match_settings():
    text = _text()
    m = re.search(r'timeout="\$\{timeout:-(\d+)\}"', text)
    assert m, "the OPENROUTER_TIMEOUT_SECONDS fallback must be one `${timeout:-N}` line"
    assert float(m.group(1)) == Settings.model_fields["OPENROUTER_TIMEOUT_SECONDS"].default
    m = re.search(r'\$\{DRAIN_FILE:-([^}]+)\}', text)
    assert m
    assert m.group(1) == Settings.model_fields["DRAIN_FILE"].default
    assert set(re.findall(r'\$\{DRAIN_FILE:-([^}]+)\}', text)) == {m.group(1)}


def test_health_interval_is_parsed_not_restated():
    text = _text()
    assert "deploy/lb/Caddyfile" in text
    assert not re.search(r"health_interval\s*\d", text)
    assert not re.search(r"health_interval=\d", text)


def test_usage_and_header_document_repeatable_f_and_p():
    # PRD-019 STORY-010: the E2E lays an overlay under its own project.
    text = _text()
    assert text.count("[-f COMPOSE_FILE]... [-p PROJECT]") == 2  # header and usage()
    assert re.search(r"^\s*-p\) ", text, re.M)
    assert "FILES+=(" in text


def test_drain_seconds_formula_is_timeout_plus_ten():
    assert re.search(r"DRAIN=\$\(\(timeout \+ 10\)\)", _text())


# ------------------------------------------------------------------ fake docker

_DOCKER_SHIM = r"""#!/usr/bin/env bash
F="$FAKE"
printf '%s\n' "$(echo "$*" | tr '\n' ' ')" >> "$F/calls.log"
shift                                   # compose
# PRD-019 STORY-010: any number of `-f X` and an optional `-p X`.
while [ "$1" = "-f" ] || [ "$1" = "-p" ]; do shift 2; done
sub=$1; shift
case "$sub" in
  exec)
    shift                               # -T
    svc=$1; shift
    case "$1" in
      python)
        if [[ "$*" == *OPENROUTER_TIMEOUT_SECONDS* ]]; then
          cat "$F/container_timeout" 2>/dev/null
          exit 0
        fi
        f="$F/ready_$svc"
        first=$(head -n 1 "$f")
        if [ "$(wc -l < "$f")" -gt 1 ]; then
          tail -n +2 "$f" > "$f.tmp" && mv "$f.tmp" "$f"
        fi
        [ "$first" = "down" ] && exit 1
        echo "$first"
        ;;
      sh)
        if [[ "$3" == *touch* ]] && [ ! -f "$F/ignore_touch" ]; then
          echo 503 > "$F/ready_$svc"
        fi
        ;;
    esac
    ;;
  up)
    svc="${@: -1}"
    if [ -f "$F/after_up_$svc" ]; then cp "$F/after_up_$svc" "$F/ready_$svc"; else echo 200 > "$F/ready_$svc"; fi
    ;;
esac
exit 0
"""

_SLEEP_SHIM = r"""#!/usr/bin/env bash
echo "sleep $1" >> "$FAKE/calls.log"
if [ "${1%%.*}" -ge 5 ]; then exit 0; fi   # the drain window: do not wait it out
exec "$(PATH=/usr/bin:/bin type -P sleep)" "$1"
"""


class Fake:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.bin = root / "bin"
        self.state = root / "state"
        self.bin.mkdir()
        self.state.mkdir()
        for name, body in (("docker", _DOCKER_SHIM), ("sleep", _SLEEP_SHIM)):
            (self.bin / name).write_bytes(body.replace("\r\n", "\n").encode())
        # Git Bash puts /usr/bin ahead of a prepended PATH entry, so the real
        # `sleep` would win: a function from BASH_ENV beats any PATH lookup.
        (self.root / "bash_env.sh").write_bytes(
            b'sleep() { "$BASH" "$FAKE_BIN/sleep" "$@"; }\n'
        )
        for svc in ("harness-a", "harness-b"):
            self.set(f"ready_{svc}", "200")

    def set(self, name: str, content: str) -> None:
        (self.state / name).write_bytes((content + "\n").encode())

    @property
    def calls(self) -> list[str]:
        path = self.state / "calls.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def run(self, extra_env: dict[str, str] | None = None, args: tuple[str, ...] = ()):
        env = dict(os.environ)
        env.pop("OPENROUTER_TIMEOUT_SECONDS", None)
        env.pop("DRAIN_SECONDS", None)
        env.update(
            FAKE=self.state.as_posix(),
            FAKE_BIN=self.bin.as_posix(),
            BASH_ENV=(self.root / "bash_env.sh").as_posix(),
            PATH=str(self.bin) + os.pathsep + env.get("PATH", ""),
            POLL_SECONDS="1", DRAIN_WAIT_SECONDS="3", READY_TIMEOUT_SECONDS="3",
        )
        env["DRAIN_SECONDS"] = "7"
        env.update(extra_env or {})
        return subprocess.run(
            [_BASH, _SCRIPT.as_posix(), *args],
            capture_output=True, text=True, timeout=60, env=env, cwd=str(self.root),
        )


@pytest.fixture
def fake(tmp_path):
    return Fake(tmp_path)


def _first(calls: list[str], needle: str, start: int = 0) -> int:
    for i in range(start, len(calls)):
        if needle in calls[i]:
            return i
    raise AssertionError(f"no call containing {needle!r} after {start}: {calls}")


@needs_bash
def test_refuses_when_an_instance_is_not_ready(fake):
    fake.set("ready_harness-b", "503")
    res = fake.run()
    assert res.returncode == 2
    assert "harness-b" in res.stderr
    assert not any("touch" in c or " up " in c for c in fake.calls)


@needs_bash
def test_happy_path_order_and_drain_window(fake):
    res = fake.run(args=("-f", "docker-compose.lb.yml"))
    assert res.returncode == 0, res.stderr
    calls = fake.calls
    a_touch = _first(calls, "touch")
    assert "harness-a" in calls[a_touch]
    a_poll = _first(calls, "python", a_touch)
    a_sleep = _first(calls, "sleep 17", a_poll)
    a_up = _first(calls, "up ", a_sleep)
    assert "harness-a" in calls[a_up]
    assert "--force-recreate" in calls[a_up] and "--no-deps" in calls[a_up]
    a_ready = _first(calls, "harness-a python", a_up)
    b_touch = _first(calls, "touch", a_ready)
    assert "harness-b" in calls[b_touch]
    b_up = _first(calls, "up ", b_touch)
    assert "harness-b" in calls[b_up]
    # PRD-019 STORY-010: one `-f` and no `-p` still reach compose unchanged.
    assert all("-f docker-compose.lb.yml" in c for c in calls if c.startswith("compose"))
    assert not any(" -p " in c for c in calls)
    # The drain window links the script to the Caddyfile: 2 * health_interval + DRAIN_SECONDS.
    sleeps = [int(c.split()[1]) for c in calls if c.startswith("sleep ")]
    assert 2 * int(HEALTH_INTERVAL_S) + 7 in sleeps


@needs_bash
def test_stops_when_replacement_never_ready(fake):
    fake.set("after_up_harness-a", "down")
    res = fake.run()
    assert res.returncode == 4
    assert "harness-a" in res.stderr
    calls = fake.calls
    after = calls[_first(calls, "up "):]
    assert not any("harness-b" in c for c in after), after


@needs_bash
def test_rechecks_other_instances_before_each_drain(fake):
    # harness-a answers 200 once after its recreate, then 503: harness-b must not be drained.
    fake.set("after_up_harness-a", "200\n503")
    res = fake.run()
    assert res.returncode == 2
    assert "harness-a" in res.stderr
    assert not any("touch" in c and "harness-b" in c for c in fake.calls)


@needs_bash
def test_undoes_the_drain_when_it_never_takes_effect(fake):
    (fake.state / "ignore_touch").write_bytes(b"")
    res = fake.run()
    assert res.returncode == 3
    assert "harness-a" in res.stderr
    assert any("rm -f" in c for c in fake.calls)
    assert not any(" up " in c for c in fake.calls)


@needs_bash
@pytest.mark.parametrize(
    "container_value, expected_timeout",
    [("30.5", 31), ("", 120)],  # fraction rounds up; empty falls back to the app default
)
def test_drain_window_uses_the_container_timeout(fake, container_value, expected_timeout):
    # `.env` reaches the containers via env_file, not the operator's shell.
    fake.set("container_timeout", container_value)
    res = fake.run(extra_env={"DRAIN_SECONDS": ""})
    assert res.returncode == 0, res.stderr
    sleeps = [int(c.split()[1]) for c in fake.calls if c.startswith("sleep ")]
    assert 2 * int(HEALTH_INTERVAL_S) + expected_timeout + 10 in sleeps


@needs_bash
def test_operator_env_beats_the_container_value(fake):
    fake.set("container_timeout", "999")
    res = fake.run(extra_env={"DRAIN_SECONDS": "", "OPENROUTER_TIMEOUT_SECONDS": "20"})
    assert res.returncode == 0, res.stderr
    sleeps = [int(c.split()[1]) for c in fake.calls if c.startswith("sleep ")]
    assert 2 * int(HEALTH_INTERVAL_S) + 30 in sleeps


@needs_bash
def test_drain_seconds_env_wins_over_everything(fake):
    fake.set("container_timeout", "999")
    res = fake.run(extra_env={"DRAIN_SECONDS": "9", "OPENROUTER_TIMEOUT_SECONDS": "20"})
    assert res.returncode == 0, res.stderr
    sleeps = [int(c.split()[1]) for c in fake.calls if c.startswith("sleep ")]
    assert 2 * int(HEALTH_INTERVAL_S) + 9 in sleeps


@needs_bash
def test_unknown_flag_is_a_usage_error(fake):
    res = fake.run(args=("--bogus",))
    assert res.returncode == 1
    assert "usage" in res.stderr


@needs_bash
def test_repeated_f_and_p_reach_every_compose_call(fake):
    # PRD-019 STORY-010: overlay files and the project name go to every call, in order.
    res = fake.run(args=("-f", "a.yml", "-f", "b.yml", "-p", "proj"))
    assert res.returncode == 0, res.stderr
    compose_calls = [c for c in fake.calls if c.startswith("compose")]
    assert compose_calls
    assert all(c.startswith("compose -p proj -f a.yml -f b.yml ") for c in compose_calls), compose_calls


@needs_bash
def test_no_file_flag_targets_the_shipped_lb_file(fake):
    res = fake.run()
    assert res.returncode == 0, res.stderr
    compose_calls = [c for c in fake.calls if c.startswith("compose")]
    assert all(c.startswith("compose -f ") and "docker-compose.lb.yml " in c for c in compose_calls), compose_calls


@needs_bash
@pytest.mark.parametrize("args", [("-p",), ("-p", "one", "-p", "two"), ("-f",)])
def test_p_without_value_or_twice_is_a_usage_error(fake, args):
    res = fake.run(args=args)
    assert res.returncode == 1
    assert "usage" in res.stderr
    assert not any(" up " in c or "touch" in c for c in fake.calls)
