---
story: STORY-011
prd: PRD-003
slug: docker-image-spacy-model
title: "Docker image: install spaCy PII model"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-08-02
---

# Plan: Docker image — install spaCy PII model

## Summary

`requirements.txt` installs `spacy`, `presidio-analyzer` and `presidio-anonymizer`, but **not** the `en_core_web_lg` NLP model those packages need — that model is distributed separately and must be fetched with `python -m spacy download`. Locally it happens to be present in `.venv/` (verified: `en_core_web_lg 3.8.0`, 424.5 MB on disk), so every PRD-003 story so far has passed; in a freshly built container it is absent, and the first call into `pii_redactor._build_analyzer()` would raise `PiiRedactorError: Failed to load Presidio NLP model 'en_core_web_lg'`. This story adds one `RUN python -m spacy download en_core_web_lg` line to the **final** Dockerfile stage (right after `pip install`, before `COPY . .`, so the ~425 MB layer stays cached across app-code changes) and leaves the discarded builder stage alone — verified below to never construct the analyzer at import time. It also closes a second, related container-only gap surfaced during exploration: because Reflex's `api_transformer` mount bypasses `app.main`'s `lifespan` (documented finding from PRD-002 STORY-003), [[STORY-002]]'s `pii_redactor.load()` **never runs in the container at all**, so the model would load lazily on the first `/query` — exactly the cold-start the PRD rules out (RF-4, Risk 2). One line in `chat_ui/chat_ui/chat_ui.py` registers `pii_redactor.load` as a Reflex lifespan task, restoring `python app.py` ↔ Docker parity without dragging the model into the builder stage.

## User Story

As a devops engineer
I want the `en_core_web_lg` spaCy model downloaded during the Docker build
So that the containerized app boots successfully with the same PII redaction behavior as `python app.py`, consistent with PRD-001's Docker/local parity principle

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-011-docker-image-spacy-model.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `Dockerfile`, `chat_ui/chat_ui/chat_ui.py` (1 line + import), `docker-compose.yml` (verified: no change) |
| Story | STORY-011 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None — `.agents/skills/` does not exist in this repository (confirmed via `ls`; story frontmatter `skills: []`; the same finding is recorded in [[STORY-001]]'s and [[STORY-002]]'s plans).

---

## Patterns to Follow

### Dockerfile final stage — dependency install sits before `COPY . .` (layer-cache ordering)
```dockerfile
// SOURCE: Dockerfile:41-47
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=builder /srv /srv
```
Dependencies are installed from `requirements.txt` alone, *before* the source tree is copied, so editing app code never re-runs `pip install`. The new spaCy model download must land in this same window — after `RUN pip install`, before `COPY . .` — or a one-character source edit would re-download 425 MB.

### Dockerfile — `--no-cache-dir` everywhere, explicit cleanup of package-manager caches
```dockerfile
// SOURCE: Dockerfile:31-38
RUN apt-get update && apt-get install -y --no-install-recommends \
        debian-keyring debian-archive-keyring apt-transport-https curl gnupg \
    && ...
    && apt-get purge -y curl gnupg apt-transport-https && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
```
Every install step in this file deliberately avoids leaving a cache behind (`--no-cache-dir` on pip, `rm -rf /var/lib/apt/lists/*` on apt). The spaCy download shells out to pip internally, so it gets the same treatment via an explicit `rm -rf /root/.cache/pip` in the same `RUN`.

### Eager startup work in `chat_ui.py`, because the mounted app's `lifespan` never fires
```python
// SOURCE: chat_ui/chat_ui/chat_ui.py:16-21
# Reflex's api_transformer mounts fastapi_app as a Starlette sub-app under a
# new outer Starlette app whose own lifespan runs instead of fastapi_app's —
# app.main's `lifespan` (and its init_db() call) never fires when mounted this
# way, so we call it eagerly here. CREATE TABLE IF NOT EXISTS makes this safe
# to call on every reload.
init_db()
```
This is the exact precedent for the `chat_ui.py` change below, and the reason it is needed: the same bypass that swallowed `init_db()` also swallows `pii_redactor.load()` (added to `app/main.py:14` by [[STORY-002]]). The difference in treatment — `init_db()` is called at *import* time, `pii_redactor.load` is *registered* as a lifespan task — is deliberate and explained in Design Note 2.

### Startup load entry point (from [[STORY-002]], reused unchanged)
```python
// SOURCE: app/services/pii_redactor.py:43-46
def load() -> None:
    if not settings.PII_REDACTION_ENABLED:
        return
    _get_analyzer()
```
Already flag-aware, idempotent, zero-arg, and returns `None` — directly registrable as a Reflex lifespan task with no wrapper (see Design Note 3 for the mechanics). No change to this file.

