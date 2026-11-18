---
story: STORY-004
prd: PRD-019
slug: caddy-balancer-spike
title: Spike — verify Caddy cookie policy, health, error and retry behaviour against a pinned Caddy
type: NEW_CAPABILITY
complexity: small
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Caddy balancer spike

## Summary

A measurement story, not a feature. The implementer downloads an official Caddy 2.x release into the session scratchpad, runs one `caddy run` in front of two throwaway Python backends, and records verbatim evidence for six questions (a-f below). Output: the report's Findings + "Inputs for later stories", and PRD amendments (F3, Section 8, Section 15 "Not verified in code", Risk 6). No application code, no tests, no committed binary or script.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-004-caddy-balancer-spike.md` (AC text lives there)
- PRD sections used: Section 7 F3 (`PRD.md:189-218`), Section 8 (`:241-251`), Risk 6 (`:352`), Section 15 "Not verified" (`:391-394`), D1, D6, D9 (`:360-366`)
- Systems affected: `.agents/PRDs/PRD-019-multi-instance-deployment/PRD.md`, story + index, report. Shipped `Caddyfile` untouched (the new `deploy/lb/Caddyfile` is STORY-005).

## Design Decisions (binding, from the orchestrator)

1. Caddy is not installed. Download an official Caddy 2.x Windows amd64 zip from github.com/caddyserver/caddy releases into the scratchpad, verify SHA-256 against the release's `caddy_<ver>_checksums.txt`, never commit it. Pick the latest stable 2.x minor release at least two weeks old (today 2026-11-17; check the release `published_at`, skip pre-releases/betas). Record: version, Linux amd64 tarball URL + SHA-256 (STORY-006 CI), and the `caddy:<version>` image digest (`docker buildx imagetools inspect caddy:<ver>` or `docker manifest inspect`; fall back to `docker pull` + `docker inspect --format '{{index .RepoDigests 0}}'`). Docker 29.7.2 is installed locally. Record the multi-arch index digest (what compose should pin).
2. Experiments are throwaway scripts in the scratchpad: two Python HTTP backends (free ports; modes: normal 200 with a body naming the backend, `503` + `Retry-After: 7`, hang, drop connection after reading a POST body, `/ready` failing) and one `caddy run` with a Caddyfile shaped like F3 and localhost upstreams. Every experiment records verbatim status line, headers, and the `Set-Cookie` line.
3. Report answers (a)-(f), each with evidence, listed below.
4. Deliverables: report Findings, PRD amendments, "Inputs for later stories". Commit type `docs`/`chore`.
5. Bounded: kill every process at the end (`Popen.kill` + wait, or `taskkill /F /T`); verify with `tasklist`/port check that no caddy or python backend is left.

## Skills In Use

None (`skills: []`; `.agents/skills/` only has `frontend-design`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Report/PRD style | `.agents/reports/PRD-019-multi-instance-deployment/STORY-003-image-healthcheck.report.md` | report layout, SHA handling |
| Current in-container Caddyfile | `Caddyfile:1-9` (`:{$PORT}`, `reverse_proxy localhost:{$BACKEND_INTERNAL_PORT}`) | env-placeholder syntax already used in this repo |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/PRDs/PRD-019-multi-instance-deployment/PRD.md` | UPDATE | F3 corrected where reality differs; Section 8 pin (version, digest); Section 15 verified/corrected; Risk 6 status |
| `.agents/reports/PRD-019-multi-instance-deployment/STORY-004-caddy-balancer-spike.report.md` | CREATE | Findings + Inputs for later stories |
| `.agents/stories/PRD-019-multi-instance-deployment/STORY-005..007,010*.md` | UPDATE (only if needed) | `Orchestrator decision` notes where a finding changes their ACs |
| scratchpad only | CREATE | `caddy/` (zip, extracted binary), `backend.py`, `run_spike.py`, Caddyfiles, `results.txt`. Never staged |

## Tasks

### Task 1: Pick, download, verify and pin Caddy
- Query `https://api.github.com/repos/caddyserver/caddy/releases` (curl/urllib; `gh api` also works). Take the newest non-prerelease `v2.x.y` with `published_at` <= 2026-11-03. Prefer the highest patch of that minor.
- Download `caddy_<v>_windows_amd64.zip`, `caddy_<v>_linux_amd64.tar.gz` and `caddy_<v>_checksums.txt` each into its own fresh scratchpad dir (downloaded files are untrusted; do not run scripts from those dirs). Verify both SHA-256s with `sha256sum`/`Get-FileHash`. Extract only the zip, run `caddy version` and confirm it equals `<v>`.
- Get the image digest (see Design Decision 1). Confirm `caddy:<minor>` tag resolution and that the digest's amd64 manifest runs `caddy version` equal to `<v>` only if cheap (`docker run --rm caddy@sha256:... caddy version`).
- Record version, both URLs, both SHA-256, digest, binary size.
- **Validate**: `caddy version` output pasted in the report.

### Task 2: Write the throwaway harness (scratchpad)
- `backend.py <port> <name>`: `ThreadingHTTPServer`; reply `200` with body `<name> <method> <path>` and header `X-Backend: <name>`; a control endpoint `POST /__mode` (not proxied in tests, called directly on the backend port) sets mode: `ok`, `s503` (`503` + `Retry-After: 7` + a fixed body), `hang` (sleep > 20 s), `drop` (read the whole POST body, then close the socket with no response, e.g. `self.connection.shutdown`/`close`; also log each received request to a list), `notready` (`/ready` returns 503, everything else 200). Each backend exposes `GET /__count` returning how many non-control requests it received, so replay is measurable.
- `run_spike.py`: picks two free backend ports and a free Caddy port, writes the Caddyfile, starts backends and `caddy run --config <file> --adapter caddyfile` via `Popen`, waits with a deadline loop on the Caddy port, runs the experiments below with `urllib`/raw `http.client` (raw sockets for exact header lines; `http.client` lowercases nothing, but print `resp.getheaders()` and the raw `Set-Cookie`), prints everything to `results.txt`, and kills all children in `finally`. Use a short `health_interval` (1s) and `fail_duration` in an experiment variant for speed, and also run the shipped values (5s/30s) at least once for (a).
- Base Caddyfile: copy of F3 with `harness-a:{$PORT} harness-b:{$PORT}` replaced by `127.0.0.1:<a> 127.0.0.1:<b>`, secret from env `LB_COOKIE_SECRET=spike-secret`, `admin off` not required but set global `{ admin localhost:<free> }` to avoid colliding with a developer's Caddy on :2019 (note: this is a spike detail; the shipped file's admin port is a point to record for STORY-007, since parallel Caddy processes in tests would otherwise fight over :2019).
- **Validate**: first request through Caddy returns `X-Backend`.

