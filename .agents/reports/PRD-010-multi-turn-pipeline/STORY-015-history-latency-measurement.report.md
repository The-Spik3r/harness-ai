---
story: STORY-015
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-015-history-latency-measurement.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 0a95158
status: COMPLETE
completed: 2026-09-19
---

# Implementation Report — STORY-015: Measure added per-send latency of history assembly and per-turn redaction at 20 exchanges

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-015-history-latency-measurement.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `0a95158`

## Summary

`scripts/measure_history_latency.py` seeds a session with 20 answered exchanges into the local libSQL dev server and times 30 sends through the real `chat_history.assemble`, the real `pii_redactor.redact` and the real `run_conversation` with a stub upstream, reporting p50/p95 for each layer against a single-turn baseline.

**The PRD Section 11 indicator holds.** Added per-send latency is **926.05 ms at p50**, and one `messages_for` read (5.17 ms) plus the extra per-turn redaction (927.22 ms) accounts for **932.38 ms** of it. Nothing in the added cost is unexplained: the history path costs exactly the two things the indicator names and nothing else. Per AC 2 and the plan's Task 9, **no PRD Section 13 edit was made.**

**Two findings sit alongside that pass, and both matter more than the pass does.** First, the absolute figure is large — roughly **0.93 s added to every send** at 20 exchanges, growing linearly at ~23 ms per message, with redaction accounting for **97%** of the whole pipeline cost excluding upstream. Second, **PRD Risk 3's assumption that assistant turns are cheap to analyse is wrong**: they cost the same as user turns. Both are set out under [Recommendation](#recommendation) below; acting on either is a decision for the PRD owner, not this spike.

## Measured latency

Two consecutive runs, the second reported per the plan's Task 7. The runs agree within 3 ms at p50, which is also the evidence that cleanup works (arm (a) did not degrade between them).

Run parameters, identical across both runs:

```
--- STORY-015 history latency (PRD-010 Section 11, Risk 3) ---

  endpoint             : http://127.0.0.1:8080 (same host)
  python               : 3.11.9 on Windows
  exchanges seeded     : 20
  sends per arm        : 30 (plus one discarded warm iteration)
  conversation sent    : 41 messages, 19193 characters
  CONTEXT_MAX_MESSAGES : 100
  CONTEXT_MAX_CHARACTERS: 200000
  PII_REDACTION_ENABLED: True
  PII_NLP_MODEL        : en_core_web_lg
  PII_ENTITIES         : PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION
  redact() calls/send  : 41 history+new, +1 on the response

  history send SQL     : SELECT chat_messages, SELECT audit_logs, INSERT audit_logs
  single-turn send SQL : SELECT audit_logs, INSERT audit_logs
```

Run 2, verbatim:

```
  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1].
  No latency here is asserted as a pass/fail bound.

  History path (20 exchanges):
  | arm | n | min (ms) | p50 (ms) | p95 (ms) |
  |-----|---|----------|----------|----------|
  | (a) assemble + fit | 30 | 3.97 | 5.17 | 6.99 |
  | (b) redact all messages | 30 | 924.33 | 952.75 | 984.72 |
  | (c) run_conversation excl. upstream | 30 | 953.13 | 978.28 | 1017.12 |

  Single-turn baseline:
  (a') assemble + fit: n/a -- a single-turn send reads no history, which is the whole of the difference arm (a) measures.
  | arm | n | min (ms) | p50 (ms) | p95 (ms) |
  |-----|---|----------|----------|----------|
  | (b') redact one message | 30 | 24.10 | 25.53 | 27.91 |
  | (c') run_conversation excl. upstream | 30 | 48.46 | 52.24 | 55.90 |

  added per send (p50) : 926.05 ms (978.28 - 52.24)
  added per send (p95) : 961.22 ms
  accounted for by     : 932.38 ms = assemble 5.17 + extra redaction 927.22
```

### The three arms, multi-turn against single-turn