### Tests — the suite never imports the Reflex app module
```python
// SOURCE: tests/test_chat_state.py:24-25
import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.state import ChatState
```
The only chat-UI imports in `tests/` reach `chat_ui.chat_ui.state`, never `chat_ui.chat_ui` itself — constructing `rx.App(...)` requires Reflex's `rxconfig.py` CWD context (`chat_ui/`), which the pytest suite deliberately avoids. This story therefore adds **no pytest test**; its two verifications are shell smoke-checks (Tasks 1 and 5) run from the correct CWD, matching how PRD-002's Docker story (STORY-008) was validated.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `Dockerfile` | UPDATE | Final stage: download `en_core_web_lg` after `pip install`, before `COPY . .` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Register `pii_redactor.load` as a Reflex lifespan task so the container warm-loads the model at startup instead of on the first `/query` |
| `docker-compose.yml` | NO CHANGE (verify only) | Uses `env_file: .env` with no env allowlist, so the four `PII_*` vars pass through automatically and all have defaults in `app/config.py:16-19` |
| `requirements.txt` | NO CHANGE | Model is intentionally *not* pinned here — see Design Note 4 |
| Builder stage of `Dockerfile` | NO CHANGE (verify only) | AC3 — proven below that `reflex export --frontend-only` never builds the analyzer |

---

## Design Notes (decisions worth stating up front)

1. **The builder stage does not need the model — this is provable, not assumed (AC3).** The import chain `chat_ui.chat_ui` → `app.main` → `app.services.pii_redactor` executes only module-level statements: `from presidio_analyzer import AnalyzerEngine` etc. (pip packages, present in the builder from `requirements.txt`) plus `_analyzer = None` / `_anonymizer = None`. `_build_analyzer()` — the only code that touches the spaCy model — is reachable exclusively through `_get_analyzer()`, called from `load()` and `redact()` (`app/services/pii_redactor.py:29-33, 43-46, 50`). `load()` is invoked from `app/main.py:14` (`lifespan`, never runs during `reflex export --frontend-only`) and, after Task 3, from a registered Reflex lifespan task (registration is a dict insert; `App._run_lifespan_tasks` only executes when the ASGI app actually starts). The one eager import-time call in `chat_ui.py` is `init_db()`, which is unrelated. Task 1 turns this argument into an executable assertion, and it must keep passing *after* Task 3 — that is precisely the regression AC3 is guarding against.

2. **Why `register_lifespan_task(pii_redactor.load)` and not a bare `pii_redactor.load()` call next to `init_db()`.** Calling it eagerly at import time would be the closer match to the existing `init_db()` line, but it would build the analyzer during `reflex export --frontend-only` in the **builder** stage — forcing a second 425 MB model download into a stage that is thrown away, for zero runtime benefit, and directly violating AC3's "leave the builder stage alone unless the import chain actually triggers Presidio initialization". Registering a lifespan task keeps import-time work at zero while still running the load before the backend serves traffic. `init_db()` stays exactly as it is — it is cheap, idempotent, and moving it is out of scope.

3. **A plain sync zero-arg callable is a valid Reflex lifespan task (verified against the installed `reflex==0.9.6.post1`).** `App._run_lifespan_tasks` inspects each registered task's signature, injects `app`/`starlette_app` only if those parameter names exist, calls it, and branches on the return value: `_AsyncGeneratorContextManager` → entered on the exit stack, `Coroutine` → scheduled as a task, **anything else → already executed, logged as `type=function`**. `load()` takes no parameters and returns `None`, so `app.register_lifespan_task(pii_redactor.load)` runs it synchronously during startup — blocking startup until the model is in memory, which is the desired warm-load semantics. No `async def` wrapper needed.

4. **Model install goes in the Dockerfile, not `requirements.txt`.** Pinning `en_core_web_lg @ https://github.com/explosion/spacy-models/releases/download/...` in `requirements.txt` would also work and would give a reproducible pin, but it couples the model version to a hand-maintained URL that must be bumped in lockstep with `spacy`, and it would additionally force the 425 MB download into the **builder** stage (which installs the same `requirements.txt`) — the exact outcome Design Note 1 avoids. The story's Technical Notes specify `RUN python -m spacy download en_core_web_lg`; that is what this plan implements.