### Task 3: Experiments (each records verbatim output)
- **(a) Cookie.** Request without cookie: record `Set-Cookie` verbatim (name, Path, HttpOnly, SameSite, Secure, Max-Age/Expires, value shape: length, charset, whether it equals the upstream address or an HMAC; run twice with two secrets and with no secret to show the value changes). Replay with the cookie: 10 requests all to the same backend (`X-Backend`). Then pinned upstream **unhealthy** (`/ready` -> 503, wait out `health_interval`, confirm via `caddy` logs or a request): record which backend answers and whether a new `Set-Cookie` is sent (re-set) and its value; then bring it back ready and record whether the client stays on the new one. Then pinned upstream **dead** (kill that backend process, no health wait, i.e. passive path) and again after the active check has marked it down: record the response status, whether it fell back within `lb_try_duration`, and `Set-Cookie`. Also check whether an unknown/garbage cookie value is accepted and re-set.
- **(b) No healthy upstream.** Both `/ready` failing, wait one interval; request `/query` (POST) and `/v1/chat/completions` and `GET /`: record the status Caddy generates (502 vs 503), how long it took (expect up to `lb_try_duration` 5s), and that the `handle_errors 502 503` block answers with the fixed body + `Retry-After: 10` (verbatim). Test the `@v1` matcher inside `handle_errors` (does `path` see the original `/v1/*` path there?). Also record both backends dead (dial failure) status for the same block. If `handle_errors 502 503 { ... }` is rejected, record the accepted syntax.
- **(c) Proxied 503 passthrough.** Backend in `s503` (still `/ready`-healthy): record the status line, headers and body through Caddy and compare byte for byte with the direct response (diff the raw bytes). Confirm `handle_errors` did not fire (no `Retry-After: 10`, body unchanged) and the backend stays in rotation (still selected afterwards; no `unhealthy_status` configured).
- **(d) Retry semantics.** With `lb_try_duration 5s` and no `retry_match`: (1) POST to a backend in `drop` mode, other backend ok: record the response and per-backend `__count` (replay = other backend count increased); repeat with a GET to show the GET behaviour for contrast; (2) dial failure: kill one backend, send POST with the cookie pinned to it (and without) and with active health not yet aware (use a long interval variant): expect retry to the live one; record counts. Record the `hang` case result versus `response_header_timeout` using a shortened timeout variant (e.g. 3s) to show 502/504 and no replay.
- **(e) Directives.** Run `caddy validate --adapter caddyfile --config <F3 file>` and `caddy adapt` on the exact F3 text (with env set), and save the JSON. Confirm each of `lb_try_duration`, `health_uri`, `health_interval`, `health_timeout`, `health_status`, `fail_duration`, `transport http { dial_timeout response_header_timeout }`, `stream_close_delay`, `handle_errors 502 503` appears in the adapted JSON under the expected key (e.g. `stream_close_delay`, `load_balancing.try_duration`, `health_checks.active`). Record warnings (e.g. Caddyfile formatting). Also `caddy validate` with `LB_COOKIE_SECRET` unset: record whether an empty secret is an error, since STORY-005 requires `${LB_COOKIE_SECRET:?}` only in compose. Note any directive that has to be renamed in the PRD.
- **(f) Upstream override.** Try in this order, each with `caddy adapt` and (for the winner) a live request: (1) `reverse_proxy {$LB_UPSTREAMS:harness-a:{$PORT} harness-b:{$PORT}} {`; (2) a quoted default; (3) one env per upstream `{$LB_UPSTREAM_A:harness-a:{$PORT}} {$LB_UPSTREAM_B:harness-b:{$PORT}}`; (4) one env holding both upstreams, defaulting only through compose (`LB_UPSTREAMS: harness-a:${PORT} harness-b:${PORT}` in the lb service). Record which parse (nested `{$..}` in a default and spaces in a default are the risk: env substitution is textual and ends at the first `}`). Check, for the winner, that unset env yields the shipped upstreams in the adapted JSON, and that the env-override yields localhost ones. If none works cleanly, propose the one-line textual substitution (replace exactly the `reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {` line; the test asserts that the rest is byte-identical and exactly one line changed) and say which STORY-007 helper does it.
- **(g) Optional, cheap only:** whether `ChatState._token` is in the disk-state pickle (`PRD.md:394`): `grep` Reflex `StateManagerDisk`/`pickle` in `.venv/Lib/site-packages/reflex/state.py`/`istate/manager`; otherwise write "not checked".
- **Validate**: `results.txt` exists in the scratchpad and every claim in the report quotes it.

