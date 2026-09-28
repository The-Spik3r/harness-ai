---
story: STORY-012
prd: PRD-012
slug: placeholder-spike
title: "Placeholder spike and decisions/D5-placeholders.md"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: Placeholder spike and decisions/D5-placeholders.md

## Summary

This story adds one live-model spike script, `scripts/spike_pii_placeholders.py`, a small offline test module for its pure parts, and the decision record `.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md`. **No file under `app/` or `chat_ui/` changes**, whatever the outcome (AC 4, Technical Notes).

The script runs a tiny, deterministic agent loop. A system prompt offers four text tools (`read_file`, `replace_in_file`, `write_file`, `done`). The model's reply is parsed, the tool is applied to an in-memory workspace of **raw** files, and the tool result goes back as the next `user` turn. Every send goes through the real `run_conversation(profile="code")`, so step 6 redacts exactly what a PRD-014 client's traffic would get. Three tasks are built on existing `tests/corpora/pii/code/` files: edit a fixture, write a test, rename a field.

Each task runs under four arms:
- **(a) fixed** `<TYPE>`: production, unpatched.
- **(b) indexed per request** `<TYPE_n>`, numbered by first appearance across the conversation. There is no stored mapping, and numbering restarts on every send.
- **(c) reversible**: `<TYPE_n>` from an in-memory mapping kept for the task's conversation, with placeholders restored in the response before the pipeline returns it.
- **control**: PII redaction patched off. This is not an option. It is the baseline that separates "the model cannot do the task" from "placeholders stopped it". The corpora are synthetic by construction (`tests/corpora/pii/SOURCES.md`), so this arm sends no real PII.

(b) and (c) are produced by swapping `query_pipeline._redact` for a spike function. That function reuses `pii_redactor`'s own span pipeline and changes only the placeholder string. The mappings live only in the script (Technical Notes).

The report prints, per arm and task, the placeholders that appear in model output and whether the final artifact is correct (AC 2). The decision rules below are written **before** any number is taken, in the STORY-003 style, and they pick the D5 outcome mechanically.

## User Story

As an integrating developer
I want evidence on whether fixed placeholders make coding agents unusable
So that the choice between fixed, indexed and reversible placeholders is made on data

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-012-placeholder-spike.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`. See Sections 7 (F10), 9.2 (T8), 14 (Risk 7) and 15 (D5).

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (story type: spike) |
| Complexity | MEDIUM |
| Systems Affected | `scripts/` (new script), `tests/` (new offline test module), PRD docs (decision record, Section 15 link) |
| Story | STORY-012 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-009 (done). Uses `run_conversation(profile="code")` with step 6 per policy |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` has only `frontend-design`, which covers visual UI design. This story has no UI. The story says "Skills: none applicable" | — |

---

## Findings from Exploration

### F-1: `_redact` is the single seam, and it is patchable by module name
`run_conversation` calls `_redact(message.content, policy)` for every covered message at step 6, and again at step 8 only if `policy.output` is set (`app/services/query_pipeline.py:142-159`, `:449-465`, `:500-503`). It is looked up as a module global at call time, so `unittest.mock.patch.object(query_pipeline, "_redact", spike_fn)` changes the placeholders for the whole pipeline and nothing else. `code` has `output=False` by default, so step 8 never calls it. The upstream response reaches the caller unmasked, which is exactly the file-writing path D1 describes.

### F-2: The span pipeline is reusable. Only the placeholder string needs to change
`redact_for_policy` is `strip_fenced_blocks`, then `_analyze`, `_resolve_overlaps`, `_json_tokens`/`_is_json_document`, `_replacement_ranges`, `_splice`, then the JSON post-condition (`app/services/pii_redactor.py:408-488`). `_replacement_ranges` returns `(start, end, replacement, entity_type)` tuples. `replacement` is `<TYPE>`, or `"<TYPE>"` (quoted) for a JSON number token (`:354-393`). The spike keeps every range and rewrites only `replacement`. Structure-safe splitting, fence skipping and JSON clipping are therefore production's own. The placeholder alphabet gains digits and `_`, and neither is special inside any string literal the PRD lists (Section 6.6, rule 1).

### F-3: The upstream is injectable, so reversal needs no production hook
`run_conversation(..., call_openrouter=...)` takes the upstream as an argument, and it forwards `params=` only when it is set (`:474-483`). A wrapper around the real `call_openrouter` can see `redacted_messages` (what the model saw) and the raw response. For (c) it can restore placeholders **before** the pipeline logs and returns the response.

