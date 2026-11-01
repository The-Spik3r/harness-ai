---
story: STORY-016
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-016-e2e-aider.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: a87c078
status: COMPLETE
completed: 2026-10-28
---

# Implementation Report — STORY-016: E2E: Aider applies a scripted edit through the harness

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-016-e2e-aider.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `a87c078`

## Summary

`tests/e2e/test_aider.py` runs the real Aider CLI, **`aider-chat==0.86.2`** in its own venv, non-interactively against a live harness on the stub upstream. Aider keeps its default streaming and runs with a pinned `--edit-format diff`.

- **Edit (AC 1).** In a throwaway git repository holding one file, the stub's SEARCH/REPLACE edit is applied and committed by Aider. The commit message also comes through the harness.
- **Block (AC 3).** An injection phrase in the request makes Aider print `Suspicious pattern detected: ignore previous instructions` and return. It makes one request, writes one row, and creates no commit.
- **What Aider sends.** A recording proxy (`_live.Recorder`) sits between Aider and the harness and keeps only key names, roles and the model. Aider 0.86.2 sends exactly `messages`, `model`, `stream` and `temperature`. It **never sends `tools`**, `tool_choice` or `functions`. So `ignored_params` is NULL on every row: Aider sends nothing that the harness ignores.

The run also produced two client findings that STORY-019's per-client setup needs. Both are pinned as tests:

1. **Model names.** litellm strips Aider's `openai/` provider prefix, so Aider must be told **`openai/openai/gpt-4o`** for the harness to see `openai/gpt-4o`. With `--model openai/gpt-4o`, the harness sees `gpt-4o`. Aider *knows* `gpt-4o`, and for known models it appends its reminder as a **trailing `system` turn**, which `/v1` refuses with 400 `invalid_messages` (no row).
2. **A 403 is retried by Aider for about a minute.** litellm maps 400/401/404/408/422/429/5xx by status, and a 403 falls through to `litellm.APIError`, which Aider's `exceptions.py` marks retryable. `x-should-retry: false` is never read. One `model_not_permitted` refusal became **9 requests and 9 rows**. This contradicts PRD-015 story 6 ("Aider shows it and stops") for `usage_limit_exceeded` too, since that is also a 403. **This needs a PRD decision; see Findings.**

STORY-015's subprocess plumbing moved into `tests/e2e/_live.py`, which this module and STORY-017 share. STORY-015's E2E still passes 19/19. No file under `app/` changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Aider venv + pin, harness venv unchanged | `requirements-e2e-aider.txt`, `requirements-e2e.txt` | ✅ |
| 2 | Spike: run Aider by hand, record what it sends | (research, below) | ✅ |
| 3 | Extract the shared plumbing; STORY-015 re-run 19/19 | `tests/e2e/_live.py`, `tests/e2e/test_openai_sdk.py` | ✅ |
| 4 | Stub script + README | `tests/e2e/scripts/aider.json`, `tests/e2e/scripts/README.md` | ✅ |
| 5 | Recording proxy (in `_live.py`, unit-tested) | `tests/e2e/_live.py`, `tests/test_e2e_live.py` | ✅ |
| 6 | Fixtures: Aider home, throwaway repo, runner | `tests/e2e/test_aider.py` | ✅ |
| 7 | The tests | `tests/e2e/test_aider.py` | ✅ |
| 8 | Regression (`-m "not db"`, full suite) | none | ✅ |

## Aider version, install and settings (AC 4)

