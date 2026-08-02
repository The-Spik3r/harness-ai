---
story: STORY-011
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-011-docker-image-spacy-model.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 2457952
status: COMPLETE
completed: 2026-08-02
---

# Implementation Report — STORY-011: Docker image — install spaCy PII model

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-011-docker-image-spacy-model.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `2457952`

## Summary

Added `RUN python -m spacy download en_core_web_lg` to the Dockerfile's final stage, so the `en_core_web_lg` model Presidio depends on is baked into the image instead of being absent (it ships separately from the `spacy` package in `requirements.txt`, and only happened to be present locally in `.venv/`). Placed after `pip install` and before `COPY . .` so app-code edits never re-download the 446 MB layer, with the pip cache removed in the same `RUN` to match the file's existing cleanup style.

The builder stage was left untouched, and that decision was verified rather than assumed (AC3): sabotaging `_build_analyzer` before importing `chat_ui.chat_ui` proves the analyzer is never constructed at import time, so `reflex export --frontend-only` has no use for the model.

One additional line closed a container-only gap the plan surfaced during exploration: Reflex's `api_transformer` bypasses `app.main`'s `lifespan` (the documented PRD-002 STORY-003 finding that already forced the eager `init_db()` call), which meant STORY-002's `pii_redactor.load()` **never ran in the container** — the model would have loaded lazily on the first `/query`, exactly the cold start PRD-003 RF-4 / Risk 2 rules out. Registering `pii_redactor.load` as a Reflex lifespan task (rather than calling it at import) restores `python app.py` ↔ Docker parity while keeping the builder stage model-free.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Prove the builder stage does not need the model (AC3 evidence) | — (verification) | ✅ |
| 2 | Download `en_core_web_lg` in the Dockerfile's final stage | `Dockerfile` | ✅ |
| 3 | Warm-load the model at container startup (Reflex lifespan task) | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 4 | Confirm `docker-compose.yml` needs no changes | `docker-compose.yml` | ✅ (no edit) |
| 5 | E2E container verification + image-size measurement | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Builder-stage import safety, before Task 3 | ✅ `_analyzer = None` |
| Builder-stage import safety, after Task 3 (regression guard) | ✅ `_analyzer = None` |
| Lifespan task registered | ✅ `lifespan tasks: ['_setup_event_processor', 'windows_hot_reload_lifespan_hack', 'load']` |
| Tests — host | ✅ 202 passed |
| Tests — in container | ✅ 192 passed, 10 skipped |
| Baseline image build (pre-change Dockerfile) | ✅ exit 0 |
| Post-change image build | ✅ exit 0, `Successfully installed en-core-web-lg-3.8.0` |
| E2E | ✅ 10/10 |

The 10 in-container skips are all `git history unavailable` — `.git/` is excluded by `.dockerignore`, so the merge-base assertions in `tests/test_pii_dedup_isolation.py` and `tests/test_pii_redaction_integration.py` self-skip. Pre-existing behavior, unrelated to this story; the behavioral pins those tests document still run.

## E2E Checklist

| # | Check | Result |
|---|-------|--------|
| 1 | Import-sabotage check → `_analyzer = None`, before **and** after Task 3 | ✅ |
| 2 | `python -m pytest` (host) | ✅ 202 passed |
| 3 | `docker build` succeeds; builder stage not slowed by a model download | ✅ spaCy layer only in stage-1, 39.1s |
| 4 | `docker run ... python -c "import spacy; spacy.load('en_core_web_lg')"` | ✅ `model present` |
| 5 | `docker compose up -d --build`; logs free of `PiiRedactorError` / "Can't find model" | ✅ clean startup |
| 6 | `curl http://localhost:8000/health` | ✅ `{"status":"ok"}` |
| 7 | In-image redaction smoke test | ✅ `('my email is <EMAIL_ADDRESS> and my name is <PERSON>', ['EMAIL_ADDRESS', 'PERSON'])` |
| 8 | `docker compose run --rm harness-ai pytest tests/ -v` | ✅ 192 passed, 10 skipped |
| 9 | Image size delta recorded for STORY-012 | ✅ see below |
| 10 | `http://localhost:8000` serves the chat UI (builder stage unaffected) | ✅ 200, `<title>ChatUi \| Index</title>`, 6444 B |

Additional check beyond the plan: `GET /stats` without a token still returns `401`, confirming the admin middleware is intact in the containerized build.

**AC2 proof.** A clean `/health` is necessary but not sufficient — it does not distinguish a warm-loaded model from a lazy one. Ran the backend in-container with `--loglevel debug`, which printed:

```
Debug: Registered lifespan task: load
Debug: Started lifespan task: load as function
```

confirming `pii_redactor.load` executes during startup, before traffic is served, exactly as plan Design Note 3 predicted for a sync zero-arg callable.

## Image Size (AC4 — for STORY-012's README)