### F-4: The duplicate check would block repeated tasks
Step 4 is `check_duplicate(identity.user_id, dedup_key(...))` over the raw conversation (`:291-310`). The first turn of a task is identical across arms and runs, so the second arm would get `BLOCKED_DUPLICATE`. Mitigation: a fresh `user_id` per (run nonce, arm, task, run), such as `spike012-<nonce>-b-fixture-2`. The conversation text is not altered, so every arm sees byte-identical prompts. Every send's result must be a `QuerySuccessResponse`. Anything else aborts that task-run with the outcome recorded (the `measure_history_latency.py` rule).

### F-5: Tool results must be `user` turns, unfenced
Step 0 refuses `tool` turns until PRD-016 (`_validate_conversation`). Under `code`, fenced blocks are skipped (D2), so a fenced file read would carry no placeholders and would test nothing. Tool results are therefore sent unfenced, as `user` turns, the way `scripts/measure_pii_latency.py` shapes tool-like turns (PRD F1). The tool protocol is Cline-style XML tags, also unfenced, so the assistant turns fed back as history are redacted too (T7, Section 6.3), as they would be for a real text-protocol agent. The parser matches only the four known tag names, so a placeholder such as `<EMAIL_ADDRESS_1>` inside a tool argument cannot be mistaken for a tag.

### F-6: Environment and loader facts
- `Settings()` needs `DATABASE_URL`, `OPENROUTER_API_KEY` and `ADMIN_TOKEN` in the environment before the first `app.` import (`scripts/measure_history_latency.py:69-98`). Here `OPENROUTER_API_KEY` must be **real**. The script refuses to start if it is unset or equals a known dummy.
- `log_query` writes to the database, and there is no FK on `audit_logs.user_id` (grep `app/db/models.py`). The script needs the local libSQL dev server plus `database.init_db()`, and it refuses a non-local URL unless `--allow-remote-database` is passed (`_guard_local`, `measure_history_latency.py:349-360`).
- Startup order is `pii_redactor.load(); authz.load(); pattern_config.load(); pii_policy.load()` (`app/main.py:14-17`). The script calls the same four.
- `authorize_model` passes any model for roles in `MODEL_ALLOWLIST_WILDCARD_ROLES = {"admin"}` (`app/services/authz.py:49,148`). The spike identity is `Identity(user_id=..., role="admin")`, so `--model` can be any OpenRouter slug. It is **required** and has no default, so the record always names the model.
- No `pytest.ini`, `pyproject.toml` or `setup.cfg` exists. CI runs `pytest -q` (`.github/workflows/ci.yml:62`) with the default `python_files = test_*.py *_test.py`, so `scripts/spike_pii_placeholders.py` is never collected (AC 5). A test pins this.
- `PyYAML` is already in `requirements.txt`, which task 3's checker needs. No new dependency.

---

## Decision rules (written before measuring)

Definitions, per arm:
- A **task-run** is one task under one arm in one run. It is **correct** if its checker passes on the final workspace (see Tasks). A task-run that aborts (turn cap, non-success pipeline result, upstream error) is incorrect, and its cause is recorded.
- `success(arm)` = correct task-runs / (3 tasks × `--runs`).
- `sent(arm, task)` = placeholders in the messages the model received. A task with `sent = 0` under (a) exercised nothing, so the run is **invalid**. The script reports that loudly and the decision is not taken until the fixture is fixed.

Rules, applied in order:
- **R0 (validity).** `success(control) ≥ 2/3`. Otherwise the model cannot do the tasks unredacted, the run says nothing about placeholders, and the record says "inconclusive: re-run with a stronger model". The default stays (a).
- **R1 (does (a) fail?).** (a) **fails** if `success(a) < success(control) − 1/3`, meaning on average it loses at least one of the three tasks per run to redaction, **or** some task is incorrect in every run under (a) while correct in at least half its runs under control.
- **R2.** If (a) does not fail → **decision (a)**. No production change (AC 4). If (b) also scores above (a) by ≥ 1/3, the record lists (b) under Future Considerations. It is not adopted, because the PRD keeps (a) unless (a) is unusable (F10).
- **R3.** If (a) fails, apply R1's test to (b) against control. If (b) does not fail → **decision (b)**. The record names a follow-up story (proposed `STORY-015 indexed-placeholders`) and implements nothing (AC 4).
- **R4.** If both (a) and (b) fail, and (c) does not → **decision: (c) is justified by the data, but not adopted in PRD-012**. The record states the at-rest cost: a server-side mapping of real values keyed by conversation is a new PII store (T8), with retention, deletion and access control that PRD-013 or a new PRD must own. The default stays (a) until then.
- **R5.** If all three fail → (a) stays. The record says placeholders of any shape are not the bottleneck at this model, and it lists the observed failure causes.

