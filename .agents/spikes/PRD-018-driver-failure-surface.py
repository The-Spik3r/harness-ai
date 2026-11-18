"""PRD-018 F1 / STORY-001 -- driver failure-surface capture. THROWAWAY, not production code.

Two roles in one file.

* HOST orchestrator (`.venv/Scripts/python`, from the repo root): drives Docker
  (`docker pause`, `docker restart -t 0`), starts probes, and writes every record
  to `<out>/captures.jsonl`.
* PROBE: a fresh process with a fresh raw `libsql` client, run in a throwaway
  `docker run -i --rm --network harness-test-net` container of the harness-ai
  image (bind-mounting only `app/` and `.agents/spikes/`, never the repo root,
  which holds a real `.env`). The host talks to it over stdin/stdout.

Every driver call is timed and labelled with the call that raised it (connect /
execute / fetchone / fetchall / commit / rollback / close). Every message goes
through `app.db.database._redacted()` and an SQL guard before it is written.
All writes go to the scratch table `prd018_spike_rows`, dropped by `restore`.

Commands (cwd = repo root; OUT = a scratch dir outside the repo):

    .venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py host preflight --out OUT
    ... host run refused|connect-timeout|pause|restart|idle|q1|q2|q3|control --out OUT [--where innet|host] [--variant V]
    ... host restore --out OUT        # ALWAYS safe; leaves the dev server running + unpaused

If anything crashes mid-way run `host restore` before anything else.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

SERVER = "harness-libsql-dev"
NETWORK = "harness-test-net"
IN_NET_URL = "http://harness-libsql-dev:8080"
HOST_URL = "http://127.0.0.1:8080"
REFUSED_URL = "http://127.0.0.1:1"
UNROUTABLE_URLS = ("http://10.255.255.1:8080", "http://192.0.2.1:8080")
TABLE = "prd018_spike_rows"
IDLE_SECONDS = 15.0
IDLE_CONTROL_SECONDS = 8.0
PAUSE_HOLD_LONG = 60.0
PAUSE_HOLD_SHORT = 15.0
REPEATS = 3
PROBE_WALL_TIMEOUT = 300.0
IMAGE = "harness-ai-harness-ai"

SELF = Path(__file__).resolve()
REPO = SELF.parents[2]

_SQL_WORDS = re.compile(r"\b(prd018_spike_rows|INSERT|SELECT|CREATE|DROP)\b", re.IGNORECASE)


# =====================================================================================
# PROBE ROLE
# =====================================================================================
class Probe:
    """Runs in the container (or on the host). Talks to the raw libsql client."""

    def __init__(self, ns):
        self.ns = ns
        self.step_no = 0
        self.redact = None

    # -- output ---------------------------------------------------------------------
    def _emit(self, rec: dict) -> None:
        rec.update(
            probe=self.ns.name, variant=self.ns.variant or self.ns.name,
            repeat=self.ns.repeat, where=self.ns.where, marker=self.ns.marker,
            t_wall=round(time.time(), 3),
        )
        print("REC " + json.dumps(rec), flush=True)

    def _say(self, token: str) -> None:
        print(token, flush=True)

    def _wait_go(self) -> None:
        line = sys.stdin.readline().strip()
        if line != "GO":
            raise SystemExit(f"expected GO, got {line!r}")

    def _clean(self, message: str) -> tuple[str, bool]:
        text = self.redact(message)
        m = _SQL_WORDS.search(text)
        if m:
            return text[: m.start()] + "<sql elided>", True
        return text, False

    # -- the timed step: re-raises the ORIGINAL exception (_RecordedClient rule) -----
    def step(self, step: str, call: str, fn, client=None):
        self.step_no += 1
        before = self._in_tx(client)
        started = time.monotonic()
        outcome, exc_type, message, elided = "ok", None, None, False
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 - spike: record then re-raise the same object
            outcome, exc_type = "raised", type(exc).__name__
            message, elided = self._clean(str(exc))
            raise
        finally:
            self._emit(dict(
                step=step, n=self.step_no, call=call,
                elapsed_s=round(time.monotonic() - started, 3), outcome=outcome,
                exc_type=exc_type, message=message, sql_elided=elided,
                in_tx_before=before, in_tx_after=self._in_tx(client),
            ))

    def attempt(self, step: str, call: str, fn, client=None):
        """Like step(), but a raise is swallowed (the record already holds it)."""
        try:
            return True, self.step(step, call, fn, client)
        except BaseException as exc:  # noqa: BLE001
            return False, exc

    @staticmethod
    def _in_tx(client):
        if client is None:
            return None
        try:
            return bool(client.in_transaction)
        except BaseException:  # noqa: BLE001
            return "n/a"

    # -- helpers --------------------------------------------------------------------
    def connect(self, url=None, **kw):
        import libsql
        url = url or self.ns.url
        return self.step("connect", "connect", lambda: libsql.connect(url, auth_token="", **kw))

    def sql(self, client, label, sql, params=(), fetch=None):
        """execute and fetch are two steps so the report shows where the request leaves."""
        cur = self.step(label, "execute", lambda: client.execute(sql, params), client)
        if fetch == "one":
            return self.step(label, "fetchone", lambda: cur.fetchone(), client)
        if fetch == "all":
            return self.step(label, "fetchall", lambda: cur.fetchall(), client)
        return cur

    def insert(self, client, label, marker):
        return self.sql(client, label, f"INSERT INTO {TABLE} (marker, note) VALUES (?, ?)", (marker, label))

    def select1(self, client, label="select1"):
        return self.sql(client, label, "SELECT 1", (), fetch="one")

    # -- probes ---------------------------------------------------------------------
    def p_select1(self):
        c = self.connect()
        self.select1(c)
        self.step("close", "close", c.close, c)

    def p_setup(self):
        c = self.connect()
        self.sql(c, "create", f"CREATE TABLE IF NOT EXISTS {TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT, marker TEXT NOT NULL, note TEXT)")
        self.step("setup-commit", "commit", c.commit, c)

    def p_teardown(self):
        c = self.connect()
        self.sql(c, "drop", f"DROP TABLE IF EXISTS {TABLE}")
        self.step("teardown-commit", "commit", c.commit, c)

    def p_leftovers(self):
        c = self.connect()
        rows = self.sql(c, "leftovers", "SELECT name FROM sqlite_master WHERE name LIKE 'prd018_spike_%'", fetch="all")
        self._emit(dict(step="leftovers", call="result", leftover_tables=[r[0] for r in rows]))

    def p_landed(self):
        c = self.connect()
        row = self.sql(c, "landed", f"SELECT COUNT(*) FROM {TABLE} WHERE marker = ?", (self.ns.marker,), fetch="one")
        self._emit(dict(step="landed", call="result", landed=bool(row[0]), count=row[0]))

    def p_insert_commit(self):  # positive control (Q1c)
        c = self.connect()
        self.insert(c, "insert", self.ns.marker)
        self.step("commit", "commit", c.commit, c)

    def p_connfault(self):  # F1 / F2
        c = self.connect()
        ok, _ = self.attempt("select1", "execute", lambda: c.execute("SELECT 1", ()), c)
        if ok:
            self.attempt("select1", "fetchone", lambda: _.fetchone(), c)
        c2 = self.connect()
        self.attempt("never-used-commit", "commit", c2.commit, c2)
        c3 = self.connect()
        self.attempt("never-used-rollback", "rollback", c3.rollback, c3)

    def p_pause(self):  # F3a-d. hold/restart is host's job; mode picks the in-flight call
        mode = self.ns.mode
        c = self.connect()
        self.select1(c, "warm")
        if mode == "commit":
            self.insert(c, "insert", self.ns.marker)
        self._say("READY pause")
        self._wait_go()
        self._say("SENT pause")
        if mode == "commit":
            ok, _ = self.attempt("in-flight", "commit", c.commit, c)
        else:
            ok, _ = self.attempt("in-flight", "execute",
                                 lambda: c.execute(f"INSERT INTO {TABLE} (marker, note) VALUES (?, ?)", (self.ns.marker, "in-flight")), c)
            if ok:
                self.attempt("after-commit", "commit", c.commit, c)

    def p_restart(self):  # F4a-c
        mode = self.ns.mode
        c = self.connect()
        if mode == "a":
            self.insert(c, "insert-m1", self.ns.marker)
        elif mode == "b":
            self.insert(c, "insert", self.ns.marker)
        else:
            self.select1(c, "warm")
        self._say("READY restart")
        self._wait_go()
        self._say("SENT restart")
        if mode == "a":
            self.attempt("insert-m2", "execute",
                         lambda: c.execute(f"INSERT INTO {TABLE} (marker, note) VALUES (?, ?)", (self.ns.marker2, "m2")), c)
            self.attempt("commit-after", "commit", c.commit, c)
            self.attempt("rollback-after", "rollback", c.rollback, c)
        elif mode == "b":
            self.attempt("commit", "commit", c.commit, c)
        else:
            self.attempt("commit-no-tx", "commit", c.commit, c)
            self.attempt("select1-after", "execute", lambda: c.execute("SELECT 1", ()), c)

    def p_idle(self):  # F5a-e + control
        mode, secs = self.ns.mode, self.ns.sleep
        c = self.connect()
        if mode in ("a", "control"):
            self.select1(c, "warm")
        elif mode in ("b", "c"):
            self.insert(c, "insert", self.ns.marker)
        else:  # d, e
            self.select1(c, "warm")
        self._say("SLEEP idle")
        time.sleep(secs)
        self._emit(dict(step="slept", call="sleep", elapsed_s=secs))
        if mode in ("a", "control"):
            ok, cur = self.attempt("after-idle", "execute", lambda: c.execute("SELECT 1", ()), c)
            if ok:
                self.attempt("after-idle", "fetchone", cur.fetchone, c)
        elif mode == "b":
            self.attempt("commit", "commit", c.commit, c)
        elif mode == "c":
            self.attempt("select1", "execute", lambda: c.execute("SELECT 1", ()), c)
            self.attempt("commit", "commit", c.commit, c)
        elif mode == "d":
            self.attempt("commit-no-tx", "commit", c.commit, c)
        elif mode == "e":
            self.attempt("rollback-no-tx", "rollback", c.rollback, c)

    def p_q1(self):
        c = self.connect()
        self.insert(c, "insert", self.ns.marker)
        if self.ns.mode == "b":
            self._say("READY q1")
            self._wait_go()
        self._emit(dict(step="abandon", call="os._exit", in_tx_after=self._in_tx(c)))
        sys.stdout.flush()
        os._exit(0)  # no commit, no close

    def p_q2(self):  # supporting: commit() with no tx vs a real round trip
        c = self.connect()
        self.select1(c, "warm")
        t0 = time.monotonic()
        for _ in range(20):
            c.commit()
        commit_total = time.monotonic() - t0
        t0 = time.monotonic()
        for _ in range(20):
            c.execute("SELECT 1", ()).fetchone()
        select_total = time.monotonic() - t0
        self._emit(dict(step="q2-timing", call="timing", in_tx_after=self._in_tx(c),
                        commit_x20_s=round(commit_total, 4), select_x20_s=round(select_total, 4)))

    def p_q3a(self):  # A: holds an open transaction and stays alive (mode a) or dies (mode b)
        c = self.connect()
        self.insert(c, "insert-a", self.ns.marker)
        if self.ns.mode == "a":
            self._say("READY q3a")
            self._wait_go()
        self._emit(dict(step="abandon", call="os._exit", in_tx_after=self._in_tx(c)))
        sys.stdout.flush()
        os._exit(0)

    def p_q3b(self):  # B: the fresh writer
        kw = {}
        if self.ns.timeout is not None:
            kw["timeout"] = self.ns.timeout
        c = self.connect(**kw)
        ok, _ = self.attempt("writer-insert", "execute",
                             lambda: c.execute(f"INSERT INTO {TABLE} (marker, note) VALUES (?, ?)", (self.ns.marker, "writer")), c)
        if ok:
            self.attempt("writer-commit", "commit", c.commit, c)

    def run(self):
        os.environ.setdefault("OPENROUTER_API_KEY", "spike")
        os.environ.setdefault("ADMIN_TOKEN", "spike")
        os.environ["DATABASE_URL"] = self.ns.url
        os.environ["TURSO_AUTH_TOKEN"] = ""
        sys.path.insert(0, str(REPO))
        from app.db.database import _redacted
        self.redact = _redacted
        fn = getattr(self, "p_" + self.ns.name.replace("-", "_"))
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - record + finish; the step already emitted
            self._emit(dict(step="probe-aborted", call="abort", exc_type=type(exc).__name__,
                            message=self._clean(str(exc))[0]))
        self._say("DONE")


# =====================================================================================
# HOST ROLE
# =====================================================================================
class Host:
    def __init__(self, out: Path):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.captures = out / "captures.jsonl"
        self.state_file = out / "state.json"
        self.rid = 0
        if self.captures.exists():
            with self.captures.open(encoding="utf-8") as fh:
                self.rid = sum(1 for _ in fh)

    # -- capture log ----------------------------------------------------------------
    def log(self, rec: dict) -> None:
        self.rid += 1
        rec = {"rid": self.rid, **rec}
        with self.captures.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def action(self, name: str, **kw) -> None:
        self.log({"host_action": name, "t_wall": round(time.time(), 3), **kw})
        print(f"  [host] {name} {kw if kw else ''}", flush=True)

    def docker(self, *args, check=True):
        started = time.monotonic()
        r = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
        took = round(time.monotonic() - started, 3)
        if args[0] in ("pause", "unpause", "restart", "start", "network"):
            self.action("docker " + " ".join(args), rc=r.returncode, took_s=took)
        if check and r.returncode != 0:
            raise RuntimeError(f"docker {' '.join(args)} failed: {r.stderr.strip()}")
        return r

    # -- server state ---------------------------------------------------------------
    def server_state(self) -> str:
        return self.docker("inspect", "-f", "{{.State.Status}} paused={{.State.Paused}}", SERVER).stdout.strip()

    def server_networks(self) -> list[str]:
        out = self.docker("inspect", "-f", "{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}", SERVER).stdout
        return [n for n in out.split() if n]

    def wait_healthy(self, timeout=90.0) -> float:
        import urllib.request
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            try:
                with urllib.request.urlopen(f"{HOST_URL}/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("dev server not healthy within timeout")
        recs = self.run_probe("select1", "innet" if self.in_network_ready() else "host", variant="healthcheck")
        ok = any(r.get("step") == "select1" and r.get("call") == "fetchone" and r.get("outcome") == "ok" for r in recs)
        if not ok:
            raise RuntimeError("SELECT 1 probe failed after health 200")
        downtime = round(time.monotonic() - started, 2)
        self.action("healthy", waited_s=downtime)
        return downtime

    def in_network_ready(self) -> bool:
        return NETWORK in self.server_networks()

    def restore_server(self) -> None:
        self.docker("unpause", SERVER, check=False)
        self.docker("start", SERVER, check=False)
        self.wait_healthy()

    # -- probes ---------------------------------------------------------------------
    def run_probe(self, name, where, *, variant=None, repeat=0, url=None, marker="", marker2="",
                  mode="", sleep=0.0, timeout=None, interactive=None, wall=PROBE_WALL_TIMEOUT):
        """Run one probe to completion. `interactive(session)` may drive READY/SENT/GO."""
        url = url or (IN_NET_URL if where == "innet" else HOST_URL)
        pargs = ["probe", name, "--url", url, "--where", where, "--variant", variant or name,
                 "--repeat", str(repeat), "--marker", marker, "--marker2", marker2,
                 "--mode", mode, "--sleep", str(sleep)]
        if timeout is not None:
            pargs += ["--timeout", str(timeout)]
        env_pairs = {"DATABASE_URL": url, "TURSO_AUTH_TOKEN": "", "OPENROUTER_API_KEY": "spike",
                     "ADMIN_TOKEN": "spike", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        cname = f"prd018-probe-{uuid.uuid4().hex[:8]}"
        if where == "innet":
            cmd = ["docker", "run", "-i", "--rm", "--name", cname, "--network", NETWORK,
                   "--mount", f"type=bind,source={REPO / 'app'},target=/work/app,readonly",
                   "--mount", f"type=bind,source={REPO / '.agents' / 'spikes'},target=/work/spike,readonly",
                   "-w", "/tmp", "-e", "PYTHONPATH=/work"]
            for k, v in env_pairs.items():
                cmd += ["-e", f"{k}={v}"]
            cmd += [IMAGE, "python", "/work/spike/PRD-018-driver-failure-surface.py", *pargs]
            popen_kw = {}
        else:
            cmd = [sys.executable, str(SELF), *pargs]
            env = {**os.environ, **env_pairs, "PYTHONPATH": str(REPO)}
            popen_kw = {"cwd": str(self.out), "env": env}
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", bufsize=1, **popen_kw)
        session = Session(self, proc, cname if where == "innet" else None, where, wall)
        try:
            if interactive:
                interactive(session)
            session.finish()
        finally:
            session.cleanup()
        return session.recs


class Session:
    def __init__(self, host, proc, cname, where, wall):
        self.host, self.proc, self.cname, self.where = host, proc, cname, where
        self.recs: list[dict] = []
        self.deadline = time.monotonic() + wall
        self.q: queue.Queue = queue.Queue()
        self.recs_since_sent = 0
        self.sent = False
        self.hung = False
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.q.put(line.rstrip("\n"))
        self.q.put(None)

    def _handle(self, line: str) -> str | None:
        if line.startswith("REC "):
            rec = json.loads(line[4:])
            self.recs.append(rec)
            self.host.log(rec)
            if self.sent:
                self.recs_since_sent += 1
            return None
        if line.split(" ")[0] in ("READY", "SENT", "DONE", "SLEEP"):
            return line.split(" ")[0]
        if line.strip():
            self.host.log({"probe_output": line[:300], "where": self.where})
        return None

    def wait(self, token: str, timeout: float | None = None) -> bool:
        """Consume lines until `token` arrives. False on EOF or timeout (probe hung)."""
        limit = time.monotonic() + timeout if timeout else self.deadline
        limit = min(limit, self.deadline)
        while True:
            left = limit - time.monotonic()
            if left <= 0:
                return False
            try:
                line = self.q.get(timeout=min(left, 1.0))
            except queue.Empty:
                continue
            if line is None:
                return False
            if self._handle(line) == token:
                if token == "SENT":
                    self.sent = True
                return True

    def drain(self) -> None:
        while True:
            try:
                line = self.q.get_nowait()
            except queue.Empty:
                return
            if line is not None:
                self._handle(line)

    def go(self):
        self.proc.stdin.write("GO\n")
        self.proc.stdin.flush()

    def finish(self):
        if not self.wait("DONE"):
            try:
                self.proc.wait(timeout=5)  # EOF without DONE = crashed, not hung
            except Exception:  # noqa: BLE001
                pass
            if self.proc.poll() is None:
                self.hung = True
                self.host.log({"probe_hung": True, "where": self.where,
                               "note": "wall guard hit; probe killed", "recs_so_far": len(self.recs)})
                print("  [host] PROBE HUNG -> killing", flush=True)
        self.drain()

    def cleanup(self):
        if self.proc.poll() is None:
            if self.cname:
                subprocess.run(["docker", "kill", self.cname], capture_output=True)
            self.proc.kill()
        try:
            self.proc.wait(timeout=20)
        except Exception:  # noqa: BLE001
            pass
        self.drain()


# -------------------------------------------------------------------------------------
# host commands
# -------------------------------------------------------------------------------------
def cmd_preflight(h: Host, ns):
    existed = subprocess.run(["docker", "network", "inspect", NETWORK], capture_output=True).returncode == 0
    nets = h.server_networks()
    state = {"network_existed": existed, "server_was_on_network": NETWORK in nets, "server_networks": nets}
    if not h.state_file.exists():  # keep the FIRST recorded state across re-runs
        h.state_file.write_text(json.dumps(state), encoding="utf-8")
    if not existed:
        h.docker("network", "create", NETWORK)
    if NETWORK not in h.server_networks():
        h.docker("network", "connect", NETWORK, SERVER)
    print("server:", h.server_state(), "networks:", h.server_networks(), "state:", state)
    h.wait_healthy()
    h.run_probe("setup", "innet", variant="setup")
    print("preflight ok")


def new_marker() -> str:
    return uuid.uuid4().hex


def landed(h: Host, marker: str, variant: str, repeat: int, where="innet") -> bool:
    recs = h.run_probe("landed", where, variant=variant + "-landed", repeat=repeat, marker=marker)
    for r in recs:
        if r.get("step") == "landed" and r.get("call") == "result":
            h.action("landed", variant=variant, repeat=repeat, marker=marker, landed=r["landed"])
            return r["landed"]
    h.action("landed-unknown", variant=variant, repeat=repeat, marker=marker)
    return None


def loop(variants, only):
    return [v for v in variants if only is None or v == only]


def group_smoke(h, ns):
    m = new_marker()
    landed(h, m, "smoke-never", 0)
    m2 = new_marker()
    h.run_probe("insert-commit", "innet", variant="smoke-control", marker=m2)
    landed(h, m2, "smoke-control", 0)


def group_refused(h, ns):
    for where in ([ns.where] if ns.where else ["innet", "host"]):
        for i in range(1, REPEATS + 1):
            print(f"F1 refused {where} #{i}")
            h.run_probe("connfault", where, variant="F1-refused", repeat=i, url=REFUSED_URL, wall=120)


def group_connect_timeout(h, ns):
    urls = UNROUTABLE_URLS[ns.url_index:ns.url_index + 1]
    for where in ([ns.where] if ns.where else ["innet", "host"]):
        for i in range(1, ns.repeats + 1):
            for url in urls:
                print(f"F2 connect-timeout {where} {url} #{i}")
                h.run_probe("connfault", where, variant=f"F2-connect-timeout[{url}]", repeat=i, url=url, wall=280)


def group_pause(h, ns):
    try:
        for v in loop(["a", "b", "c", "d"], ns.variant):
            for i in range(1, REPEATS + 1):
                m = new_marker()
                mode = "commit" if v == "d" else "insert"
                print(f"F3{v} #{i} marker={m}")

                def drive(s, v=v):
                    if not s.wait("READY", 90):
                        return
                    h.docker("pause", SERVER)
                    s.go()
                    s.wait("SENT", 30)
                    if v == "a":
                        h.action("hold", seconds=PAUSE_HOLD_LONG)
                        time.sleep(PAUSE_HOLD_LONG)
                        s.drain()
                        h.action("after-hold", probe_returned=s.recs_since_sent > 0, recs_since_sent=s.recs_since_sent)
                        h.docker("unpause", SERVER)
                    elif v == "b":
                        h.action("hold", seconds=PAUSE_HOLD_SHORT)
                        time.sleep(PAUSE_HOLD_SHORT)
                        s.drain()
                        h.action("after-hold", probe_returned=s.recs_since_sent > 0, recs_since_sent=s.recs_since_sent)
                        h.docker("unpause", SERVER)
                    else:  # c, d: restart while paused
                        h.action("hold", seconds=3)
                        time.sleep(3)
                        s.drain()
                        h.action("after-hold", probe_returned=s.recs_since_sent > 0, recs_since_sent=s.recs_since_sent)
                        h.docker("restart", "-t", "0", SERVER)

                h.run_probe("pause", "innet", variant=f"F3{v}", repeat=i, marker=m, mode=mode, interactive=drive,
                            wall=240)
                h.restore_server()
                landed(h, m, f"F3{v}", i)
    finally:
        h.restore_server()
        print("server:", h.server_state())


def group_restart(h, ns):
    try:
        for v in loop(["a", "b", "c"], ns.variant):
            for i in range(1, REPEATS + 1):
                m, m2 = new_marker(), new_marker()
                print(f"F4{v} #{i} markers={m},{m2}")

                def drive(s):
                    if not s.wait("READY", 90):
                        return
                    h.docker("restart", "-t", "0", SERVER)
                    h.wait_healthy()
                    s.go()
                    s.wait("SENT", 30)

                h.run_probe("restart", "innet", variant=f"F4{v}", repeat=i, marker=m, marker2=m2, mode=v,
                            interactive=drive, wall=200)
                landed(h, m, f"F4{v}-m1", i)
                if v == "a":
                    landed(h, m2, f"F4{v}-m2", i)
    finally:
        h.restore_server()
        print("server:", h.server_state())


def group_idle(h, ns):
    plan = {"a": IDLE_SECONDS, "b": IDLE_SECONDS, "c": IDLE_SECONDS, "d": IDLE_SECONDS, "e": IDLE_SECONDS,
            "control": IDLE_CONTROL_SECONDS}
    for v in loop(list(plan), ns.variant):
        for i in range(1, REPEATS + 1):
            m = new_marker()
            print(f"F5{v} #{i} marker={m}")
            h.run_probe("idle", "innet", variant=f"F5{v}", repeat=i, marker=m, mode=v, sleep=plan[v], wall=120)
            if v in ("b", "c"):
                landed(h, m, f"F5{v}", i)


def group_q1(h, ns):
    for i in range(1, REPEATS + 1):
        # Q1a: abandon by process exit
        m = new_marker()
        print(f"Q1a #{i} marker={m}")
        h.run_probe("q1", "innet", variant="Q1a", repeat=i, marker=m, mode="a")
        landed(h, m, "Q1a-immediate", i)
        time.sleep(15)
        landed(h, m, "Q1a-after15s", i)
        # Q1b: abandon while the client is alive
        m = new_marker()
        print(f"Q1b #{i} marker={m}")

        def drive(s, m=m):
            if not s.wait("READY", 60):
                return
            landed(h, m, "Q1b-while-alive", i)
            s.go()

        h.run_probe("q1", "innet", variant="Q1b", repeat=i, marker=m, mode="b", interactive=drive)
        landed(h, m, "Q1b-after-exit", i)
        time.sleep(15)
        landed(h, m, "Q1b-after15s", i)
        # Q1c: positive control
        m = new_marker()
        print(f"Q1c #{i} marker={m}")
        h.run_probe("insert-commit", "innet", variant="Q1c", repeat=i, marker=m)
        landed(h, m, "Q1c", i)


def group_q2(h, ns):
    for i in range(1, REPEATS + 1):
        h.run_probe("q2", "innet", variant="Q2-healthy", repeat=i)


def group_q3(h, ns):
    for v in loop(["a", "b", "c"], ns.variant):
        for i in range(1, REPEATS + 1):
            ma, mb = new_marker(), new_marker()
            print(f"Q3{v} #{i} ma={ma} mb={mb}")
            timeout = 1.0 if v == "c" else None
            if v in ("a", "c"):
                def drive(s):
                    if not s.wait("READY", 60):
                        return
                    h.run_probe("q3b", "innet", variant=f"Q3{v}-writer", repeat=i, marker=mb, timeout=timeout, wall=120)
                    s.go()

                h.run_probe("q3a", "innet", variant=f"Q3{v}-holder", repeat=i, marker=ma, mode="a", interactive=drive)
            else:
                h.run_probe("q3a", "innet", variant="Q3b-holder", repeat=i, marker=ma, mode="b")
                h.run_probe("q3b", "innet", variant="Q3b-writer", repeat=i, marker=mb, wall=120)
            landed(h, mb, f"Q3{v}-writer", i)
            landed(h, ma, f"Q3{v}-holder", i)


def cmd_run(h: Host, ns):
    groups = {"smoke": group_smoke, "refused": group_refused, "connect-timeout": group_connect_timeout,
              "pause": group_pause, "restart": group_restart, "idle": group_idle,
              "q1": group_q1, "q2": group_q2, "q3": group_q3}
    docker_touching = ns.group in ("pause", "restart", "q3")
    try:
        groups[ns.group](h, ns)
    finally:
        if docker_touching:
            h.restore_server()
    print("server:", h.server_state())


def cmd_restore(h: Host, ns):
    h.restore_server()
    h.run_probe("teardown", "innet" if h.in_network_ready() else "host", variant="teardown")
    recs = h.run_probe("leftovers", "innet" if h.in_network_ready() else "host", variant="leftovers")
    left = [r.get("leftover_tables") for r in recs if r.get("step") == "leftovers" and r.get("call") == "result"]
    print("leftover prd018_spike_% tables:", left)
    h.run_probe("select1", "innet" if h.in_network_ready() else "host", variant="final-in-net")
    h.run_probe("select1", "host", variant="final-host")
    if h.state_file.exists():
        st = json.loads(h.state_file.read_text(encoding="utf-8"))
        if not st["server_was_on_network"] and NETWORK in h.server_networks():
            h.docker("network", "disconnect", NETWORK, SERVER)
        if not st["network_existed"]:
            h.docker("network", "rm", NETWORK, check=False)
    print("state:", h.server_state())
    print("networks:", h.server_networks())
    print("docker networks:", h.docker("network", "ls", "--format", "{{.Name}}").stdout.split())


# =====================================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="role", required=True)

    pr = sub.add_parser("probe", help="(internal) one probe in a fresh process")
    pr.add_argument("name")
    pr.add_argument("--url", default=HOST_URL)
    pr.add_argument("--where", default="host")
    pr.add_argument("--variant", default="")
    pr.add_argument("--repeat", type=int, default=0)
    pr.add_argument("--marker", default="")
    pr.add_argument("--marker2", default="")
    pr.add_argument("--mode", default="")
    pr.add_argument("--sleep", type=float, default=0.0)
    pr.add_argument("--timeout", type=float, default=None)

    ho = sub.add_parser("host", help="orchestrator (run from the repo root with .venv/Scripts/python)")
    ho.add_argument("action", choices=["preflight", "run", "restore"])
    ho.add_argument("group", nargs="?", choices=["smoke", "refused", "connect-timeout", "pause", "restart",
                                                  "idle", "q1", "q2", "q3"])
    ho.add_argument("--out", required=True)
    ho.add_argument("--where", choices=["innet", "host"])
    ho.add_argument("--variant")
    ho.add_argument("--url-index", type=int, default=0)
    ho.add_argument("--repeats", type=int, default=REPEATS)
    ns = ap.parse_args()

    if ns.role == "probe":
        Probe(ns).run()
        return
    h = Host(Path(ns.out))
    if ns.action == "preflight":
        cmd_preflight(h, ns)
    elif ns.action == "restore":
        cmd_restore(h, ns)
    else:
        if not ns.group:
            ap.error("host run needs a group")
        cmd_run(h, ns)


if __name__ == "__main__":
    main()