5. **The Dockerfile hardcodes `en_core_web_lg` while `PII_NLP_MODEL` is configurable (`app/config.py:19`).** Only the default is baked into the image. Overriding `PII_NLP_MODEL` to e.g. `en_core_web_trf` at runtime will fail startup with `PiiRedactorError` unless that model is installed too. This is an accepted, documented limitation, not a bug — it is handed to [[STORY-012]] as a README note alongside the image-size figure.

6. **Failure mode shifts from "first `/query` 500s" to "container fails to start".** After Task 3, a missing/misnamed model crashes backend startup rather than surfacing on the first request. That is the intended direction (it matches [[STORY-002]] Design Note 3 — a broken redaction state should fail loud) and is why Task 5's smoke check is a *startup* check, not a request check. Note it also applies to a developer running `cd chat_ui && reflex run` locally without the model installed.

7. **`PII_REDACTION_ENABLED=false` remains a clean escape hatch.** `load()` short-circuits on the flag, so a deployment that disables redaction never touches the model — the image still carries it, but startup does no NLP work. No new conditional logic is needed anywhere.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Prove the builder stage does not need the model (AC3 evidence, pre-change baseline)

- **File**: none — verification only
- **Action**: VERIFY
- **Implement**: Confirm that importing the Reflex app module (what `reflex export --frontend-only` does in the builder stage) never constructs the Presidio analyzer, by sabotaging `_build_analyzer` before the import and asserting it is never called. Run from the `chat_ui/` directory, which is the CWD Reflex itself uses:
  ```bash
  cd f:\AI\harness-ai\chat_ui
  python -c "import sys; sys.path.insert(0, '..'); import app.services.pii_redactor as p; p._build_analyzer = lambda: (_ for _ in ()).throw(AssertionError('analyzer built at import time')); import chat_ui.chat_ui; print('OK - no analyzer built at import; _analyzer =', p._analyzer)"
  ```
  Expected output: `OK - no analyzer built at import; _analyzer = None`. Record this result — it is the AC3 answer, and Task 5 re-runs it after Task 3 to prove the lifespan registration did not change it.