Small-N caveat, stated in the record: the default is `--runs 3`, so 9 task-runs per arm, and the rules above act on differences of whole tasks, not percentages. The record reports the raw counts next to every rate.

---

## Patterns to Follow

### Script docstring: a spike that records and asserts nothing
```python
# SOURCE: scripts/measure_pii_latency.py:1-8
"""What PII redaction costs at agent sizes, and what it wrongly masks, measured before anything changes.

PRD-012 STORY-003, serving PRD Section 4 (*Benchmark and baseline*), Section 6.4
(D7), Section 11 (*Benchmark criteria*), Risk 2 and threat T10. This is a spike:
it *records* numbers and asserts none of them, exactly as
`scripts/measure_history_latency.py` does -- ...
```

### Env bootstrap before the first `app.` import (argv peek for the DB URL)
```python
# SOURCE: scripts/measure_history_latency.py:64-98
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
...
def _bootstrap_environment(argv: Optional[Sequence[str]] = None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
    os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")
    return endpoint

_ENDPOINT = _bootstrap_environment()

from app.config import settings  # noqa: E402
```
Deviation: do **not** default `OPENROUTER_API_KEY`. Leave it unset if it is unset, and have `_measure_command` refuse to run with a clear message. The offline tests set a dummy themselves, as `tests/test_measure_pii_latency.py:17-18` does. Importing the script must stay side-effect-free: no DB, no network, no analyzer build.

### Local-DB guard
```python
# SOURCE: scripts/measure_history_latency.py:349-360
def _guard_local(endpoint: str, allow_remote: bool) -> None:
    if allow_remote:
        return
    host = urlsplit(endpoint).hostname or ""
    if host in _LOCAL_HOSTS:
        return
    raise SystemExit(f"Refusing to seed a non-local database: {endpoint}\n" ...)
```

### The span pipeline being reused (placeholder is the only change)
```python
# SOURCE: app/services/pii_redactor.py:470-488
analysis = strip_fenced_blocks(text) if policy.skip_fenced_blocks else text
accepted = _resolve_overlaps(_analyze(analysis, policy))
if not accepted:
    return RedactionResult(text, [])
json_tokens = _json_tokens(text) if _is_json_document(text) else None
ranges = _replacement_ranges(text, analysis, accepted, json_tokens)
redacted = _splice(text, ranges)
entities = sorted({entity_type for _, _, _, entity_type in ranges})
if json_tokens is not None:
    try:
        json.loads(redacted)
    except (ValueError, RecursionError) as exc:
        raise PiiRedactorError("redaction would produce invalid JSON") from exc
```

### Stub upstream signature (three parameters plus optional `params`)
```python
# SOURCE: scripts/measure_history_latency.py:412-434
def call(messages, model=_MODEL, api_key=None) -> OpenRouterResult:
    ...
    return OpenRouterResult(response=..., model_used=model, tokens_used=64)
```

### CLI shape
```python
# SOURCE: scripts/measure_history_latency.py:748-794
def _build_parser() -> argparse.ArgumentParser: ...
    parser.set_defaults(func=_measure_command)
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)
if __name__ == "__main__":
    sys.exit(main())
```

### Script tests: pure parts, fresh-interpreter import probe
```python
# SOURCE: tests/test_measure_pii_latency.py:13-40
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
import scripts.measure_pii_latency as bench

def test_importing_the_script_builds_no_analyzer():
    probe = ("import scripts.measure_pii_latency\n"
             "from app.services import pii_redactor\n"
             "assert pii_redactor._analyzer is None, pii_redactor._analyzer\n")
    completed = subprocess.run([sys.executable, "-c", probe], cwd=_REPO_ROOT, ...)
    assert completed.returncode == 0, completed.stderr
```

