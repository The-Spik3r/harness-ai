---
story: STORY-012
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-012-readme-env-docs-rollout.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 2f9a9e3
status: COMPLETE
completed: 2026-08-02
---

# Implementation Report — STORY-012: README, `.env.example`, and roadmap updates for PII redaction

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-012-readme-env-docs-rollout.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `2f9a9e3`

## Summary

`README.md` and `.env.example` now document PII redaction as shipped. Ten edits across both files: the Features table, the Solution pipeline line, the ASCII architecture diagram, Requirements, both Quickstarts, the Chat UI limitations list, the Environment Variables table, three API Reference examples, the Running Tests prerequisite, two Troubleshooting entries, and the roadmap checkbox — plus the four `PII_*` vars in `.env.example`. No source code, tests, Dockerfile, compose file, or CI workflow was touched (`git status` over those paths: clean).

Every documented value was verified against the running application rather than transcribed from the PRD. A purpose-built E2E script parsed the JSON blocks straight out of `README.md`, issued the documented requests against the real app with a stubbed OpenRouter, and compared key sets: all five documented shapes (`POST /query` success, both `BLOCKED` variants, `GET /audit`, `GET /stats`) match exactly.

The single most consequential outcome is a **correction to the plan's own premise**. The plan (Design Note 5), and STORY-011's plan before it, asserted that a missing `en_core_web_lg` makes the service fail at startup with `PiiRedactorError`. Testing that claim in a genuinely clean virtualenv proved it false: Presidio auto-downloads a missing model (400.7 MB) during startup and boots successfully. The README was rewritten to describe what actually happens before the work was committed.

## Correction: the missing-model failure mode (found and fixed mid-implementation)

Task 11's verification pass, plus the clean-venv E2E, established the real behavior:

| Scenario | Documented in the plan | **Actually observed** |
|---|---|---|
| `pip install -r requirements.txt`, model never installed | Startup fails with `PiiRedactorError` | Model absent (`spacy.util.get_installed_models()` → `[]`), Presidio **auto-downloads** `en_core_web_lg` (400.7 MB from the spacy-models GitHub release) during startup, and the service **starts successfully** |
| `PII_NLP_MODEL` names an unresolvable model | Startup fails with `PiiRedactorError` | spaCy's CLI prints `[x] No compatible package found for '<model>'` and calls `sys.exit(1)` — the exception is **`SystemExit`, not `PiiRedactorError`**, so `pii_redactor`'s `except Exception` wrapper never sees it |
| `PII_NLP_MODEL=en_core_web_trf` on a host without a C++ toolchain | "requires installing it yourself, or startup fails" | Auto-download starts (457 MB), then dies building `curated-tokenizers`: `Microsoft Visual C++ 14.0 or greater is required` — again a `SystemExit`, after a large download |

Three README passages written earlier in this story were rewritten accordingly, before the commit:

1. **Quickstart — Local** no longer claims skipping the download breaks startup; it says the model is fetched automatically on first boot (~400 MB) and that this needs network access at runtime.
2. **Troubleshooting** replaces the invented `PiiRedactorError` entry with two observed ones: a first-startup stall while spaCy downloads, and the `No compatible package found` process exit. `PiiRedactorError` is still mentioned, but correctly scoped to load failures that are not download failures.
3. **`PII_NLP_MODEL`** row and the **Requirements** bullet were reworded to match.

This also refines — without invalidating — STORY-011's justification for baking the model into the image. The container was never going to crash without it; it would have stalled on a ~400 MB download before serving its first request, and would have required runtime network access. That is still the cold start PRD-003 RF-4 / Risk 2 rules out, so the Dockerfile change stands. The Docker Quickstart now states this consequence explicitly.

## Scope Decision: PRD §10 vs. the shipped API