| Arm | 20 exchanges (41 messages) | Single turn (1 message) | Added |
|---|---|---|---|
| (a) `assemble` + `fit` | p50 **5.17 ms**, p95 6.99 ms | n/a — reads nothing | +5.17 ms |
| (b) redaction of all messages | p50 **952.75 ms**, p95 984.72 ms | p50 25.53 ms, p95 27.91 ms | +927.22 ms |
| (c) whole `run_conversation` excl. upstream | p50 **978.28 ms**, p95 1017.12 ms | p50 52.24 ms, p95 55.90 ms | **+926.05 ms** |

Run 1, for comparison: (a) 5.18 / 7.08, (b) 951.89 / 1018.05, (c) 981.36 / 1018.00; single-turn (b') 25.35, (c') 52.80; added 928.56 ms p50.

### Verdict against PRD Section 11

> Added latency per chat send at most one `messages_for` read plus per-turn redaction, measured and recorded in the STORY-015 report at 20 exchanges

**It holds, with numbers.** Added latency is 926.05 ms at p50; one `messages_for` read plus the extra per-turn redaction is 932.38 ms. The added cost is 99.3% of its own explanation, and the 6 ms shortfall is measurement noise between separately-timed arms, not a saving. There is no third cost — no extra round trip, no per-message DB work, no hidden re-read.

The statement lists are what prove the *read* half rather than merely timing it: a history send issues `SELECT chat_messages, SELECT audit_logs, INSERT audit_logs` and a single-turn send issues `SELECT audit_logs, INSERT audit_logs`. **Exactly one extra SELECT, and it is `assemble`'s.** Counts are the assertable number in this repo; the latencies beside them are context (`tests/test_two_instance_smoke.py:1225-1246`).

### Caveats on the figures

- **Same host.** Both the application and libSQL ran on one machine, so arm (a)'s 5.17 ms understates a remote endpoint — a real deployment pays network latency on that read. This is the caveat STORY-011 recorded for `/stats` and it applies unchanged. It cuts one way only: **the redaction half does not change with deployment topology**, because it is local CPU. The 97% of added cost that is Presidio is 97% wherever this runs.
- **Upstream is excluded by subtraction, not by assumption.** The stub records its own `perf_counter` span and arm (c) reports `total - stub_span`, so "excluding upstream" is measured rather than asserted.
- **No latency here is asserted as a pass/fail bound**, following the house rule. These are recorded figures.
- Windows, Python 3.11.9, `en_core_web_lg`. A Linux CI box will differ in absolute terms; the ratio between the arms is the portable part.

## Recommendation

Neither item below changes any file in this commit. Both are for the PRD owner.

**1. The redaction-cache follow-up is worth opening, even though AC 2's trigger did not fire.** AC 2 opens it only if added latency *exceeds* one read plus per-turn redaction, and it does not — so no PRD edit was made here, correctly. But PRD Risk 3 names a second, softer trigger: "a per-content redaction cache is a documented follow-up **if the measurement is poor**." At 20 exchanges the measurement is ~0.93 s added to every send, scaling linearly toward roughly 2.3 s at the `CONTEXT_MAX_MESSAGES` ceiling of 100. Every one of those analyses is re-work: assistant content in `chat_messages` is *already redacted* (PRD-008 Section 9), and each history user turn was redacted on the send that created it. A per-content cache keyed on the raw string would collapse arm (b) to the cost of the one new turn — about 25 ms — and take the added per-send cost from 926 ms to roughly 30 ms. Whether that is worth a PRD-013 slot is the owner's call; the data says the ceiling is real and linear.