Measured with `docker image inspect --format "{{.Size}}"`:

| Image | Contents | Size |
|-------|----------|------|
| `harness-ai:test` (built 2026-07-05, pre-PRD-003) | no Presidio, no spaCy | 131 MB |
| `harness-ai:pre-story-011` (HEAD before this story) | + presidio/spacy pip deps, **no model** | 223 MB |
| `harness-ai:story-011` (this story) | + `en_core_web_lg` | 628 MB |

- PRD-003 total impact vs. pre-PRD-003: **131 MB → 628 MB (≈ 4.8×, +497 MB)**
- This story's share: **+405 MB**; `docker history` reports the single model layer at **446 MB**
- Build-time cost of the new layer: **39.1 s** (network download), incurred only when `requirements.txt` changes

Caveat worth carrying into the README: the `SIZE` column of `docker images` reports considerably larger figures for the same images on this containerd-backed Docker Desktop (484 MB / 927 MB / 1.78 GB). The `docker image inspect` figures above are the internally consistent ones and agree with the `docker history` layer size; the README should quote a single measurement method.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `Dockerfile` | UPDATE | +9 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +8 |
| `docker-compose.yml` | VERIFIED, no change | — |

## Deviations from Plan

1. **Baseline image built from a copy of the pre-change Dockerfile instead of `git stash`.** Plan Task 5 step 1 specified `git stash && docker build && git stash pop`. Used `git show HEAD:Dockerfile > scratchpad/Dockerfile.pre` + `docker build -f` instead — identical result (only the Dockerfile differs between the two builds), with no mutation of a working tree that also held an unrelated modification to `.agents/commands/prime.md`.
2. **A genuine pre-PRD-003 image was already present locally**, so the AC4 comparison uses `harness-ai:test` (built 2026-07-05, before PRD-003's first commit `0495068` on 2026-07-25) rather than requiring a third build. This is a closer match to AC4's wording ("compared to the pre-PRD-003 image") than the plan's pre-STORY-011 baseline; both are reported above.
3. **Added an explicit `--loglevel debug` lifespan check** not listed in the plan's E2E section, because a passing `/health` cannot by itself distinguish warm-loading from lazy loading, and AC2 is specifically about the startup load.
4. **No pytest test was added**, as anticipated by the plan's "Tests" pattern section: no test in the suite imports `chat_ui.chat_ui` (constructing `rx.App(...)` needs Reflex's `rxconfig.py` CWD context), so the two verifications are shell smoke-checks run from `chat_ui/`. Both are recorded above and in the commit message so they can be re-run.

## Tests Written

None — this is a packaging/deployment story with no new application function. Verification is the E2E checklist above plus the unchanged 202-test suite (host) / 192-test suite (container). See Deviation 4 for why a pytest test was not viable here.

## Follow-ups for STORY-012

- Document the four `PII_*` env vars and the image-size figures above.
- Note that the Dockerfile bakes in **`en_core_web_lg` only**: overriding `PII_NLP_MODEL` (e.g. to `en_core_web_trf`) at runtime requires installing that model separately, or startup fails with `PiiRedactorError`.
- Note the changed failure mode: with the warm load in place, a missing/misnamed model now fails **container startup** rather than the first `/query`. This also applies to a developer running `cd chat_ui && reflex run` locally without the model installed.
- Note that `python -m spacy download` requires network access at build time.

## Acceptance Criteria

- [x] Given `docker build` runs, when the final image stage installs `requirements.txt`, then it also runs `python -m spacy download en_core_web_lg` so the model is present in the image (not downloaded at container startup). — `Dockerfile` stage-1; verified by `spacy.load('en_core_web_lg')` succeeding in a container with no network dependency at start.
- [x] Given the container starts via `docker-compose up`, when `lifespan` triggers STORY-002's startup load, then the Presidio analyzer initializes successfully — no missing-model error. — Required the `chat_ui.py` lifespan-task registration to be true at all; proven by `Started lifespan task: load as function` and clean startup logs.
- [x] Given the builder stage, when it builds, then it is **not** required to download the spaCy model unless `chat_ui.chat_ui`'s import chain actually triggers Presidio initialization at import time — verified, and only add the download to the builder stage if needed. — Verified twice (before and after the `chat_ui.py` change); the import chain never builds the analyzer, so the builder stage was left unmodified.
- [x] Given the resulting image, when its size is compared to the pre-PRD-003 image, then the increase is noted for STORY-012's README documentation. — 131 MB → 628 MB; full table above.
- [x] All tasks completed
- [x] `docker-compose.yml` confirmed to need no changes (no env allowlist blocking `PII_*`)
- [x] Full existing test suite (`python -m pytest`) still passes, unmodified — 202 passed
- [x] Follows existing patterns (dependency install before `COPY . .`, package caches cleaned in the same `RUN`, lifespan-bypass compensation in `chat_ui.py`)