Where PRD §10 and the code disagree, the code wins (the story's Technical Notes require documenting "the actual shipped shape of every field"):

- **`GET /audit` does not return `prompt_preview`.** PRD.md:207-217 shows it; `AuditQueryEntry` has never carried it and `tests/test_audit_router.py::test_response_never_includes_ip_or_raw_text` forbids it. The README documents the 11 fields the endpoint actually returns. This continues STORY-009's recorded scope decision.
- **`GET /stats` returns nine fields, not the two in PRD §10.** The README's existing full example was extended with the two new ones rather than replaced.
- **The two `BLOCKED` responses gain no PII fields**, because redaction runs only after both checks pass (`app/services/query_pipeline.py:27-57`). Their examples are byte-identical to before; the E2E asserts this.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Features table row (Presidio-backed, mask-not-block, English-only) | `README.md` | ✅ |
| 2 | Solution pipeline one-liner | `README.md` | ✅ |
| 3 | ASCII architecture diagram — two redaction stages | `README.md` | ✅ |
| 4 | Requirements + both Quickstarts (model step, image size) | `README.md` | ✅ (reworded post-correction) |
| 5 | Chat UI — redaction applies, no UI indicator | `README.md` | ✅ |
| 6 | Environment Variables — four `PII_*` rows | `README.md` | ✅ (reworded post-correction) |
| 7 | API Reference — three response examples | `README.md` | ✅ |
| 8 | Running Tests + Troubleshooting | `README.md` | ✅ (rewritten post-correction) |
| 9 | Roadmap checkbox → `[x]` | `README.md` | ✅ |
| 10 | Four `PII_*` vars | `.env.example` | ✅ |
| 11 | Cross-check every documented value against code | — (verification) | ✅ — surfaced the correction above |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A — no npm frontend in this repo (Reflex/Python project) |
| Tests — baseline before edits | ✅ 202 passed |
| Tests — after edits | ✅ 202 passed (byte-identical; a doc-only change cannot move it) |
| `.env.example` parsed through real `Settings` | ✅ matches `app/config.py` defaults exactly |
| E2E | ✅ 11/11 |

## E2E Checklist

| # | Check | Result |
|---|-------|--------|
| 1 | `git diff --stat` → only `README.md` + `.env.example`; no app/test/docker/CI file | ✅ `clean: no source/CI/docker files modified` |
| 2 | `pytest -q` unchanged from baseline | ✅ 202 passed, both runs |
| 3 | `.env.example` parsed by `Settings(_env_file=...)` vs. code defaults | ✅ `match: True` for all four vars |
| 4 | Quickstart — Local followed verbatim in a **clean venv** → service starts | ✅ `spacy download` succeeded, `python app.py` booted, `/health` → `{"status":"ok"}`, `/audit` → `401`, no download during startup |
| 5 | Skipping the download step in that clean venv | ✅ tested — **contradicted the plan**, see Correction above |
| 6 | Documented `POST /query` success shape vs. live response | ✅ key sets identical; `pii_redacted: true`; `pii_entities_masked: ['EMAIL_ADDRESS', 'PERSON']` sorted; OpenRouter received `my name is <PERSON>, my email is <EMAIL_ADDRESS>`; no raw PII in either direction |
| 7 | Documented `GET /audit` entry shape vs. live | ✅ identical 11-key set; `prompt_preview` absent; payload contains neither raw PII nor masked placeholders |
| 8 | Documented `GET /stats` shape vs. live | ✅ identical 9-key set; `pii_detected_queries: 1`, `top_pii_entities: ['EMAIL_ADDRESS', 'PERSON']` |
| 9 | Both `BLOCKED` examples still exact, no PII fields | ✅ key sets match; `no pii fields on blocked: True` |
| 10 | ASCII diagram alignment | ✅ every box interior is 23 chars — `misaligned: none` |
| 11 | Markdown structure: fences, tables, anchors | ✅ 34 fence markers (balanced), no table with inconsistent column counts, 16/16 TOC entries and 19/19 inline anchors resolve, no heading missing from the TOC |

Beyond the plan: `GET /audit` without a token returned `401` in the clean-venv boot, confirming the docs' auth claim on a fresh install.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +58/−11 |
| `.env.example` | UPDATE | +12 |

## Deviations from Plan

1. **The plan's missing-model failure mode was wrong, and the README was corrected before committing.** Full detail in the Correction section above. The plan file is archived as written; this report is the authority on the behavior. Nothing in the plan's task list changed — only the wording those tasks produced.
2. **Validation commands need `.venv/Scripts/python.exe`, not bare `python`.** The plan's commands say `python -m pytest`. On this machine bare `python` is system Python 3.13 with no Presidio installed, so the first baseline run aborted with `ModuleNotFoundError: No module named 'presidio_analyzer'` and 10 collection errors. Re-running with the repo venv gave the expected 202. The plan's E2E intent was unaffected; only the interpreter path changed. Worth noting for future stories in this repo.
3. **Task 3 (architecture diagram) was kept, not dropped.** The plan flagged it as independently droppable if alignment proved fiddly. It did not — the interiors are all 23 characters and verified programmatically.
4. **The `en_core_web_trf` probe was run against `.venv` before its consequences were understood**, triggering a 457 MB download that then failed to build. `.venv` was verified undamaged afterwards (`['en_core_web_lg', 'en_core_web_sm']` — no `trf` installed, no stray dependency), and the suite still reports 202 passed. Subsequent probes were run in the throwaway scratch venv instead.
5. **No new tests were written** — consistent with the plan and with STORY-011's precedent for a no-new-code story. Verification is the E2E checklist plus the unchanged 202-test suite. The E2E script lives in the scratchpad, not the repo, because it asserts on README prose rather than on application behavior and would become a maintenance burden in `tests/`.

## Tests Written

None — documentation-only story with no new application function. See Deviation 5.

## Follow-ups (not fixed here — this story is doc-only)

1. **CI does not install the spaCy model.** `.github/workflows/ci.yml:21-25` runs `pip install -r requirements.txt` then `pytest -q`, with no `spacy download`. Given the finding above, CI will not *fail* on a clean runner — it will silently download 400 MB on the first test that touches the analyzer, on every run, since `actions/setup-python`'s pip cache does not cover it. Recommend adding `python -m spacy download en_core_web_lg` as an explicit step. This is a workflow change, out of scope for a documentation story.
2. **`pii_redactor` cannot report a model-load failure as `PiiRedactorError`** when spaCy's downloader is the thing that fails, because `spacy.cli.download` raises `SystemExit`, which `except Exception` does not catch (`app/services/pii_redactor.py:25`). If fail-loud-with-our-own-error is the intent, that handler needs `except BaseException` or an explicit pre-check that the model is installed. Behavioral change — needs its own story.
3. **PRD §10's `GET /audit` example still shows `prompt_preview`**, which no endpoint returns. The README is now correct; the PRD is not. Worth a small PRD amendment so the next reader is not misled.

## Acceptance Criteria

- [x] Given `README.md`'s Features table, when read, then it lists PII redaction on input/output, mentioning it's English-only, mask-not-block, and Presidio-backed. — Features row: "Masking never blocks a request… English-only in this release", links Presidio.
- [x] Given `README.md`'s Environment Variables section, when read, then it documents `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES`, `PII_NLP_MODEL` with the same defaults as STORY-001's implementation. — Four rows; defaults verified equal to `app/config.py:15-18` programmatically.
- [x] Given `README.md`'s API Reference section, when read, then the `POST /query` response example includes `pii_redacted`/`pii_entities_masked`, and `GET /audit`/`GET /stats` examples include the new PII telemetry fields from STORY-009. — All three updated; key sets verified against live responses.
- [x] Given `README.md`'s Roadmap section, when read, then `- [ ] PII redaction on input/output` is changed to `- [x] PII redaction on input/output`. — README.md:369.
- [x] Given `.env.example`, when read, then it includes the four new `PII_*` vars with a short comment each, matching the existing file's comment style. — One comment line per var, blank line between, no quotes; parses through `Settings`.
- [x] Given `README.md`'s Requirements/Quickstart sections, when read, then they note the added spaCy model download step and the image-size/build-time impact from STORY-011 (PRD Risk 5). — Requirements (2 bullets), Quickstart — Local (command + consequence of skipping), Quickstart — Docker (131 MB → 628 MB, ~446 MB layer, ~40 s, measurement method named).
- [x] All tasks completed
- [x] No source code changed — `git diff --stat` shows only `README.md` and `.env.example`
- [x] Full test suite still passes unchanged (202 passed)
- [x] Follows existing patterns (`.env.example` comment rhythm, README table/fence/troubleshooting styles)
