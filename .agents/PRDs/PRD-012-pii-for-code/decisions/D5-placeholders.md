# D5: Fixed, indexed or reversible PII placeholders under `code`

**Status**: decided, 2026-09-25 · **Story**: [STORY-012](../../../stories/PRD-012-pii-for-code/STORY-012-placeholder-spike.md) · **PRD**: [PRD-012](../PRD.md) Section 7 (F10), Section 9.2 (T8), Risk 7, Section 15 (D5)

**Decision: keep fixed `<TYPE>` placeholders (a) as the default in PRD-012.** Rule **R4** fired. Fixed (a) and indexed (b) placeholders both break agent tasks, and only reversible placeholders (c) match the unredacted control. (c) is **justified by the data but not adopted here**: its mapping is PII at rest, and a store of real values needs an owner that PRD-012 is not (see [Why (c) is not adopted](#why-c-is-not-adopted-in-prd-012)). No production code changes in this story.

---

## Question

Under the `code` profile, input redaction replaces an email with `<EMAIL_ADDRESS>` before the model sees it, and output redaction is off (D1). The PRD predicts two failures for a coding agent. A search-and-replace edit quotes the placeholder and so fails to match the file on disk. A whole-file write puts the placeholder into the user's repository. F10 asks whether that makes agents unusable, and whether one of two alternatives fixes it:

- **(a) fixed** `<TYPE>`, today's behaviour;
- **(b) indexed per request** `<TYPE_n>`, numbered by first appearance across the conversation. There is no stored mapping: the whole conversation is re-redacted on every send, so the numbering is deterministic;
- **(c) reversible**: `<TYPE_n>` from a per-conversation mapping, with placeholders restored in the output.

The PRD's standing rule: (a) stays unless the evidence shows (a) makes agents unusable, and (c) is ruled out unless (a) and (b) both fail, because a stored mapping is PII at rest (T8).

## Method

**Script**: [`scripts/spike_pii_placeholders.py`](../../../../scripts/spike_pii_placeholders.py). Offline tests are in [`tests/test_spike_pii_placeholders.py`](../../../../tests/test_spike_pii_placeholders.py). The script is never collected by CI.

**Loop.** A small agent loop sends every turn through the real `run_conversation(profile="code")`, so step 6 redacts exactly as it would for a PRD-014 client. The model answers with one tool call per reply. The script applies the call to an in-memory workspace of the **raw** files and sends the tool's result back as the next `user` turn. Each response is appended to the history as it came back from the pipeline. The loop stops at `<done/>` or after 8 turns.

**Arms**:

| Arm | What step 6 does | How |
|---|---|---|
| control | nothing is masked | `query_pipeline._redact` patched to identity. This is the baseline that separates "the model cannot do the task" from "placeholders stopped it". Every value in the corpus is synthetic (`tests/corpora/pii/SOURCES.md`) |
| a | `<TYPE>` | production, unpatched |
| b | `<TYPE_n>`, renumbered per send | `_redact` swapped for a scheme that runs `pii_redactor`'s own span pipeline and changes only the placeholder string. Its numbering state is cleared before every send |
| c | `<TYPE_n>` from a mapping kept per task conversation | the same scheme with the state kept. The injected upstream restores `<TYPE_n>` in the response before the pipeline returns it. The mapping lives in the script's memory only |

A parity test pins (b) and (c) to production. Over every file in `tests/corpora/pii/code/` and `json/`, the fixed scheme's output equals `redact_for_policy`'s. With the `_n` suffix removed, the indexed scheme's output equals it too. Structure-safe splitting, fence skipping and JSON clipping are production's own.

**System prompt** (a `system` turn, not redacted under `code`, D3), verbatim:

```text
You are a coding agent working in a small repository. You act only through tools.

Reply with exactly one tool call per message, written as plain text in these tags. Do not wrap tool calls in Markdown code fences.

<read_file><path>relative/path</path></read_file>
  Returns the file's current contents.

<replace_in_file><path>relative/path</path><old>exact existing text</old><new>replacement text</new></replace_in_file>
  Replaces one occurrence of the old text. The old text must match the file exactly, including whitespace, and must occur exactly once.

<write_file><path>relative/path</path><content>full file contents</content></write_file>
  Creates or overwrites the whole file.

<done/>
  Call this when the task is complete.

Read a file before you change it. You may write a short sentence before the tool call, but nothing after it.
```

**Tasks.** They are built on existing `tests/corpora/pii/code/` files. The instructions carry no PII (a test pins this), so only file content is ever masked.

| Task | File | Instruction | Correct if |
|---|---|---|---|
| fixture (edit a fixture) | `seed-users.json` | set `active` to false for username `pobrien`, change nothing else | `json.loads(result)` equals the original with that one field flipped |
| test (write a test) | `billing_seed.py` | write `tests/test_billing_contacts.py` asserting the first customer's email and phone as string literals | it `ast.parse`s and contains `"jane.doe@example.com"` and `"+1 415 555 0134"` as string constants |
| rename (rename a field) | `staging-values.yaml` | rename `oncall-phone` → `oncallPhone` and `SUPPORT_CONTACT_EMAIL` → `SUPPORT_EMAIL`, keeping values | `yaml.safe_load(result)` equals the original with those two keys renamed |

Every checker also fails if a placeholder is left in the target file. A task-run that aborts is incorrect even if the workspace passes. Aborts are the turn cap, a non-success pipeline result, or an upstream error.

**Settings**: temperature 0, `max_tokens` 4096, 3 runs per task per arm, and a fresh user id per task-run. The fresh id stops step 4's duplicate check from blocking the second arm, and the conversation text is never altered to avoid it. The `code` policy ran as shipped: `EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`, threshold 0.40, fenced blocks skipped, output not redacted. Versions: presidio-analyzer 2.2.364, spaCy 3.8.16, Python 3.11.9, at epic commit `41c4cc3` plus this story's uncommitted script.

**Decision rules**: written in the [plan](../../../plans/PRD-012-pii-for-code/completed/STORY-012-placeholder-spike.plan.md#decision-rules-written-before-measuring) before any number was taken, and computed by the script:

- An arm **fails** (R1) if its success is below control's minus 1/3, **or** some task is incorrect in every run under it while control gets that task right in at least half its runs.
- **R0**: control < 2/3 → inconclusive.
- **R2**: (a) does not fail → (a).
- **R3**: (a) fails and (b) does not → (b), with a follow-up story.
- **R4**: (a) and (b) fail and (c) does not → (c) justified, not adopted in PRD-012.
- **R5**: all three fail → (a).

A task where (a) never put a placeholder in front of the model makes the run invalid.

**Limitations, stated plainly**:
- **Text tool protocol.** The tools are text tags in the reply, not native `tool_calls`. PRD-016 will make tool-call *arguments* never redacted, but the file content an agent *reads* stays in redacted turns, and that content is what this spike exercises.
- **Tool results sent as `user` turns.** Step 0 refuses `tool` turns until PRD-016. Both roles are covered by `code` with the same policy, so the redaction is identical.
- **Small N.** 9 task-runs per arm per model. The rules act on whole tasks, not percentages, and every rate below sits next to its raw count.
- **Three short tasks.** Real agent sessions are longer, which gives placeholders more chances to appear. The result is more likely a floor on the damage than a ceiling.
- **Local environment**: the machine running the spike has antivirus HTTPS scanning that intermittently presents its own root certificate. The runs used `SSL_CERT_FILE` pointing at certifi plus the Windows root store. Verification stayed on, and `app/` was unchanged.

## Model

- **Primary**: `anthropic/claude-sonnet-5` via OpenRouter, run on 2026-09-25 from 21:27 UTC. 36 task-runs, 598,962 tokens.
- **Robustness**: `openai/gpt-5.6-sol` via OpenRouter, run on 2026-09-25 (see [Second model](#second-model-openaigpt-56-sol)).

The decision is taken on the primary model, as the plan specifies.

## Raw results: `anthropic/claude-sonnet-5`

### Per arm and task

"Sent" is the placeholder count in the largest request the model received. "In model output" sums placeholders across every raw response. For (c), responses are counted before restoration.

| Arm | Task | Correct | Sent to model (max) | In model output | In artifact | Unresolved (c) | Replace misses | Parse errors | Mean turns | Aborts |
|---|---|---|---|---|---|---|---|---|---|---|
| control | fixture | 3/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3.0 | - |
| control | test | 3/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3.0 | - |
| control | rename | 3/3 | 0 | 0 | 0 | 0 | 0 | 0 | 4.0 | - |
| a | fixture | 1/3 | 66 | 16 | 0 | 0 | 8 | 0 | 6.7 | upstream error: OpenRouter returned no text content (finish_reason=stop) |
| a | test | 0/3 | 25 | 8 | 6 | 0 | 0 | 0 | 3.0 | - |
| a | rename | 2/3 | 70 | 6 | 0 | 0 | 3 | 0 | 4.3 | upstream error: OpenRouter returned no text content (finish_reason=stop) |
| b | fixture | 0/3 | 88 | 44 | 20 | 0 | 10 | 0 | 8.0 | no <done/> within 8 turns |
| b | test | 0/3 | 23 | 4 | 4 | 0 | 0 | 0 | 3.0 | - |
| b | rename | 3/3 | 73 | 13 | 0 | 0 | 6 | 0 | 7.0 | - |
| c | fixture | 3/3 | 22 | 6 | 0 | 0 | 0 | 0 | 3.0 | - |
| c | test | 3/3 | 23 | 6 | 0 | 0 | 0 | 0 | 3.0 | - |
| c | rename | 3/3 | 38 | 12 | 0 | 0 | 0 | 0 | 4.0 | - |

### Per arm

| Arm | Correct | Rate | Placeholders in model output |
|---|---|---|---|
| control | 9/9 | 1.00 | 0 |
| a | 3/9 | 0.33 | 30 |
| b | 3/9 | 0.33 | 61 |
| c | 9/9 | 1.00 | 24 |

### Per task-run

| Arm | Task | Run | Correct | Turns | Sent | In output | In artifact | Unresolved | Replace misses | Tokens | Reason / abort |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | fixture | 1 | yes | 3 | 0 | 0 | 0 | 0 | 0 | 6934 | ok |
| a | fixture | 1 | yes | 7 | 46 | 6 | 0 | 0 | 3 | 34576 | ok |
| b | fixture | 1 | no | 8 | 48 | 10 | 0 | 0 | 4 | 41638 | parsed document differs from the expected edit; aborted: no <done/> within 8 turns |
| c | fixture | 1 | yes | 3 | 22 | 2 | 0 | 0 | 0 | 7315 | ok |
| control | test | 1 | yes | 3 | 0 | 0 | 0 | 0 | 0 | 9851 | ok |
| a | test | 1 | no | 3 | 25 | 4 | 2 | 0 | 0 | 10142 | 2 placeholder(s) in the artifact, e.g. <EMAIL_ADDRESS> |
| b | test | 1 | no | 3 | 23 | 2 | 2 | 0 | 0 | 10136 | 2 placeholder(s) in the artifact, e.g. <EMAIL_ADDRESS_2> |
| c | test | 1 | yes | 3 | 23 | 2 | 0 | 0 | 0 | 10142 | ok |
| control | rename | 1 | yes | 4 | 0 | 0 | 0 | 0 | 0 | 10037 | ok |
| a | rename | 1 | no | 3 | 70 | 2 | 0 | 0 | 1 | 7105 | parsed document differs from the expected rename; aborted: upstream error: OpenRouter returned no text content (finish_reason=stop) |
| b | rename | 1 | yes | 7 | 72 | 4 | 0 | 0 | 2 | 32980 | ok |
| c | rename | 1 | yes | 4 | 38 | 4 | 0 | 0 | 0 | 10701 | ok |
| control | fixture | 2 | yes | 3 | 0 | 0 | 0 | 0 | 0 | 6935 | ok |
| a | fixture | 2 | no | 6 | 64 | 4 | 0 | 0 | 2 | 27132 | parsed document differs from the expected edit; aborted: upstream error: OpenRouter returned no text content (finish_reason=stop) |
| b | fixture | 2 | no | 8 | 46 | 6 | 0 | 0 | 3 | 42063 | parsed document differs from the expected edit; aborted: no <done/> within 8 turns |
| c | fixture | 2 | yes | 3 | 22 | 2 | 0 | 0 | 0 | 7315 | ok |
| control | test | 2 | yes | 3 | 0 | 0 | 0 | 0 | 0 | 9855 | ok |
| a | test | 2 | no | 3 | 23 | 2 | 2 | 0 | 0 | 10254 | 2 placeholder(s) in the artifact, e.g. <EMAIL_ADDRESS> |
| b | test | 2 | no | 3 | 23 | 2 | 2 | 0 | 0 | 10136 | 2 placeholder(s) in the artifact, e.g. <EMAIL_ADDRESS_2> |
| c | test | 2 | yes | 3 | 23 | 2 | 0 | 0 | 0 | 10141 | ok |
| control | rename | 2 | yes | 4 | 0 | 0 | 0 | 0 | 0 | 10038 | ok |
| a | rename | 2 | yes | 5 | 36 | 2 | 0 | 0 | 1 | 14023 | ok |
| b | rename | 2 | yes | 7 | 73 | 5 | 0 | 0 | 2 | 33009 | ok |
| c | rename | 2 | yes | 4 | 38 | 4 | 0 | 0 | 0 | 10701 | ok |
| control | fixture | 3 | yes | 3 | 0 | 0 | 0 | 0 | 0 | 6935 | ok |
| a | fixture | 3 | no | 7 | 66 | 6 | 0 | 0 | 3 | 36847 | parsed document differs from the expected edit; aborted: upstream error: OpenRouter returned no text content (finish_reason=stop) |
| b | fixture | 3 | no | 8 | 88 | 28 | 20 | 0 | 3 | 54760 | 20 placeholder(s) in the artifact, e.g. <EMAIL_ADDRESS_1> |
| c | fixture | 3 | yes | 3 | 22 | 2 | 0 | 0 | 0 | 7179 | ok |
| control | test | 3 | yes | 3 | 0 | 0 | 0 | 0 | 0 | 9851 | ok |
| a | test | 3 | no | 3 | 23 | 2 | 2 | 0 | 0 | 10126 | 2 placeholder(s) in the artifact, e.g. <EMAIL_ADDRESS> |
| b | test | 3 | no | 3 | 21 | 0 | 0 | 0 | 0 | 11893 | 2 expected literal(s) missing |
| c | test | 3 | yes | 3 | 23 | 2 | 0 | 0 | 0 | 10148 | ok |
| control | rename | 3 | yes | 4 | 0 | 0 | 0 | 0 | 0 | 10037 | ok |
| a | rename | 3 | yes | 5 | 36 | 2 | 0 | 0 | 1 | 14119 | ok |
| b | rename | 3 | yes | 7 | 72 | 4 | 0 | 0 | 2 | 33207 | ok |
| c | rename | 3 | yes | 4 | 38 | 4 | 0 | 0 | 0 | 10701 | ok |

### What the transcripts show

These were read from the per-task-run transcripts. They were kept outside the repository and are not checked in.

- **The PRD's search-and-replace failure is real.** In (a)/fixture, the model's `replace_in_file` quotes lines like `"mobile": "<PHONE_NUMBER>",` as the text to replace. That never matches the raw file, so the tool returns `old text not found`. The model re-reads, sees the same placeholder, and tries again. There were 8 misses across 3 runs under (a) and 10 under (b). In one (a) run the model then settled for a nearby edit that changed the file incorrectly.
- **The placeholder reaches disk.** In every (a)/test run the model wrote `assert first.email == "<EMAIL_ADDRESS>"` and `assert first.phone == "<PHONE_NUMBER>"` into the new test file. Under (b) it wrote `"<EMAIL_ADDRESS_2>"`. The (c) file has `"jane.doe@example.com"` and `"+1 415 555 0134"`.
- **Indexing does not help, and can hurt.** (b) makes a placeholder look like a real, unique token, so the model copies it more readily: 61 placeholders in output against 30 under (a). In (b)/fixture/run 3 it gave up on edits and rewrote the whole file, which put 20 placeholders on disk. In (b)/test/run 3 the model noticed the values were masked and wrote a test that parses `billing_seed.py` at runtime instead of asserting literals. That is a reasonable workaround, but it is not the task.
- **(a)'s three aborts are empty replies** (`finish_reason=stop` with no content) after repeated replace misses. They occur only in (a). The decision does not depend on them: if all three had counted as correct, (a) would still fail R1's second test, because (a)/test is incorrect in every run while control gets it right in all three.
- **(c) is not a leak-free comparison either.** The model still *sees* `<TYPE_n>`: 24 in its output, all resolved (0 unresolved). It succeeds only because the script restores values after the model has written them.

## Second model: `openai/gpt-5.6-sol`

Run on 2026-09-25 from 21:40 UTC with the same script, settings and commit. 36 task-runs, 425,740 tokens. **The script's computed decision is the same: R4.** Here it fires through R1's second test rather than the success gap.

| Arm | Task | Correct | Sent to model (max) | In model output | In artifact | Unresolved (c) | Replace misses | Parse errors | Mean turns | Aborts |
|---|---|---|---|---|---|---|---|---|---|---|
| control | fixture | 3/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3.0 | - |
| control | test | 3/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3.0 | - |
| control | rename | 3/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3.0 | - |
| a | fixture | 3/3 | 42 | 6 | 0 | 0 | 6 | 0 | 6.3 | - |
| a | test | 0/3 | 23 | 6 | 6 | 0 | 2 | 0 | 5.7 | - |
| a | rename | 3/3 | 70 | 2 | 0 | 0 | 4 | 0 | 5.7 | - |
| b | fixture | 3/3 | 42 | 4 | 0 | 0 | 5 | 0 | 6.0 | - |
| b | test | 0/3 | 25 | 10 | 6 | 0 | 2 | 0 | 6.0 | - |
| b | rename | 3/3 | 70 | 4 | 0 | 0 | 5 | 0 | 6.3 | - |
| c | fixture | 3/3 | 40 | 24 | 0 | 0 | 2 | 0 | 4.0 | - |
| c | test | 3/3 | 23 | 6 | 0 | 0 | 1 | 0 | 5.7 | - |
| c | rename | 3/3 | 68 | 38 | 0 | 0 | 2 | 0 | 5.3 | - |

| Arm | Correct | Rate | Placeholders in model output |
|---|---|---|---|
| control | 9/9 | 1.00 | 0 |
| a | 6/9 | 0.67 | 14 |
| b | 6/9 | 0.67 | 18 |
| c | 9/9 | 1.00 | 68 |

The script's decision line: "(a) fails (task test incorrect in every run while control is correct in 1); (b) fails (task test incorrect in every run while control is correct in 1); (c) does not (success 1 vs control 1)".

**How the two models differ.** This model recovers from a missed `replace_in_file` better. It re-reads the file and then quotes a shorter span with no placeholder in it, so fixture and rename pass under (a) and (b) despite 4-6 misses each. It can't recover when the task needs the masked value itself. Every (a) and (b) test file asserts `"<EMAIL_ADDRESS>"` / `"<EMAIL_ADDRESS_2>"`, just as with the primary model. So the damage from placeholders depends on the model for **edits**, but not for **writing the value**. Once a task needs the value, fixed and indexed placeholders fail on both models.

## Decision

**R4 fired: (a) fails, (b) fails, (c) does not.**

- (a): success 3/9, against control 9/9 − 1/3 = 6/9. It fails.
- (b): success 3/9. It fails.
- (c): success 9/9, equal to control. It does not fail.
- The robustness model, `openai/gpt-5.6-sol`, reaches the same rule: (a) 6/9, (b) 6/9, (c) 9/9, control 9/9. Its test task fails in every run under both (a) and (b).

Under the PRD's rule, that outcome makes (c) **justified by the data**. PRD-012 does **not adopt it**, and the default stays **(a) fixed `<TYPE>`** until a later PRD builds (c) with the safeguards below. No production code changes in this story (STORY-012 AC 4). No follow-up story is created inside PRD-012: the rule that names one applies to decision (b), which was not reached.

### Why (c) is not adopted in PRD-012

Reversible placeholders only work if the server remembers, for the life of a conversation, which real value each `<TYPE_n>` stands for. In the spike that mapping was a dict in one process. In production it would be:

- **A new store of PII at rest** (T8). It holds exactly the values redaction exists to keep from the provider, collected in one place and keyed by conversation. It is a better target than the data it protects.
- **Long-lived.** A PRD-014 `/v1` client sends its own history on every step. The mapping must outlive each request and be shared by every worker and instance, so it cannot stay in process memory. It needs the database, or another shared store with its own credentials.
- **In need of an owner.** Retention and expiry, deletion when the session or user is deleted, access control, encryption at rest, and exclusion from logs, audit rows and `/audit`. Today `audit_logs.prompt` holds the raw prompt, and adding a mapping table would widen what the admin surfaces can reach.
- **A new failure mode.** It adds a decision on every response: restore or not. A model that invents `<EMAIL_ADDRESS_7>`, or echoes another conversation's placeholder, must never be resolved against the wrong mapping, so per-conversation isolation becomes a correctness property.

None of this fits PRD-012's scope ("redaction policy by profile, role and direction"), and PRD-013 is already redesigning per-request telemetry and storage. The decision is therefore: **(c) goes to a later PRD, as a designed feature with its own threat model.** It is not a flag added here.

### Consequences

- **The `code` profile ships with fixed placeholders.** For PII that reaches a redacted turn, this evidence shows that coding agents will often fail edits or write placeholders into files. The README (STORY-014) must say so plainly, next to D1 and D2. The mitigations available today:
  - PII inside fenced blocks is not redacted (D2);
  - the entity list is pattern-only, so names and identifiers are not masked (D7);
  - an operator whose agents mostly handle synthetic fixtures can narrow `PII_ENTITIES_CODE`.
- **Future Considerations (PRD Section 13)**: "Indexed or reversible placeholders" becomes "**Reversible placeholders (D5: justified by STORY-012's spike, not adopted)**", with the at-rest requirements above as its entry criteria. Indexed placeholders are dropped: they did no better than fixed ones.
- **Input to PRD-014.** An agent that sends `tool` turns will see placeholders in every file it reads that contains an email or a phone number. PRD-014's rollout note should point here.
