---
story: STORY-004
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-004-caddy-balancer-spike.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: 2e0ac34
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-004: Caddy balancer spike

**Commit**: `2e0ac34`

## Summary

A measurement story: no application code, no tests, no committed binary or script. Official Caddy 2.11.7 (Windows amd64) was downloaded to the session scratchpad and run (`caddy run --adapter caddyfile`) in front of two throwaway Python backends. Every claim below was measured on that binary; raw output is in the scratchpad `caddy_spike/work/results.txt` (not committed). Most of F3 holds. Three findings contradict or sharpen the PRD (marked **CONTRADICTS PRD** below): `handle_errors` also fires for a request that was already sent and failed mid-flight (and the `/v1` body then wrongly says it was not sent), a header timeout yields an empty 504 outside `handle_errors`, and the in-file upstream override suggested in the story (`{$LB_UPSTREAMS:...}`) does not parse. The cookie has no `Secure`, and an unset secret is silently accepted.

## Validation Results

| Check | Result |
|-------|--------|
| Experiments (a)-(f) run against real `caddy run` + two real backends | all run, evidence below |
| `caddy validate` / `caddy adapt` on the exact F3 text (env set) | rc 0, every directive present in the adapted JSON |
| Backend import | OK (no app code touched) |
| Tests | none written or run (spike) |
| Full suite | GitHub CI on push (user decision) |
| Processes | all caddy and backend processes killed; `tasklist` shows no caddy and no python left |

## Pin block (AC1)

| Item | Value |
|---|---|
| Version | `v2.11.7`, published 2026-10-03 (newest stable at least 2 weeks old; `v2.11.8` is 2026-11-04 and `v2.11.9` 2026-11-05, so skipped; 2.11.0 betas are prereleases) |
| `caddy version` (Windows binary) | `v2.11.7 h1:yj0Y4fYZGPkSvibBJ1sTWE33xC0fxztVyXEW5iIdUT4=` (same string from `docker run caddy@sha256:36c2... caddy version`) |
| Windows asset | `https://github.com/caddyserver/caddy/releases/download/v2.11.7/caddy_2.11.7_windows_amd64.zip`, SHA-256 `0a1edc0b799512051c57071ce0e798d3f2cf67dc98171366f1d2b326072e3b06`, SHA-512 `c308154504e53755958ffc62d8a2657ab17eefd6dd25c45dbb2c3d93d29519971f77ca652f7d0f2bcb7f980b9ba3822478865e29969d0272d7613550a43152b1`; extracted `caddy.exe` 53,159,936 bytes |
| Linux asset | `https://github.com/caddyserver/caddy/releases/download/v2.11.7/caddy_2.11.7_linux_amd64.tar.gz`, SHA-256 `727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b`, SHA-512 `a7a433a1b133efc3c8d10eb0b99d52a24b5ef5c322dc77f5282182b1c0402139ab83f3a99f0c52409df77d20123fb0b523edad8a66d8f5e49136197bf61ef0e7` |
| Checksums file | `caddy_2.11.7_checksums.txt` lists **SHA-512** (128 hex), not SHA-256. Both archives' SHA-512 match it. The SHA-256 values above were computed locally |
| Image | `caddy:2.11.7` index digest `sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e` (OCI index; linux/amd64 manifest `sha256:04913b1da43339a40ad1ea87827d70a576ac5aa6cf674c6e24fdca675887533a`, alpine 3.23 based). Compose should pin `caddy:2.11.7@sha256:36c24ad9...` |

## Findings

### (a) Cookie policy

`lb_policy cookie harness_lb <secret>` sets, verbatim:

```
Set-Cookie: harness_lb=e199842ac3e3f561dab2727806c89271658811be247d8735b7f744e7952a8893; Path=/; HttpOnly; SameSite=Lax
```