- `python -m pip index versions aider-chat --use-feature=truststore` gave `aider-chat (0.86.2)`, the newest on 2026-10-27/28.
- **Separate venv, recorded choice.** The commands were `uv venv --python 3.11 C:\Users\tobip\.venvs\aider-e2e` and then `uv pip install --python C:\Users\tobip\.venvs\aider-e2e\Scripts\python.exe -r requirements-e2e-aider.txt`. uv got through the TLS interception without `--native-tls`. Aider brings `openai 2.20.0`, `pydantic 2.12.5`, `httpx 0.28.1` and `litellm 1.81.10`, while the harness venv has `openai 3.40.0` and `pydantic 2.13.5`. A shared venv would have moved both. The harness venv's `pip freeze` was identical before and after (103 lines, `diff` empty).
- `aider-chat` lives in **`requirements-e2e-aider.txt`**, not `requirements-e2e.txt` as the story note suggested: one requirements file per venv. `requirements-e2e.txt`'s comment points to it. The module finds Aider through **`HARNESS_E2E_AIDER`** and never through `PATH`.
- **Command line** (the edit run; the token is passed in env, never on the command line):

  ```
  C:/Users/tobip/.venvs/aider-e2e/Scripts/aider.exe
    --config <aider home>/aider.conf.yml
    --model-settings-file <aider home>/model-settings.yml
    --env-file <aider home>/empty.env
    --input-history-file <aider home>/<test>.input.history
    --chat-history-file <aider home>/<test>.chat.history.md
    --message "E2E-AIDER-EDIT [<nonce>-edit] change the greeting to say hello, harness"
    greeting.py
  ```

  The env sets `OPENAI_API_BASE=<recorder>/v1`, `OPENAI_API_KEY=<harness token>`, `HOME`/`USERPROFILE=<aider home>`, `LITELLM_LOCAL_MODEL_COST_MAP=True`, `PYTHONIOENCODING=utf-8` and `NO_COLOR=1`. Every inherited `OPENAI_*`, `OPENROUTER_*`, `ANTHROPIC_*` and `AIDER_*` variable is removed. The cwd is the throwaway repo, and stdin is `DEVNULL`.