### Task 4: Teardown
- Kill Caddy and both backends; run `tasklist | findstr /i "caddy python"` (or the Python equivalent) and confirm only the session's own processes remain; confirm the chosen ports are free. Note: the extracted binary and zip stay in the scratchpad.
- **Validate**: `git status --short` shows no binary, zip or script staged or untracked outside the intended files.

### Task 5: Write the report
- `.agents/reports/PRD-019-multi-instance-deployment/STORY-004-caddy-balancer-spike.report.md` (copy the STORY-003 report's section layout). Findings: one block per question (a)-(f): answer, verbatim evidence (status line, headers, `Set-Cookie`, counts). Then "Inputs for later stories": STORY-005 (final F3 text, `handle_errors` syntax, cookie name, image digest, shipped-file override mechanism), STORY-006 (version, Linux URL + SHA-256, Windows asset name, `caddy version` assertion string, admin-port note), STORY-007 (upstream override mechanism, start/stop helper hints for Windows `Popen.kill` and Linux, `caddy run --config ... --adapter caddyfile`, readiness wait loop), STORY-010 (cookie re-set behaviour; what the user sees after failover). Also helper idea if cheap.

### Task 6: Amend the PRD (only where evidence supports it)
- F3 (`PRD.md:192-218`): correct directive names/syntax and the sentence "`handle_errors` only fires for errors the balancer generates itself" if (b)/(c) differ; document the override mechanism and the `admin` port point.
- Section 8 (`:247-248`): replace `caddy:2.<minor>` with the exact version and digest; mention the CI binary SHA-256 lives in STORY-006's workflow.
- Section 15 "Not verified" (`:391-394`): move verified items to a "Verified (STORY-004, Caddy x.y.z)" list with the measured result; items not verified (e.g. `_token`) stay with an explicit "not checked".
- Risk 6 (`:352`): mark "verified in STORY-004", noting any difference. If a finding contradicts D1/D9 or an AC of a later story, add an `Orchestrator decision` note in that story file and tell the orchestrator in the final message instead of deciding.
- **Validate**: `git diff --stat` touches only the PRD, report, and any story notes.

## End-to-End Tests

- [ ] The experiment run in Task 3 is itself the E2E: real `caddy run` + two real backends, verbatim output in `results.txt`.
- [ ] `caddy validate` on the exact amended F3 text passes with the env set.
- [ ] No test files or application code changed.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-019   # errors: none
git status --short   # only PRD.md, the report, story/index files
```
No pytest run (no code or tests touched; full suite is GitHub CI).

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Evidence |
|----|---------|----------|
| AC1 version + digest + URLs/SHA | Task 1, Task 5 | report Findings: pin block |
| AC2 cookie attributes/value/unhealthy re-set | Task 3(a) | `results.txt` verbatim in report |
| AC3 no-healthy-upstream status, `handle_errors`, 503 passthrough | Task 3(b), 3(c) | report (b), (c) |
| AC4 POST replay vs dial retry | Task 3(d) | report (d) with per-backend counts |
| AC5 directives accepted + override mechanism + PRD amended | Task 3(e), 3(f), Task 6 | report (e), (f); PRD diff |

Plus: processes killed (Task 4), nothing committed that is not text.

## Risks

- Latest release under 2 weeks old or a beta: take the previous minor/patch and say why.
- Cookie may not be re-set on fallback: record exactly (STORY-010 depends on it).
- `lb_try_duration` makes "no healthy upstream" take about 5 s: record it (tests need a longer timeout).
- Parallel Caddy processes share admin `:2019`: note for STORY-007.
- Windows: verify no caddy/python child survives (`tasklist`).