- Attributes: `Path=/; HttpOnly; SameSite=Lax`. No `Secure`, no `Max-Age`/`Expires` (a session cookie). The PRD assumed no attributes; docs/STORY-010 must state that `Secure` is absent.
- Value: 64 lowercase hex chars, an HMAC-SHA-256 of the upstream address. It does not reveal the address. Three secrets (`spike-secret`, `other-secret`, none) gave three different values. An empty/unset secret is **not an error** (`caddy validate` rc 0; adapt drops the `secret` key): the cookie is then an unkeyed hash that anyone can compute to pin themselves. STORY-005's `${LB_COOKIE_SECRET:?}` in compose is the only guard.
- Cookie-less requests are spread randomly (second request of the same client landed on the other backend). A valid cookie is replayed 10/10 to the same backend and carries **no** new `Set-Cookie`.
- Garbage cookie (`harness_lb=garbage`), 64 zeros, and the plain upstream address `127.0.0.1:<port>` are all ignored: a random backend answers and a fresh `Set-Cookie` is sent.
- Pinned upstream unhealthy (`/ready` 503, interval 1 s): after the next check, the old cookie is answered by the other backend with a **new `Set-Cookie`** for it (re-set confirmed). With that new cookie the client stays on the new backend, also after the first one recovers (`NEW cookie after recovery: backend A`). A client that keeps sending the OLD cookie goes back to the original backend once it is healthy again (it only moves permanently if it stores the new `Set-Cookie`, which browsers do).
- With the shipped values (interval 5 s): failover after exactly 5.0 s ("first failover after 5.0s -> A", new cookie set).
- Pinned upstream dead, active check not yet aware (interval 60 s): the dial fails, Caddy retries within `lb_try_duration` and answers 200 from the other backend after **0.25 s**, with a new `Set-Cookie`. After the active check marked it down: 200 from the other, re-set, 0.00 s. POST behaves the same on dial failure (see d2).
- Quirk: when every backend is dead (both dial failures), the *503 error response* itself carried two `Set-Cookie: harness_lb=...` lines (one per upstream tried). A client can be pinned to a dead upstream by an error response; harmless because a cookie that points at an unhealthy/dead upstream falls back as above.

### (b) No healthy upstream

- Both `/ready` 503, marked down: `POST /query`, `POST /v1/chat/completions`, `GET /`, `GET /v1/models` all returned **503** (not 502) after **5.01 s** (`lb_try_duration`; test timeouts need more than 5 s).
- Both backends dead (dial failure), active check unaware and aware: 503 after 5.01 s, same body.
- Verbatim, `/query`:

```
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 10
Server: Caddy
Content-Length: 32
{"detail":"Service unavailable"}
```

- `/v1/chat/completions` and `/v1/models`: same headers, body `{"error":{"message":"Service unavailable; the request was not sent to the model.","type":"api_error","param":null,"code":"service_unavailable"}}` (144 bytes). The `@v1 path /v1/*` matcher inside `handle_errors` sees the original request path.
- `handle_errors 502 503 { ... }` is accepted as written. Neither backend received a non-`/ready` request (counts 0/0).

### (c) Proxied 503 passthrough