- **`aider.conf.yml`** (every key checked against 0.86.2's `aider/args.py`):

  ```yaml
  model: openai/openai/gpt-4o
  edit-format: diff
  stream: true
  yes-always: true
  pretty: false
  fancy-input: false
  check-update: false
  analytics-disable: true
  show-release-notes: false
  show-model-warnings: false
  auto-lint: false
  auto-test: false
  map-tokens: 0
  gitignore: false
  dirty-commits: false
  detect-urls: false
  encoding: utf-8
  ```

- **`model-settings.yml`**:

  ```yaml
  - name: openai/openai/gpt-4o
    edit_format: diff
    reminder: user
    use_temperature: true
  ```

  `model-settings-unprefixed.yml` (only for the 403 finding) holds `- name: openai/gpt-4o / edit_format: diff / reminder: user`.
- **Settings file names.** The files deliberately avoid the `.aider.conf.yml` / `.aider.model.settings.yml` names. The spike showed that Aider loads `.aider.model.settings.yml` from `HOME` **on its own**, which silently changed one variant's result.
- **History files** go to the Aider home, so the repository has no untracked files after a run (`git status --porcelain` is empty).

## Task 2 spike: what Aider sends

The spike was a scratch script running harness + stub + recorder + Aider in variants. Its findings decided the module's design:

| Question | Observed (0.86.2) |
|---|---|
| Model received for `--model openai/openai/gpt-4o` | `openai/gpt-4o` (litellm strips one `openai/`) |
| Model received for `--model openai/gpt-4o` | `gpt-4o`. Aider recognises it ("Weak model: gpt-4o-mini") |
| Keys of the edit request | `messages, model, stream, temperature` (`stream: true`, `temperature: 0`). No `stream_options`, `tools`, `tool_choice`, `functions` or `user` |
| Messages | 10 turns, all `content` strings, keys `role`/`content` only. Roles: `system`, then 4 example user/assistant pairs, then `user` |
| Last role, `openai/openai/gpt-4o` | `user`, with or without a settings file (the default `reminder` is `user` for an unknown name) |
| Last role, `gpt-4o` (known) | **`system`**, 5 turns (examples folded into the system prompt). `/v1` gives 400 `messages[4]: the last message must be a user turn`, no row |
| Requests per `--message` run | 2: the edit (streamed) and then the **commit message** (`stream` absent, i.e. false; roles `system, user`; user turn = context + `# Diffs:` + diff). Source: `aider/repo.py:326-361` and `models.py:1022-1065` (`simple_send_with_retries`, `"stream": False`) |
| Retry policy | `aider/exceptions.py:14-52`. `BadRequestError` retry=False, **`APIError` retry=True**, `InternalServerError`/`ServiceUnavailableError`/`BadGatewayError` retry=True. Backoff 0.125 s doubling up to `RETRY_TIMEOUT` (60 s), so 9 attempts |
| litellm 403 mapping | `litellm/litellm_core_utils/exception_mapping_utils.py:498-603` (OpenAI branch): 400, 401, 404, 408, 422, 429, 500, 502, 503 and 504 are mapped. Anything else, 403 included, is `raise APIError(...)` |
| Exit code | 0 on success, on the 400 block, on the trailing-system 400 and on the retried 403 (`--message` mode returns after printing the error) |
| Stub script | The commit-message request also quotes the edit request (Aider passes the chat as context). The first draft's edit rule therefore answered it too, and the commit subject became the SEARCH/REPLACE block. A `# Diffs:` rule placed **first** fixes this |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ (no `app/` change; the harness subprocess starts in every E2E run) |
| `tests/test_e2e_live.py` | ✅ 18 passed |
| `pytest tests/e2e` without the flag | ✅ 24 skipped (`e2e: pass --run-e2e`), no errors |
| `-m "not db"` (Docker-free, `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`) | ✅ 3,487 passed / 50 skipped in 132 s (STORY-015: 3,469 / 45) |
| Full suite (throwaway libSQL `:8086`) | ✅ 4,911 passed / 51 skipped in 448 s, 0 `libsql verdict` lines (STORY-015: 4,893 / 46) |
| E2E `test_aider.py` (`:8088`) | ✅ 5/5 in 104 s (about 68 s of it is the 403 retry test) |
| E2E both modules, same container again | ✅ 24/24 in 139 s |
| `git diff --stat HEAD -- app/` | ✅ empty |
| Frontend lint | n/a (no UI) |

## End-to-end run

Commands, exactly as run (Git Bash, harness venv Python). Docker Desktop was already up:

```bash
docker run -d --name harness-libsql-e2e016 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 python -m pytest tests/e2e/test_openai_sdk.py -m e2e --run-e2e -q -p no:cacheprovider
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_AIDER=C:/Users/tobip/.venvs/aider-e2e/Scripts/aider.exe \
  python -m pytest tests/e2e/test_aider.py -m e2e --run-e2e -v -p no:cacheprovider
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_AIDER=C:/Users/tobip/.venvs/aider-e2e/Scripts/aider.exe \
  python -m pytest tests/e2e -m e2e --run-e2e -v -p no:cacheprovider
```

| Run | Result |
|---|---|
| STORY-015 module after the extraction | ✅ 19 passed in 32.5 s |
| Aider module, first | 4 passed, 1 failed. The failure was test-side: Aider wraps messages at 80 columns, so assertions now match on whitespace-normalised text (Deviation 4) |
| Aider module, second | ✅ 5 passed in 104.5 s |
| Both modules, **same container** again | ✅ 24 passed in 138.6 s. The nonce isolates runs |
| Control 1: `reminder: user` removed from `model-settings.yml` (local, restored) | ✅ The edit test still **passes** (16.7 s). For the unknown double-prefixed name Aider's default is already `user`, so the pin is belt-and-braces. The trailing-system failure needs a *known* name, and `test_a_known_model_name_ends_with_a_system_turn_and_is_refused` pins it |
| Control 2: `HARNESS_E2E_AIDER` unset, or `C:/nope/aider.exe` | ❌ as intended: 5 setup errors in 0.42 s, `HARNESS_E2E_AIDER is not set. Install the pinned Aider in its own venv: uv venv ...` (or `does not name a file`). No child starts. The first try left `test_zz` starting children and failing, so it now requests `aider_exe` first (Deviation 5) |
| Control 3: the stub's SEARCH text changed to `return "howdy"` (local, restored byte for byte) | ❌ as intended. Aider prints `SearchReplaceNoExactMatch` and sends **one reflection request**: 2 POSTs, both streamed, 10 then 14 turns, upstream rules `['1', 'default']`. The stub's default answers without an edit block, so Aider stops with exit 0, the file is unchanged and there is no commit. Aider's own reflection loop is separate from HTTP retries |
| After the runs | 0 `uvicorn`/`stub_openrouter`/`aider` processes (`Get-CimInstance Win32_Process`). Harness ports closed (fixture assertion). `docker rm -f harness-libsql-full016`, and `harness-libsql-e2e016` removed after this report |

### Requests Aider sent (recorder log, final run; names only)

| Test | Exit | POSTs | Keys | tools / tool_choice / functions | Last role | Upstream rules |
|---|---|---|---|---|---|---|
| edit | 0 | 2 | `messages, model, stream, temperature`, then `messages, model, temperature` | absent / absent / absent | user, user | `1` (edit), `0` (commit msg) |
| block | 0 | 1 | `messages, model, stream, temperature` | absent | user | none |
| known name (`gpt-4o`) | 0 | 1 | same | absent | **system** | none |
| 403 (`gpt-4o`, `reminder: user`) | 0 | **9** | same | absent | user | none |

### Audit rows produced (final run; `rows.json`, no tokens or prompt text)

| id | user | success | streamed | ingress/profile | model | tokens | conversation_key | ignored_params | verdict | from |
|---|---|---|---|---|---|---|---|---|---|---|
| 74 | edit | True | True | v1/code | openai/gpt-4o | 60 | `7b7bbd83d0ab…` | NULL | - | the edit (the session) |
| 75 | edit | True | False | v1/code | openai/gpt-4o | 38 | `d0c92f2e1dbf…` | NULL | - | Aider's commit-message request |
| 76 | block | True | True | v1/code | - | - | `69f1544da9eb…` | NULL | pattern=ignore previous instructions | the block, one row |
| 77-85 | mapping | True | True | v1/code | - | - | `9c01e2e27dfa…` (all 9) | NULL | denied=query:model:gpt-4o | one 403, retried 8 times by Aider |

The trailing-system run wrote no row (a shape refusal). **`ignored_params` names (AC 2): none.** Aider 0.86.2 sends nothing the harness ignores (`temperature` is forwarded).

## Findings (for STORY-019 and the PRD)

1. **A 403 is retried by Aider (litellm `APIError`)**, about 9 attempts in 60 s with one row each. This affects `model_not_permitted`, `usage_limit_exceeded`, `permission_denied` and `break_glass_not_permitted`. PRD story 6 ("Aider shows it and stops") and the D2 rationale for 403 ("not a 429 my clients retry") don't hold for litellm-based clients. `x-should-retry` doesn't help, because litellm never reads it. Options for the PRD owner: (a) document it as a known client limit in the README; (b) return policy blocks as 400 to litellm clients, which changes D2; (c) report it upstream to litellm/Aider. **Not decided here.** `test_a_403_is_retried_by_aider_until_it_gives_up` pins the current behaviour, so either side changing will be noticed.
2. **Model name mapping for the README:** `--model openai/openai/gpt-4o` → harness sees `openai/gpt-4o`. The plain `openai/gpt-4o` fails with 400 `messages[N]: the last message must be a user turn`, because Aider's reminder for known models is a trailing `system` turn. A model-settings entry with `reminder: user` for that name gets past it, and then hits the allowlist (`gpt-4o` is not on it).
3. **Aider's commit message is a separate, non-streamed request** with its own `conversation_key`. PRD story 7's example ("twelve requests ... `streamed=1`, one `conversation_key`") describes the edit session only.
4. **One `conversation_key` across Aider sessions by the same user.** The key hashes the first system and first user turn, and Aider's first user turn is a fixed example message. So every Aider session of one user, with one edit format, shares a key (spike: runs A and B, and the block run, all `75bad37d…`). This is limit 1 of `conversation_key.py`, worth stating in the README.
5. **The developer `.aider.model.settings.yml` in `HOME` is loaded implicitly.** Per-client setup docs should say which file Aider actually reads.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `requirements-e2e-aider.txt` | CREATE | +7 |
| `requirements-e2e.txt` | UPDATE | +2/-1 |
| `tests/e2e/_live.py` | CREATE | +348 |
| `tests/e2e/test_openai_sdk.py` | UPDATE | +15/-178 |
| `tests/e2e/test_aider.py` | CREATE | +492 |
| `tests/e2e/scripts/aider.json` | CREATE | +21 |
| `tests/e2e/scripts/README.md` | UPDATE | +3/-1 |
| `tests/test_e2e_live.py` | CREATE | +242 |
| `.agents/plans/.../completed/STORY-016-e2e-aider.plan.md` | CREATE (archived) | +355 |

## Deviations from Plan

1. **The unprefixed-name test became two tests.** The plan expected `--model openai/gpt-4o` to give one 403 `model_not_permitted`. In fact Aider recognises `gpt-4o` and sends a trailing `system` turn (400 `invalid_messages`, no row). With `reminder: user` the 403 does come, and Aider then retries it 9 times. Both are pinned: `test_a_known_model_name_ends_with_a_system_turn_and_is_refused` and `test_a_403_is_retried_by_aider_until_it_gives_up`.
2. **The recorder and `expected_ignored_params` live in `_live.py`, not `test_aider.py`.** STORY-017 needs them too, and this way the everyday suite unit-tests them (`tests/test_e2e_live.py`, 18 tests). The parameter sets are **mirrored literals**, the plan's fallback, because importing `app.services.v1_translate` builds `app.config.Settings()` in the test process (`app/config.py:656`), which reads the developer's `.env`. A unit test keeps the mirrors equal to the translator's sets. That test also caught that a message `name` is recorded as `messages[].name`, not `name`.
3. **The stub script has a `# Diffs:` rule first.** The commit-message request quotes the edit request, so the plan's single edit rule answered both. The default now says `aider.json has no rule for this request`, which makes an unexpected request visible.
4. **Output is matched on whitespace-normalised text.** Aider wraps its messages at 80 columns.
5. **`test_zz` requests `aider_exe` first**, so a missing Aider errors at setup instead of starting children.
6. **Settings files are named `aider.conf.yml` / `model-settings.yml`**, not `.aider.*`, so Aider can't load them implicitly (it reads `.aider.model.settings.yml` from `HOME` on its own). History files are redirected to the Aider home, which keeps the repo clean.
7. **`run_child(cwd, env, *args)`** takes an env dict, not an env builder. Both modules call it with one fixed env.
8. **The commit isn't attributed to "(aider)".** 0.86.2 commits with the repo's git identity. The test asserts the subject, which proves the message came through the harness, not the author.
9. **The "every row" AC** is met for the edit session. The commit-message row is asserted on its own terms (`streamed=0`, its own key), as plan Decision 5 anticipated.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/e2e/test_aider.py` (5, opt-in) | Edit applied + committed, rows and request shapes. Block: reason printed, one request, one row, no commit. Known name: trailing system turn refused, no row. 403 retried by Aider (finding). Every row `v1`/`code` |
| `tests/test_e2e_live.py` (18) | Mirrors equal the translator's sets. Aider shape ignores nothing. Ignored names sorted/joined (`messages[].name`, `stream_options.x`). Rejected-unless-default never ignored. The rule equals `translate_request` on one body. Shape keeps no content. `tools: []` shape. Recorder: relays SSE and records the shape without content or token, forwards `Authorization`, relays an error status + `x-should-retry` only, forwards GET apart from posts, relays a non-JSON body. DB guard: unset, non-loopback, loopback. `port_closed_within`. `stop`. Stub log parsing |

## Acceptance Criteria

- [x] Throwaway git repo with one file, live harness on the stub, Aider with `OPENAI_API_BASE` / `OPENAI_API_KEY` (harness token) and an allowlisted model (`openai/openai/gpt-4o` → `openai/gpt-4o`): the stub's SEARCH/REPLACE edit is applied and committed by Aider
- [x] The edit session's rows: `ingress='v1'`, `profile='code'`, `streamed=1`, one `conversation_key`, and `ignored_params` naming what Aider sent and the harness did not forward: **nothing** (NULL; Aider sends `messages, model, stream, temperature`). The commit-message row (`streamed=0`, its own key) is reported separately (Finding 3)
- [x] Injection phrase: Aider prints `Suspicious pattern detected: ignore previous instructions` and returns (exit 0), one request, one row, no retry
- [x] The report records the pinned `aider-chat` version (0.86.2), the full command line, both settings files, and that Aider does **not** send `tools` in this mode
- [x] All tasks completed
- [x] `-m "not db"` and the full suite pass, and `tests/e2e` is skipped by default
- [x] No file under `app/` changed
- [x] Follows existing patterns