**2. PRD Risk 3's cost model for assistant turns is wrong, and the mitigation text should be corrected whether or not the cache is built.** Risk 3 argues the risk is bounded partly because "assistant turns are already placeholder text and cheap to analyse". They are not placeholder text — `row.content` is the model's full prose reply — and they are not cheap. Measured per message: **23.24 ms averaged across the 41-message mixed conversation (952.75 / 41), against 25.53 ms for a single user turn carrying PII.** Presidio's cost tracks character count, not entity count, so an assistant turn costs essentially what a user turn of the same length costs. The practical consequence is that history redaction is ~2× more expensive than Risk 3's reasoning implies, because it assumed half the messages were nearly free.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Script skeleton — docstring, pre-import DB bootstrap, argparse | `scripts/measure_history_latency.py` | ✅ |
| 2 | Corpus — 300–800 char prompts, PII in ~1 in 3 | `scripts/measure_history_latency.py` | ✅ |
| 3 | Seed — user, session, 20 answered exchanges | `scripts/measure_history_latency.py` | ✅ |
| 4 | Timing harness — warm-up, four arms, nearest-rank percentiles | `scripts/measure_history_latency.py` | ✅ |
| 5 | Statement-count corroboration of the `messages_for` read | `scripts/measure_history_latency.py` | ✅ |
| 6 | Cleanup in `finally` | `scripts/measure_history_latency.py` | ✅ |
| 7 | Run the measurement twice at 20×30 | — | ✅ |
| 8 | Write the report | this file | ✅ |
| 9 | Open the redaction-cache follow-up *(conditional)* | `.agents/PRDs/.../PRD.md` | ⬜ **not triggered** — the indicator holds; see Verdict |
| 10 | Prove nothing else moved | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python scripts/measure_history_latency.py --help` | ✅ exits 0, prints the `Usage:` block |
| `--show-corpus` — every string in the 300–800 band | ✅ questions 466–504 chars (486–525 with the uniqueness suffix), answers 409–510 |
| Smoke run `--exchanges 2 --sends 3` | ✅ all arms n=3, every send a `QuerySuccessResponse` |
| Full run `--exchanges 20 --sends 30`, twice | ✅ all arms n=30, no blocked iteration, no exception |
| No send blocked as a duplicate | ✅ every iteration asserted `QuerySuccessResponse`; the run would have exited non-zero otherwise |
| Statement lists | ✅ history adds exactly one `SELECT chat_messages` |
| `pytest --collect-only -q scripts/` | ✅ **no tests collected** — AC 3's exclusion |
| Full suite `pytest -q tests/` | ✅ **2224 passed, 26 skipped, 0 failed** (203.81s) — the same counts STORY-014 recorded |
| No production file modified | ✅ `git status --porcelain app/ chat_ui/ tests/` empty |

There is no linter or formatter in this repo; "validate" is pytest against the local libSQL dev server.

### A note on the environment

Docker Desktop was not running at the start of this story and the dev server container `harness-libsql-dev` was stopped, so the endpoint refused connections. Starting the daemon and the container resolved it; no code was involved. Recording it because the standing dev-server note says mass fixture errors mean restart the container rather than bisect the code, and "the container is not running at all" is the degenerate case of that same rule.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/measure_history_latency.py` | CREATE | +794 |
| `.agents/reports/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.report.md` | CREATE | this file |
| `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-015-history-latency-measurement.plan.md` | CREATE (archived from `../`) | — |
| `.agents/stories/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.md` | UPDATE | frontmatter |
| `.agents/PRDs/PRD-010-multi-turn-pipeline/index.md` | UPDATE | STORY-015 row |

No file under `app/`, `chat_ui/` or `tests/` was touched — AC 4.

## Deviations from Plan

1. **Cleanup uses `chat_sessions.delete`, and leaves `audit_logs` alone.** The plan hedged that `app/db/database.py` might expose no delete path. It does — `delete_chat_session` at `:1594` — and the service layer wraps it as `chat_sessions.delete`, so the script uses the service and never reaches past it. But the plan also asked to delete the bench user's `audit_logs` rows, and that is not merely unavailable: it is **deliberately** unavailable. `database.delete_chat_session` states that `audit_logs` is untouched by any statement, ever, because "deleting a conversation deletes a conversation; it does not edit the record of what was asked" (PRD Section 9). Writing a delete path for audit rows to tidy a benchmark would have inverted a documented invariant. The rows are left, and the plan's Risk 7 is handled instead by giving each run a fresh nonce, so no run's dedup keys can collide with an earlier run's.