Backend in `s503` mode (`503`, `Retry-After: 7`, JSON body), `/ready` healthy. Direct vs through Caddy: same status, body bytes equal (`True`), `Retry-After: 7` kept, `Content-Type` and `Server` kept. Caddy added only `Via: 1.1 Caddy`, `Connection: close` (client asked for it) and the `Set-Cookie`. `handle_errors` did **not** fire (no `Retry-After: 10`, body is the backend's). After the 503s the backend stayed in rotation: 30 cookie-less GETs split A 20 / B 10 (both selected), and a cookie-pinned client kept hitting its pinned backend 5/5. No `down`/`unhealthy` line in the Caddy log. D9's passthrough claim holds.

### (d) Retry semantics (`lb_try_duration 5s`, no `retry_match`)

- **POST, backend drops the connection after reading the body**: not replayed. Response 503 in 0.00 s (the `handle_errors` body above); the dropping backend got 1 request, the other **0**. **CONTRADICTS PRD** in two ways: (1) F3 says `handle_errors` fires only for errors "the balancer generates itself"; it also fires for a request already sent when the upstream breaks the connection (Caddy raises 502, rewritten to 503 + `Retry-After: 10` + fixed body). (2) For `/v1` the fixed body says "the request was not sent to the model", which is false here (it was sent, and may have been charged). Orchestrator decision needed (see STORY-005 note).
- **GET, same drop**: retried. Caddy tried the pinned backend twice then the other: counts A 2, B 1, final 200 from B, new `Set-Cookie`, 0.25 s.
- After one drop, the failing backend left rotation (passive, `fail_duration`): 10 cookie-less POSTs gave 1 failure (503) then 9 x 200, counts A 1 / B 9. So a request that fails mid-flight takes the instance out of rotation for 30 s, and the next 9 were not replays (B total 9).
- **Dial failure** (backend killed, active unaware, `hi=60s`): POST pinned to the dead one answered 200 by the live one in 0.26 s, live count 1 (not replayed because it never reached the dead one; dial errors are retried safely). 10 cookie-less POSTs: 10 x B, no failures.
- **Hang vs `response_header_timeout 3s`**: POST pinned to the hanging backend: **504 Gateway Timeout after 3.00 s**, `Server: Caddy`, `Content-Length: 0`, **no body, no `Retry-After`**; other backend count 0 (no replay). `handle_errors 502 503` does not catch 504. GET: retried on the other backend after 3.25 s (200). **CONTRADICTS PRD** if D9's "balancer's own 503 + Retry-After" is read to include timeouts: a 504 with an empty body reaches the client.

### (e) Directives

`caddy validate` on the exact F3 text with `LB_COOKIE_SECRET` set: rc 0 (it logs failed DNS lookups for `harness-a/b` as info only; validate does not need them to resolve). `caddy adapt` shows each directive under the expected key:

| F3 directive | Adapted JSON |
|---|---|
| `lb_policy cookie harness_lb <s>` | `load_balancing.selection_policy {"name":"harness_lb","policy":"cookie","secret":"spike-secret"}` |
| `lb_try_duration 5s` | `load_balancing.try_duration: 5000000000` |
| `health_uri /ready`, `health_status 200`, `health_interval 5s`, `health_timeout 3s` | `health_checks.active {uri:"/ready", expect_status:200, interval:5e9, timeout:3e9}` |
| `fail_duration 30s` | `health_checks.passive.fail_duration: 30000000000` (no `unhealthy_status` key) |
| `transport http {dial_timeout 3s, response_header_timeout 150s}` | `transport {protocol:"http", dial_timeout:3e9, response_header_timeout:1.5e11}` |
| `stream_close_delay 5m` | `stream_close_delay: 300000000000` |
| `handle_errors 502 503` | `errors.routes[0].match[0].expression: "{http.error.status_code} in [502, 503]"` |

No directive needs renaming. `caddy fmt --diff` reports every line changed only because the spike file had CRLF line endings on Windows (written in text mode); the F3 text itself is already tab-indented. Keep `deploy/lb/Caddyfile` LF-only (`.gitattributes` check is STORY-005's).

### (f) Upstream override

| # | Form | Result |
|---|---|---|
| 1 | `reverse_proxy {$LB_UPSTREAMS:harness-a:{$PORT} harness-b:{$PORT}}` | **fails**: `parsing upstream 'harness-a:{$PORT': invalid start port` (substitution ends at the first `}`) |
| 2 | quoted default `"{$LB_UPSTREAMS:...}"` | parses but wrong: `dial: "harness-a:{$PORT harness-b:8000}"` |
| 3 | one env per upstream `{$LB_UPSTREAM_A:harness-a:{$PORT}} ...` | wrong: `dial: "harness-a:{$PORT}"`, and override fails with `parsing upstream '127.0.0.1:111}'` |
| 4 | `reverse_proxy {$LB_UPSTREAMS}`, value supplied by compose | works with the env set (`127.0.0.1:111`, `127.0.0.1:222`). **Unset: no upstreams and `caddy validate` still returns rc 0** (silent, dangerous) |
| 5 | shipped literal `harness-a:{$PORT} harness-b:{$PORT}` | works: `harness-a:8000`, `harness-b:8000` |

None of the in-file default forms works, so the story's `{$LB_UPSTREAMS:...}` suggestion is **not usable**. Recommended mechanism: keep the shipped file exactly as F3 (literal line 5) and have the test replace that one line textually:

`reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {`  ->  `reverse_proxy 127.0.0.1:<a> 127.0.0.1:<b> {`

Verified: the line occurs exactly once in F3 and the result adapts to `127.0.0.1:111`, `127.0.0.1:222`. The test should assert that the rest of the file is byte-identical and exactly one line differs. Option 4 is the fallback if the orchestrator prefers an env override, but it changes the shipped file and loses the silent-empty guard.

### (g) `ChatState._token` and the disk state pickle

Read from code, not run: `reflex/state.py:2051-2072` `BaseState.__getstate__` copies `self.__dict__` and drops only `parent_state`, `substates`, `_was_touched`, router data on substates and inherited vars. Backend vars (such as `ChatState._token`, `chat_ui/chat_ui/state.py:269`) live in `__dict__`, so they are pickled by the disk manager (`reflex/istate/manager/disk.py:212-220` writes `token.serialize(substate)`). Not verified by an actual disk-manager round-trip.

## Inputs for later stories

**STORY-005**
- Final F3: the directive text is accepted as written. Cookie name `harness_lb`; attributes `Path=/; HttpOnly; SameSite=Lax`, no `Secure`.
- Image: `caddy:2.11.7@sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e`.
- Status when no upstream is healthy: **503**, after about 5 s; `handle_errors 502 503` syntax valid.
- Needs a decision: (1) add `504` to `handle_errors` (and/or reword the `/v1` body) so a header timeout does not leak an empty 504, and the `/v1` text does not claim "not sent to the model" for a request already sent; (2) `${LB_COOKIE_SECRET:?}` in compose is the only guard against an empty secret.
- Override: see STORY-007.

**STORY-006**
- Version `2.11.7`; Linux asset `caddy_2.11.7_linux_amd64.tar.gz` SHA-256 `727b9170...f8b` (SHA-512 `a7a433a1...ef0e7`); the release checksums file is SHA-512, so verify with `sha512sum` against it or pin the SHA-256 in the workflow.
- Assertion string: `caddy version` starts with `v2.11.7 ` (full: `v2.11.7 h1:yj0Y4fYZGPkSvibBJ1sTWE33xC0fxztVyXEW5iIdUT4=`). Windows asset: `caddy_2.11.7_windows_amd64.zip` (contains `caddy.exe`, `LICENSE`, `README.md`).

**STORY-007**
- Substitute the one `reverse_proxy` line textually (see f); do not rely on an env default.
- Admin port: two `caddy run` processes collide on the default admin `localhost:2019` (second exits 1: `listen tcp 127.0.0.1:2019: bind`). Setting env `CADDY_ADMIN=localhost:<free port>` on the child works without touching the Caddyfile (measured: third process stayed up). Caddy also writes `%APPDATA%\Caddy\autosave.json` and `instance.uuid` (Windows; `$XDG_CONFIG_HOME/caddy` on Linux); not tested whether this matters for CI.
- Command: `caddy run --config <file> --adapter caddyfile`, env `PORT`, `LB_COOKIE_SECRET`, `CADDY_ADMIN`. Readiness: deadline loop on the listen port (connected within about 1 s here). Kill: `Popen.kill()` + `wait()`; no child survived (`tasklist` clean).
- Timing: allow more than 5 s for the "no healthy upstream" cases; allow health interval + 1 s for failover; cookie-less selection is random, so tests that need each instance must loop until each has answered.
- A 503 error response can carry two `Set-Cookie` lines (see a); do not assert exactly one.

**STORY-010**
- After failover the client gets a new `Set-Cookie` on the first response from the survivor and, if it stores it, stays there (also after the first instance recovers). The user sees nothing at the HTTP level beyond the 0.25 s dial retry (dead instance) or up to one health interval (drained/unready instance, 5 s shipped).

## Files Changed

| File | Action |
|------|--------|
| `.agents/reports/PRD-019-multi-instance-deployment/STORY-004-caddy-balancer-spike.report.md` | CREATE |
| `.agents/PRDs/PRD-019-multi-instance-deployment/PRD.md` | UPDATE (F3, Section 8, Section 15, Risk 6) |
| `.agents/stories/PRD-019-multi-instance-deployment/STORY-005..007*.md` | UPDATE (`Orchestrator decision` notes) |
| plan, story, index | archived / status |

## Deviations from Plan

- Checksums were verified against the release's SHA-512 list (it publishes no SHA-256); SHA-256 values were computed locally.
- Added a small admin-port experiment (`CADDY_ADMIN`) and the shipped 5 s/30 s run; not separately listed in the plan.
- (g) is a code reading, not a run.
- Not exercised: websocket pass-through and `stream_close_delay` behaviour on reload (only that the directive is accepted); the Docker image was only run for `caddy version`, not as a balancer.

## Acceptance Criteria

- [x] AC1 version, image digest, Linux URL and checksum recorded (pin block)
- [x] AC2 cookie attributes, value shape, re-set on unhealthy and dead pinned upstream (a)
- [x] AC3 no-healthy status (503), `handle_errors` bodies, proxied 503 passthrough (b), (c)
- [x] AC4 POST not replayed, dial retry, GET retried (d), with per-backend counts
- [x] AC5 directives accepted, override mechanism found (textual substitution), PRD amended (e), (f)