### Error handling
- Upstream errors: `OpenRouterError` propagates from `run_conversation` after its audit row. The script catches it per task-run, records `aborted: upstream error`, and continues with the next task-run. It never retries silently.
- `PiiRedactorError` (JSON post-condition) is caught the same way and recorded as `aborted: redaction error`. This is a finding, not a crash.
- Non-success results (`BLOCKED_*`) are recorded with their `status`, and the task-run is aborted (F-4).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/spike_pii_placeholders.py` | CREATE | The spike: arms, placeholder schemes, agent loop, tasks, checkers, report (AC 1, 2) |
| `tests/test_spike_pii_placeholders.py` | CREATE | Offline tests of the pure parts, parity of the fixed scheme with `redact_for_policy`, one stubbed end-to-end loop, and the not-collected guard (AC 5) |
| `.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md` | CREATE | Method, raw results, model, decision, and the (c) at-rest reasoning (AC 3, 4) |
| `.agents/PRDs/PRD-012-pii-for-code/PRD.md` | UPDATE | Link the record from Section 15 (the D5 row and *Related documents*) |
| `.agents/stories/PRD-012-pii-for-code/STORY-015-indexed-placeholders.md` + `index.md` | CREATE / UPDATE | **Only if the decision is (b)** (R3): a `todo` follow-up story that the record names |

No `app/`, `chat_ui/`, `requirements.txt` or `.env.example` change.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight

- Confirm the epic branch is `epic/PRD-012-pii-for-code` and the tree is clean (`git status`).
- Start the libSQL dev server the suite uses (the `docker run` line in `scripts/measure_history_latency.py`'s docstring) and run `pytest -q` to get a green baseline.
- Open `tests/corpora/pii/code/billing_seed.py:81-120` (`CUSTOMERS`), `seed-users.json` and `staging-values.yaml`. Fix the exact targets of the three tasks (Task 4). Check under the `code` policy that each target file yields at least one span: `redact_for_policy(content, get_pii_policy("code"))` returns non-empty `entities`.
- **Validate**: the suite is green, and each of the three files has ≥ 1 entity under `code`.

### Task 1: Script skeleton, env bootstrap, CLI

- **File**: `scripts/spike_pii_placeholders.py`
- **Action**: CREATE
- **Implement**:
  - A docstring in the STORY-003 style. It says what is compared, why there is a control arm, why tool results are unfenced `user` turns (F-5), why each task-run has its own user id (F-4), that the script calls a live model and is outside CI (Risk 7), and that every value sent is synthetic (`tests/corpora/pii/SOURCES.md`).
  - An env bootstrap that mirrors `measure_history_latency.py` (argv peek for `--database-url`) **without** defaulting `OPENROUTER_API_KEY`.
  - A CLI with these flags:
    - `--model` (required);
    - `--runs` (default 3);
    - `--arms` (default `control,a,b,c`, validated);
    - `--tasks` (default all three, validated);
    - `--max-turns` (default 8);
    - `--temperature` (default 0.0) and `--max-tokens` (default 4096), passed as `GenerationParams`;
    - `--database-url`, `--allow-remote-database`;
    - `--json PATH` to write raw results;
    - `--transcripts DIR` (optional, off by default) to dump per-task-run message logs for inspection. Transcripts are not checked in.
  - `_measure_command`: guard the local DB, refuse a missing or dummy API key, refuse `PII_REDACTION_ENABLED=false`, then call the four loaders (F-6) and `database.init_db()`.
- **Mirror**: `scripts/measure_history_latency.py:64-98, 349-360, 696-794`
- **Validate**: `python scripts/spike_pii_placeholders.py --help` exits 0, and running without `OPENROUTER_API_KEY` exits non-zero with a message that names the variable.

### Task 2: Placeholder schemes (arms a, b, c, control)

- **File**: `scripts/spike_pii_placeholders.py`
- **Action**: UPDATE
- **Implement**:
  - `class Scheme` with one method `redact(text, policy) -> tuple[str, list[str]]`. It is the signature of `query_pipeline._redact`.
    - `FixedScheme`: holds a reference to the original `query_pipeline._redact`, captured at import, and delegates to it. Arm (a) is then production byte for byte. It exists so the parity test and the loop treat all arms uniformly. The live (a) arm still runs unpatched.
    - `ControlScheme`: returns `(text, [])`.
    - `IndexedScheme(persistent: bool)`: if `not policy.structure_safe`, delegate to the original. `chat` is never run here, but that makes it impossible to mask chat differently. Otherwise run F-2's pipeline and rewrite each range's replacement:
      - `number(entity_type, original)` looks up `self._mapping[(entity_type, original)]` and, if absent, assigns the next `n` for that type (`itertools.count(1)` per type). `original = text[start:end]`, the exact bytes the range covers, which for a JSON number is the whole token.
      - `<TYPE>` becomes `<TYPE_n>`, and `"<TYPE>"` becomes `"<TYPE_n>"`. Re-derive the string from `entity_type` and whether the old replacement was quoted. Do not string-replace.
      - Keep the JSON post-condition and raise `PiiRedactorError` as production does.
      - `begin_request()` clears `_mapping` when `persistent` is False. That is arm (b): numbered by first appearance within one send, restarting every send. Numbering is stable over the conversation's unchanged prefix, because step 6 redacts messages in order and earlier turns are byte-identical between sends. A test pins this property.
      - `restore(text) -> tuple[str, int]` (arm (c) only) replaces every `<TYPE_n>` in the mapping's reverse table with its original value and returns the number of unknown `<TYPE_n>` left over. A JSON-number original is restored without quotes only when the placeholder appears quoted (`"<TYPE_n>"` becomes the number token). Otherwise the raw value is used.
  - `placeholder_count(text, entities) -> int`, a regex over `<(?:TYPE1|TYPE2|...)(?:_\d+)?>` built from the `code` policy's entity list **plus** the NER types, so a model echoing `<PERSON>` from its own imagination is also counted.
  - A context manager `_scheme_installed(scheme)`, `unittest.mock.patch.object(query_pipeline, "_redact", scheme.redact)`. It is installed for arms b, c and control. Arm (a) runs unpatched.
- **Mirror**: `app/services/pii_redactor.py:354-393, 470-488` (F-2)
- **Validate**: Task 7's scheme tests.

### Task 3: Agent loop (tool protocol, workspace, upstream wrapper)

- **File**: `scripts/spike_pii_placeholders.py`
- **Action**: UPDATE
- **Implement**:
  - `SYSTEM_PROMPT` (a `system` turn, not redacted under `code`, D3). It describes one tool call per reply, in exactly these unfenced tags:
    - `<read_file><path>…</path></read_file>`
    - `<replace_in_file><path>…</path><old>…</old><new>…</new></replace_in_file>`
    - `<write_file><path>…</path><content>…</content></write_file>`
    - `<done/>`

    It says "no Markdown fences around tool calls". Keep it short and fixed, since it is part of the method recorded in D5.
  - `parse_tool_call(reply) -> ToolCall | ParseError`: find the first opening tag among the four names only, then take the content up to that tag's own closing tag. Inner tags are matched by name only, so `<EMAIL_ADDRESS_1>` inside `<content>` is plain text (F-5). Strip one leading and one trailing newline from each argument. A reply with no tool call gets the tool result `error: no tool call found; reply with exactly one tool call`.
  - `Workspace(files: dict[str, str])`, where `apply(call) -> str` returns the tool result text:
    - `read_file` returns `"[tool_result read_file path=<p>]\n" + content`, unfenced.
    - `replace_in_file` requires exactly one occurrence of `old` in the **raw** file. On zero it returns `error: old text not found in <p>` and counts a `replace_miss`. On more than one it returns `error: old text is not unique`.
    - `write_file` stores the content as given, placeholders and all. That is the point.
    - `done` ends the loop.
  - `Upstream(real_call, scheme, entities)`, a callable with the `(messages, model, api_key, params=None)` signature (F-3):
    - It does **not** call `scheme.begin_request()`. Redaction (step 6) runs before the upstream call, so the loop calls `begin_request()` just before each `run_conversation`.
    - It records `sent += Σ placeholder_count(m.content)` over the `messages` it receives (what the model saw).
    - It calls `real_call(...)` and records `in_output += placeholder_count(response)`.
    - For arm (c) it sets `response = scheme.restore(response)` and records the unresolved count.
    - It returns `OpenRouterResult(response=..., model_used=..., tokens_used=...)`.
  - `run_task(task, scheme, arm, run, identity_prefix) -> TaskRun`. The loop:
    - It starts from `[system, user(task.instruction)]` with a fresh `Workspace(task.files())` and a fresh `IndexedScheme` per task-run for (b) and (c). The (c) mapping is per conversation.
    - Each turn calls `run_conversation(identity, messages, device="spike012", model, None, params, call_openrouter=upstream, profile="code")`.
    - A non-`QuerySuccessResponse` aborts. Otherwise it appends `assistant(result.response)`, applies the tool, and appends `user(tool_result)`, until `done` or `--max-turns`.
    - `messages` holds the **raw** conversation as the client would. Under (a) and (b) the assistant turn is the placeholder-bearing response. Under (c) it is the restored one.
  - Identity is `Identity(user_id=f"spike012-{nonce}-{arm}-{task.id}-{run}", role="admin")` (F-4, F-6).
- **Mirror**: `app/services/query_pipeline.py:200-213` for the `run_conversation` call shape. `scripts/measure_history_latency.py:412-434` for the upstream callable.
- **Validate**: Task 7's stubbed end-to-end test.

### Task 4: The three tasks and their checkers (AC 1)

- **File**: `scripts/spike_pii_placeholders.py`
- **Action**: UPDATE
- **Implement**: `Task(id, instruction, files, check)`. `files` are read from `tests/corpora/pii/code/` at run time. Nothing is copied: `SOURCES.md` refuses undeclared samples, so no new corpus file is added. Every checker returns `(correct: bool, reason: str)` and also fails if any placeholder remains in the target file.
  1. **`fixture`: edit a fixture.** `seed-users.json`, with the instruction "In fixtures/seed-users.json set `active` to false for the user whose username is `pobrien`. Change nothing else." Correct if `json.loads(result) == expected`, where `expected` is the original parsed with that one field flipped. This catches a whole-file write that placed `<EMAIL_ADDRESS>` anywhere.
  2. **`test`: write a test.** `billing_seed.py` (as `billing_seed.py`), with the instruction "Write tests/test_billing_contacts.py with a pytest test asserting the email and phone of the first customer in CUSTOMERS are exactly the values in billing_seed.py." The file is not executed. Correct if the new file `ast.parse`s and contains, as string literals (`ast.Constant`), the exact raw email and phone of `CUSTOMERS[0]` (Task 0 fixes the values).
  3. **`rename`: rename a field.** `staging-values.yaml`, with the instruction "Rename the key `oncall-phone` to `oncallPhone` and `SUPPORT_CONTACT_EMAIL` to `SUPPORT_EMAIL`, keeping their values." Correct if `yaml.safe_load(result) == expected`, where `expected` is the original loaded with the two keys renamed in place and the values unchanged.
  - Instructions contain no PII, so the task statement itself is never redacted. Only file content is.
- **Validate**: Task 7's checker tests, which cover a correct artifact, a placeholder-bearing artifact and a wrong edit for each task.

### Task 5: Report and raw results (AC 2)

- **File**: `scripts/spike_pii_placeholders.py`
- **Action**: UPDATE
- **Implement**:
  - A header with the model, date, runs, max turns, temperature, the `code` policy's entities and threshold, Presidio/spaCy versions (`importlib.metadata`, as `measure_pii_latency._version` does) and the git SHA.
  - **Table 1 (per arm × task)**: correct/runs, placeholders sent to the model, **placeholders in model output**, placeholders in the final artifact, unresolved placeholders ((c) only), `replace_miss` count, mean turns, abort causes.
  - **Table 2 (per arm)**: `success(arm)` as a count and a rate.
  - A **Decision rules** block that computes R0-R5 and prints the resulting decision and the rule that fired. The script states the decision, and the record adopts it.
  - A validity warning: any task with `sent == 0` under (a) is flagged `INVALID`.
  - `--json` writes every `TaskRun`: counts, outcome, reason, turns. Values are not written, and neither are transcripts unless `--transcripts` is given.
- **Mirror**: `scripts/measure_pii_latency.py:1053-1186` (`_report`)
- **Validate**: Task 7's report test over a hand-built list of `TaskRun`s asserts the rule outcomes for each branch R0-R5.

### Task 6: Keep the script out of CI collection (AC 5)

- **File**: `tests/test_spike_pii_placeholders.py`
- **Action**: CREATE (the guard lives with Task 7's tests)
- **Implement**:
  - `test_the_spike_is_not_collected`: `subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "scripts"], cwd=_REPO_ROOT)` returns exit code 5 (no tests collected). Also assert `not Path("scripts/spike_pii_placeholders.py").name.startswith("test_")`.
  - `test_importing_the_spike_builds_no_analyzer_and_opens_no_connection`: fresh-interpreter probe, as in the STORY-003 test.
- **Validate**: `pytest -q tests/test_spike_pii_placeholders.py -k collected`

### Task 7: Offline tests for the pure parts

- **File**: `tests/test_spike_pii_placeholders.py`
- **Action**: UPDATE
- **Implement** (no network, and no NER model, because the `code` policy uses the tokenizer-only analyzer):
  - **Parity**: for every file in `tests/corpora/pii/code/` and `json/`, `FixedScheme().redact(text, code_policy) == redact_for_policy(text, code_policy)`. For `IndexedScheme`, stripping `_\d+` from its output gives exactly `redact_for_policy`'s output. This proves (b) and (c) differ from (a) **only** in the placeholder string (F-2).
  - **Numbering**: the same value maps to the same `n`, and distinct values get distinct `n` per type. Numbering is by first appearance. **Prefix stability**: redacting `[m1, m2]` and then `[m1, m2, m3]` with `begin_request()` between them gives identical outputs for `m1, m2`.
  - **(b) vs (c)**: after `begin_request()`, a non-persistent scheme restarts at 1 and a persistent one does not.
  - **JSON**: a phone stored as a JSON number becomes `"<PHONE_NUMBER_1>"` and the document still parses (`tests/corpora/pii/json/` has the case). `restore` turns `"<PHONE_NUMBER_1>"` back into the bare number token.
  - **Restore**: known placeholders are restored, and unknown `<EMAIL_ADDRESS_9>` stays and is counted.
  - **Parser**: each of the four tags parses. A placeholder inside `<content>` stays content. Text around the call is ignored. A missing tag gives `ParseError`.
  - **Workspace**: `replace_in_file` hits, misses, and non-unique cases.
  - **Checkers**: correct, placeholder-bearing and wrong-edit artifacts for each of the three tasks.
  - **Rules**: R0-R5 over synthetic `TaskRun` lists.
  - **Stubbed end-to-end** (needs the libSQL dev server, like the rest of the suite; mirror the DB fixture in `tests/conftest.py`): a scripted stub model (`read_file`, then `write_file` echoing what it read, then `done`) runs task `fixture` under (a), (b) and (c) through the real `run_conversation(profile="code")`.
    - (a) and (b): the artifact contains placeholders, `correct is False` and `sent > 0`.
    - (c): the artifact is restored and `correct is True`.
    - This pins that the patch reaches step 6 and that the upstream wrapper restores before the pipeline returns.
- **Mirror**: `tests/test_measure_pii_latency.py:13-40`, `tests/test_pii_structure_safe.py` (corpus iteration)
- **Validate**: `pytest -q tests/test_spike_pii_placeholders.py`, then `pytest -q` for the whole suite green, with no existing assertion changed.

### Task 8: Run the spike against a live model

- **Action**: run, not code.
- **Implement**:
  - `OPENROUTER_API_KEY=… python scripts/spike_pii_placeholders.py --model <slug> --runs 3 --json <scratch>/d5-results.json`
  - Use one current, capable coding model as the primary run. If R0 fails, re-run once with a stronger model and record both. Optionally run a second model family for robustness. The decision uses the primary model and the record says which one it was.
  - Check no task is `INVALID`. If one is, fix that task's target in Task 4, re-run the offline tests, and run again.
- **Validate**: the report printed, a decision computed, and the JSON written.

### Task 9: Decision record and PRD link (AC 3, 4)

- **File**: `.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md`
- **Action**: CREATE
- **Implement**, with these sections:
  - **Question**: D5 and F10.
  - **Method**: the arms (including why control exists), the tool protocol and system prompt verbatim, the three tasks and checkers, the per-task-run identity, temperature, max turns and runs. Include the limitations:
    - a text tool protocol, not native `tool_calls`, which PRD-016 will make un-redacted;
    - `tool` results sent as `user` turns (step 0);
    - small N;
    - one model family.
  - **Model**: the exact slug(s) and date.
  - **Raw results**: Tables 1 and 2 pasted verbatim, plus the per-task-run JSON inline or summarized with counts.
  - **Decision**: the rule that fired (R0-R5) and the outcome.
  - **Why (c) is or is not adopted**: in every branch, state that a reversible mapping is PII at rest (T8). It is a server-side store of real values, keyed by conversation, that must outlive a request, and it needs retention, deletion on session delete, access control, and exclusion from logs and audit. PRD-012 does not build it, and the evidence either does not require it or hands it to a later PRD (R4).
  - **Consequences**:
    - decision (a): "no production code changes" (AC 4);
    - decision (b): the follow-up story's id and scope;
    - any Future Considerations.
- **File**: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`
- **Action**: UPDATE. In Section 15, append "→ [decisions/D5-placeholders.md](./decisions/D5-placeholders.md)" with a one-clause outcome to the D5 row, and add the record under *Related documents*. If the decision is not (a), also update the Section 13 bullet "Indexed or reversible placeholders".
- **If decision (b)**: create `.agents/stories/PRD-012-pii-for-code/STORY-015-indexed-placeholders.md` (`status: todo`, `depends_on: [STORY-012]`), with the scope taken from the record. Add it to `index.md`. Implement nothing (AC 4).
- **Validate**: `git diff --stat` shows no `app/` or `chat_ui/` path. The record has all six section headings, and the PRD link resolves.