- **Mirror**: Design Note 1 — this is the executable form of that static analysis.
- **Validate**: Command exits 0 and prints `_analyzer = None`. If it raises `AssertionError`, **stop**: the builder stage genuinely needs the model and Task 2 must also add the download to the builder stage (per AC3's conditional). Given the code as it stands today this is not expected.

### Task 2: Download `en_core_web_lg` in the Dockerfile's final stage

- **File**: `Dockerfile`
- **Action**: UPDATE
- **Implement**: In the final stage only (`FROM python:3.11-slim`, `Dockerfile:29`), insert a new `RUN` immediately after the existing `RUN pip install --no-cache-dir -r requirements.txt` (`Dockerfile:44`) and before `COPY . .` (`Dockerfile:46`):
  ```dockerfile
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  # Presidio's analyzer needs an English spaCy model (PRD-003); it ships separately
  # from the `spacy` package in requirements.txt. Baked into the image at build time
  # so the container never downloads it at startup. ~425 MB — accepted tradeoff,
  # PRD-003 Risk 5. Kept before `COPY . .` so app-code edits don't re-download it.
  RUN python -m spacy download en_core_web_lg \
      && rm -rf /root/.cache/pip

  COPY . .
  ```
  The builder stage (`Dockerfile:1-27`) is **not** touched — justified by Task 1's result. `--no-cache-dir` is not passed to `spacy download` (its pip pass-through varies by spaCy version); the explicit `rm -rf /root/.cache/pip` achieves the same size saving unambiguously.
- **Mirror**: `Dockerfile:41-47` (install-before-`COPY . .` cache ordering) and `Dockerfile:31-38` (clean up the package cache in the same `RUN`).
- **Validate**: `docker build -t harness-ai:story-011 .` completes; then `docker run --rm harness-ai:story-011 python -c "import spacy; spacy.load('en_core_web_lg'); print('model present')"` prints `model present`. **Docker Desktop must be running** — `docker images` currently fails with `open //./pipe/dockerDesktopLinuxEngine: file not found`, i.e. the CLI is installed (v28.4.0) but the daemon is down. Start it before this task.

### Task 3: Warm-load the model at container startup (Reflex lifespan task)

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Add the `pii_redactor` import alongside the existing `app.*` imports, and register `load` as a lifespan task immediately after the `app = rx.App(...)` line at the bottom of the file:
  ```python
  from app.db.database import init_db
  from app.main import app as fastapi_app
  from app.services import pii_redactor
  ```
  ```python
  app = rx.App(api_transformer=fastapi_app)
  app.add_page(index)

  # Same api_transformer lifespan bypass as init_db() above: app.main's lifespan —
  # and so STORY-002's pii_redactor.load() — never fires under Reflex. Registered as
  # a lifespan task (not called at import) so `reflex export --frontend-only` in the
  # Dockerfile's builder stage still never touches the spaCy model. load() is
  # zero-arg, sync and PII_REDACTION_ENABLED-aware, so Reflex runs it as-is.
  app.register_lifespan_task(pii_redactor.load)
  ```
  Do not convert the existing eager `init_db()` call to a lifespan task — out of scope.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:16-21` — the existing "lifespan is bypassed, compensate here" precedent and its comment style; `app/main.py:12-15` — the `init_db()` + `pii_redactor.load()` startup pairing this restores.
- **Validate**: Re-run Task 1's command verbatim — it must **still** print `_analyzer = None` (registration must not trigger a build). Then `python -m pytest` from the repo root: the full suite must still pass, unchanged (no test imports `chat_ui.chat_ui`, so this is a no-regression check).

### Task 4: Confirm `docker-compose.yml` needs no changes (AC: env passthrough)

- **File**: `docker-compose.yml`
- **Action**: VERIFY (expected: no edit)
- **Implement**: Confirm the service has no `environment:` allowlist that would drop the new `PII_*` vars. Current content passes the whole `.env` through `env_file: .env` and only overrides `DATABASE_URL`, so any `PII_*` var set in `.env` reaches the container automatically; all four also have defaults in `app/config.py:16-19`, so an `.env` without them is equally fine. Record "no change required" for the report.
- **Mirror**: `docker-compose.yml:8-12`.
- **Validate**: `docker-compose config` renders without error and shows no `PII_*` omission (run after Docker Desktop is up).

### Task 5: End-to-end container verification + image-size measurement (AC2, AC4)

- **File**: none — verification only
- **Action**: VERIFY
- **Implement**:
  1. Build the pre-change baseline for comparison (from a clean checkout of the previous commit, or reuse an existing pre-PRD-003 image if one is still present locally):
     ```bash
     git stash && docker build -t harness-ai:pre-story-011 . && git stash pop
     ```
  2. Build the post-change image and compare:
     ```bash
     docker build -t harness-ai:story-011 .
     docker images harness-ai --format "{{.Tag}}\t{{.Size}}"
     ```
  3. Boot the stack and confirm startup completes with the analyzer loaded — no missing-model error:
     ```bash
     docker-compose up -d --build
     docker-compose logs harness-ai        # must NOT contain PiiRedactorError / "Can't find model"
     curl http://localhost:8000/health     # {"status":"ok"}
     ```
  4. Confirm redaction actually works inside the image, without spending an OpenRouter call:
     ```bash
     docker-compose run --rm harness-ai python -c "from app.services import pii_redactor; print(pii_redactor.redact('my email is juan@empresa.com and my name is Maria Lopez'))"
     ```
     Expected: masked text plus `['EMAIL_ADDRESS', 'PERSON']`.
  5. Run the suite in-container, as README documents:
     ```bash
     docker-compose run --rm harness-ai pytest tests/ -v
     ```
  6. Write the measured size delta into the story's report for [[STORY-012]] to document. Reference figure for sanity-checking the result: `en_core_web_lg 3.8.0` is **424.5 MB** on disk in `.venv/` (measured), so expect roughly +0.4–0.5 GB on the final image.
- **Mirror**: `README.md:139-144` (Quickstart — Docker) and `README.md:295-298` (in-container pytest invocation) — use the documented commands rather than inventing new ones.
- **Validate**: All five steps succeed; the recorded size delta is captured for [[STORY-012]]. Finish with `docker-compose down`.

---

## End-to-End Tests

Checks for `/implement` to execute (Docker Desktop must be running for all but the first two):

- [ ] `cd chat_ui && python -c "...sabotage _build_analyzer... import chat_ui.chat_ui..."` (Task 1) → prints `_analyzer = None`, **both before and after** Task 3 — proves the builder stage still needs no model (AC3)
- [ ] `python -m pytest` from repo root → full suite passes unchanged (no regression from the `chat_ui.py` edit)
- [ ] `docker build -t harness-ai:story-011 .` → succeeds; builder stage build time is not materially longer than before (no model download there)
- [ ] `docker run --rm harness-ai:story-011 python -c "import spacy; spacy.load('en_core_web_lg')"` → model is present *in the image*, not downloaded at container start (AC1)
- [ ] `docker-compose up -d --build` then `docker-compose logs harness-ai` → startup completes, no `PiiRedactorError` / "Can't find model 'en_core_web_lg'" (AC2)
- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `docker-compose run --rm harness-ai python -c "from app.services import pii_redactor; print(pii_redactor.redact('my email is juan@empresa.com and my name is Maria Lopez'))"` → returns masked text + `['EMAIL_ADDRESS', 'PERSON']`
- [ ] `docker-compose run --rm harness-ai pytest tests/ -v` → suite passes inside the container
- [ ] `docker images harness-ai --format "{{.Tag}}\t{{.Size}}"` → size delta vs. the pre-change image recorded for [[STORY-012]] (AC4)
- [ ] Browse `http://localhost:8000` → chat UI loads (confirms the builder stage's frontend export was unaffected)

---

## Validation

```bash
cd f:\AI\harness-ai\chat_ui
python -c "import sys; sys.path.insert(0, '..'); import app.services.pii_redactor as p; p._build_analyzer = lambda: (_ for _ in ()).throw(AssertionError('analyzer built at import time')); import chat_ui.chat_ui; print('OK - _analyzer =', p._analyzer)"

cd f:\AI\harness-ai
python -m pytest

docker build -t harness-ai:story-011 .
docker run --rm harness-ai:story-011 python -c "import spacy; spacy.load('en_core_web_lg'); print('model present')"
docker images harness-ai --format "{{.Tag}}\t{{.Size}}"

docker-compose up -d --build
docker-compose logs harness-ai
curl http://localhost:8000/health
docker-compose run --rm harness-ai python -c "from app.services import pii_redactor; print(pii_redactor.redact('my email is juan@empresa.com and my name is Maria Lopez'))"
docker-compose run --rm harness-ai pytest tests/ -v
docker-compose down
```

---

## Risks

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Docker daemon is not running in this environment (`docker images` fails; CLI v28.4.0 present, Desktop engine pipe missing) — every build/run validation is blocked | Start Docker Desktop before Task 2. If it cannot be started, Tasks 1, 3 and the pytest run still complete; Tasks 2/4/5 must be marked *not verified* in the report rather than assumed passing |
| 2 | `python -m spacy download` needs network access at build time; a firewalled build host fails the image build | Documented as a build-time requirement for [[STORY-012]]'s README. Fallback if it becomes a real constraint: pin the model wheel URL in `requirements.txt` (Design Note 4) — deliberately not chosen now |
| 3 | Image grows ~0.4–0.5 GB, slowing pulls/deploys | Accepted tradeoff, explicitly PRD-003 Risk 5. Mitigated only insofar as the layer sits before `COPY . .` (rebuilds don't re-download) and the pip cache is removed in the same `RUN` |
| 4 | Task 3 changes the failure mode: a missing model now crashes backend startup instead of failing the first request | Intended (Design Note 6); consistent with [[STORY-002]]'s fail-loud design. Local `reflex run` without the model will now fail fast with a clear `PiiRedactorError` — noted for [[STORY-012]]'s docs |
| 5 | Task 3 is one line beyond a strict "Dockerfile-only" reading of this story | Justified by AC2, which asserts the container's startup load succeeds — unreachable in the Reflex-mounted container without it. Scope is 1 import + 1 call + comment, no behavior change to any request path, no test churn. If rejected during review, drop Task 3 and file the warm-load gap as a follow-up story; the rest of the plan stands on its own |

---

## Acceptance Criteria

(Copied from story STORY-011)

- [ ] Given `docker build` runs, when the final image stage installs `requirements.txt`, then it also runs `python -m spacy download en_core_web_lg` so the model is present in the image (not downloaded at container startup).
- [ ] Given the container starts via `docker-compose up`, when `lifespan` triggers [[STORY-002]]'s startup load, then the Presidio analyzer initializes successfully — no missing-model error.
- [ ] Given the builder stage (used only for the Reflex frontend export, per the existing `Dockerfile` comments), when it builds, then it is **not** required to download the spaCy model unless `chat_ui.chat_ui`'s import chain actually triggers Presidio initialization at import time — verify this and only add the download step to the builder stage if needed.
- [ ] Given the resulting image, when its size is compared to the pre-PRD-003 image, then the increase is noted for [[STORY-012]]'s README documentation (PRD Risk 5 — accepted tradeoff, not a blocker).
- [ ] All tasks completed
- [ ] `docker-compose.yml` confirmed to need no changes (no env allowlist blocking `PII_*`)
- [ ] Full existing test suite (`python -m pytest`) still passes, unmodified
- [ ] Follows existing patterns (dependency install before `COPY . .`, package caches cleaned in the same `RUN`, lifespan-bypass compensation in `chat_ui.py`)