2. **Seeding goes through `chat_sessions`, not `database`.** The plan's Task 3 named `database.insert_user` / `create_chat_session` / `append_chat_message` directly. `insert_user` has no service wrapper and is used directly, as `scripts/manage_users.py` does; but sessions and messages do, so the script calls `chat_sessions.create` and `chat_sessions.append_message`. `tests/test_chat_sessions.py` forbids store-level session calls from outside that service, and although its AST scan covers only `app/` and `chat_ui/`, a script that quietly violates the rule it cannot be caught by is worse than one that follows it.

3. **The statement comparison shows 3 statements against 2, not 4 against 3.** The plan predicted `SELECT users → SELECT audit_logs → INSERT audit_logs` plus the history read, citing `test_two_instance_smoke.py:1194-1201`. That test measures an HTTP *request*, which first resolves a bearer token through `find_user_by_token_hash`. This script calls `run_conversation` directly with an already-constructed `Identity`, so there is no identity read. The difference the comparison exists to show — exactly one extra `SELECT chat_messages` on the history path — is unaffected.

4. **`_first_words` names the table, not just the verb.** The borrowed helper reported `SELECT, SELECT, INSERT`, which cannot distinguish `assemble`'s read from the duplicate check's — the one distinction the comparison exists to make. It now prints `SELECT chat_messages, SELECT audit_logs, INSERT audit_logs`.

5. **`fit` is timed inside arm (a) and labelled as such.** As planned, but worth stating in the report: arm (a)'s 5.17 ms is `assemble` + `fit` together. `fit` is pure and does no I/O (`chat_history.py:178-196`), so essentially all of that figure is the read.

6. **Task 9 was not executed.** Its condition did not fire. This is the planned behaviour for a passing indicator, not an omission — see Verdict and Recommendation.

## Tests Written

None, and that is the story's shape rather than a gap. STORY-015 is a spike whose deliverable is "the numbers in the report, plus the script" (Technical Notes), and AC 3 requires the script to be **excluded** from the default pytest run. A test asserting any of these latencies would be precisely the flaky wall-clock assertion `tests/test_two_instance_smoke.py:1225-1246` rules out. The script's own correctness is guarded at runtime instead: every send is checked to be a `QuerySuccessResponse` and the run aborts loudly otherwise, which is what stops a silently-blocked arm reporting a fast, meaningless number.

## Acceptance Criteria

- [x] **20 answered exchanges, 300–800 char prompts with PII, 30 timed sends, real `redact()`, stub upstream, p50/p95 for (a) `assemble`, (b) redaction of all messages, (c) whole `run_conversation` excluding upstream, against a single-turn baseline** — the table under [Measured latency](#measured-latency). 41 messages, 19,193 characters; corpus 466–525 chars per question, PII in one question in three.
- [x] **Verdict against the Section 11 indicator, with numbers; otherwise state the gap and open the Section 13 follow-up** — the indicator holds: 926.05 ms added against 932.38 ms accounted for by one `messages_for` read plus per-turn redaction. No PRD edit made, as AC 2 specifies for the passing case. The separate judgement call Risk 3 leaves open is recorded under [Recommendation](#recommendation) rather than actioned unilaterally.
- [x] **Script lives under `scripts/`, excluded from the default pytest run, runnable with one documented command** — `scripts/measure_history_latency.py`; `pytest --collect-only -q scripts/` collects nothing; `python scripts/measure_history_latency.py` runs the 20×30 measurement on its defaults, documented in the module's `Usage:` block. (README documentation of the multi-turn work is STORY-018's scope.)
- [x] **Full suite green and no production file modified** — see Validation Results.