---

## End-to-End Tests

- [ ] `python scripts/spike_pii_placeholders.py --help` exits 0. With no API key it exits non-zero, naming `OPENROUTER_API_KEY`.
- [ ] With a non-local `--database-url` and no `--allow-remote-database`, the script refuses.
- [ ] Offline: `pytest -q tests/test_spike_pii_placeholders.py` passes against the libSQL dev server, with no network access.
- [ ] `pytest --collect-only -q scripts` collects no tests (exit 5), and `pytest -q` (the CI command) is green.
- [ ] Live: a run with `--model <slug> --runs 3` completes all four arms × three tasks. Every row shows `sent > 0` for (a), (b) and (c). The report prints placeholders-in-output and correctness per arm, plus a computed decision.
- [ ] `D5-placeholders.md` records method, raw results, model, decision and the (c) at-rest reasoning. PRD Section 15 links it.
- [ ] `git diff --stat epic/PRD-012-pii-for-code~1..HEAD -- app chat_ui` is empty.

---

## Validation

```bash
python scripts/spike_pii_placeholders.py --help
pytest -q tests/test_spike_pii_placeholders.py
pytest --collect-only -q scripts; test $? -eq 5
pytest -q
git diff --stat -- app chat_ui   # must be empty
```

---

## Risks + Mitigations

| Risk | Mitigation |
|------|-----------|
| The tasks never put a placeholder in front of the model (a fenced read, a threshold miss), so every arm looks equal | Tool results are unfenced (F-5). Task 0 proves each file yields entities under `code`. The report marks `sent == 0` as `INVALID` and the rules refuse to decide on it |
| The model fails the tasks for reasons unrelated to PII | The control arm and R0. A failed control is "inconclusive", not "(a) is fine" |
| The spike's (b)/(c) drift from production span logic, so it measures something else | It reuses `pii_redactor`'s private pipeline instead of copying it, and a parity test pins fixed == `redact_for_policy` and indexed-minus-suffix == `redact_for_policy` over all corpora |
| Coupling to `pii_redactor` privates breaks the script later | The parity test fails loudly in CI if the privates change shape. The script is a spike, and that coupling is acceptable and stated in its docstring |
| The duplicate check blocks the second arm | A per-task-run user id (F-4), with every non-success result recorded as an abort |
| Nondeterminism and small N | Temperature 0 by default, 3 runs, whole-task thresholds in the rules, raw counts next to rates, and the caveat stated in the record |
| Cost / runaway loops | `--max-turns 8`, 4 arms × 3 tasks × 3 runs ≤ 288 calls, `max_tokens` capped |
| The text protocol is not how PRD-014 clients will call tools | Stated as a method limitation. The redaction surface it exercises (file content in turns, model-written file content) is the one D1 and D5 are about |
| The live key leaks into the repo | The key is read from the environment only. `--json` holds counts, not values. Transcripts are opt-in and go to a directory outside the repo |

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given `scripts/spike_pii_placeholders.py`, when it runs with an OpenRouter key, then it drives at least three scripted multi-turn agent tasks (for example, edit a fixture, write a test, rename a field) through `run_conversation(profile="code")`, feeding each response back as history, for each of: (a) fixed `<TYPE>`, (b) indexed per request `<TYPE_n>` numbered by first appearance across the conversation, (c) reversible with an in-memory mapping.
- [ ] Given each run, when it completes, then the script reports, per option, the number of placeholders that appear in model output and whether the task's final artifact is correct.
- [ ] Given `.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md`, when it is read, then it records the method, the raw results, the model used, the decision, and why option (c) is or is not adopted, given that a stored mapping is PII at rest.
- [ ] Given the decision is (a), when this story lands, then no production code changes. Given it is (b), then the decision record names the follow-up story instead of implementing it here.
- [ ] Given CI, when the suite runs, then the spike script is not collected as a test.
- [ ] All tasks completed
- [ ] Full suite (`pytest -q`) passes
- [ ] No file under `app/` or `chat_ui/` changed
- [ ] Follows existing patterns (`scripts/measure_*` spike shape, `tests/test_measure_pii_latency.py` test shape)
