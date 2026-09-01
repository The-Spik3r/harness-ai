---
story: STORY-010
prd: PRD-006
slug: admin-route-registration
title: "Register /admin, /admin/audit and /admin/stats without touching a reserved route"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: three routes into `chat_ui.py`, and nothing else moves

## Summary

Add three `app.add_page(...)` calls to `chat_ui/chat_ui/chat_ui.py` so the console STORY-009 built becomes reachable: `/admin/audit` (the register), `/admin/stats` (the summary) and `/admin`, which renders the same shell and redirects to the register on load. The two page functions are three lines each — `admin_page(rx.fragment(), VIEW_REGISTER)` and its summary twin — because `register.py` and `summary.py` do not exist yet (STORY-011, STORY-015); this story registers the routes and hands those two stories a `content` slot to fill, which is exactly the seam `admin_page(content, active)` was given in STORY-009. The route strings are **imported**, never retyped: `ROUTE_REGISTER` / `ROUTE_SUMMARY` are declared once in `admin_shell.py:56-57` and STORY-009 wired the masthead's switch to those same constants, so a moved page cannot leave the switch pointing at a dead path. Nothing under `app/` is touched, no FastAPI route is added, the `Caddyfile` is unchanged, and `tests/test_route_reservations.py` must pass with a zero-line diff. Two edits ride along: each admin page is registered with `context={"sitemap": None}` so the console's routes stay out of the publicly served `sitemap.xml` (`reflex_base/plugins/sitemap.py:154-161`), and `tests/test_admin_shell.py` gains a second probe that imports the real `app` object and asserts the three routes are registered while `app.main`'s route table is identical to what it was before the import.

## User Story

As an integrating developer
I want the console's two pages registered under `/admin` with no new FastAPI route
So that the REST contract and the reserved-route test hold unmodified.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-010-admin-route-registration.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4, Section 5 (story 9), Section 6 (routing constraint, files), Section 9 (reserved routes, deployment), Section 10 (no new or modified endpoints), Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/chat_ui.py` (UPDATE — three `add_page` calls, one import line), `tests/test_admin_shell.py` (UPDATE — a second probe). No `app/` change, no `Caddyfile` change, no new module, no new dependency. |
| Story | STORY-010 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check.** `depends_on: [STORY-009]` — `status: done` at `5a35ce3`. Everything this story consumes therefore exists and was read before planning: `admin_page(content, active)`, `ROUTE_REGISTER` (`"/admin/audit"`), `ROUTE_SUMMARY` (`"/admin/stats"`), `VIEW_REGISTER`, `VIEW_SUMMARY` — all in `chat_ui/chat_ui/components/admin_shell.py:47-70,289`. `blocks: [STORY-011, STORY-015]`, both `todo`, and both consume the `content` slot this story leaves empty. Working tree clean on `epic/PRD-006-admin-console` at `48cf5eb`. Baseline captured before planning: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/ -q` → **418 passed in 7.77s**. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (**NOT INSTALLED** — substituted, see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API, and this story is *only* Reflex API: `app.add_page(route=..., on_load=..., context=...)` and `rx.redirect`. The story's own Technical Notes name it and name the two questions to answer — the `add_page(..., route=...)` signature, and how `/admin` should redirect or alias to the register. | Tasks 1, 2 |
| `reflex-process-management` (**NOT INSTALLED** — substituted, see below) | Mandated for any compile/run/reload cycle. This is **the first story that compiles the admin pages** — STORY-009's own plan says so explicitly — so the dev-server run in Task 4 is the point the skill exists for. | Tasks 4, 5 |
| `.agents/skills/frontend-design` | Not in this story's `skills:` list, and correctly so: nothing here is designed. It is named only to record that the one judgment call with a visual consequence — what `/admin` renders during the redirect — was decided against the skill's *"an empty screen is an invitation to act"* rather than by default. See Design decisions. | Task 1 |

### Skill availability and the substitution

`reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed in this environment (`~/.claude/plugins` is absent; `.agents/skills/` holds only `frontend-design`). This is the same gap STORY-001 … STORY-009 each recorded — a tooling gap, not a decision to work from memory. `chat_ui/AGENTS.md`'s rule is *"rather than relying on memory"*, so every Reflex API below was verified against **both** the pinned package (`reflex==0.9.6.post1`, confirmed via `importlib.metadata`) and current Reflex documentation (context7 `/websites/reflex_dev`) before being written into a task. **`/implement` must install the plugin if it has since become available and re-verify; otherwise repeat this substitution and say so in the report.**

What was verified for **this** story, with sources:

1. **`add_page`'s signature is `(component, route, title, description, image, on_load, meta, context)`** — `reflex/app.py:864-874`. `route` is optional *only* for a callable, where it is derived as `format_route(to_kebab_case(component.__name__))`; passing it explicitly is required here and is what keeps the page path tied to `admin_shell`'s constant rather than to a function name. The docs confirm the same call shape (`reflex.dev/docs/getting-started/dashboard-tutorial`).
2. **An explicit `route` is *not* kebab-cased.** `format_route` (`reflex_base/utils/format.py:315-329`) only strips the surrounding slashes and maps `""` to the index route. Verified empirically against the real app object: after two `add_page` calls the registered keys are `['admin', 'admin/audit', 'index']`. So `/admin/audit` stays `/admin/audit`, and the `href` STORY-009's `_view_link` already emits resolves to the page this story registers.
3. **Nested routes are valid and produce a nested static file.** `verify_route_validity` (`reflex/route.py:12-30`) splits on `/` and accepts each alphanumeric part, so a two-segment route needs nothing special. `_path_to_file_stem` (`reflex/compiler/utils.py:679-684`) turns `admin/audit` into the flat-route file `[admin].[audit]._index.jsx`, and `reflex export` prerenders it to `build/client/admin/audit/index.html`, which `_duplicate_index_html_to_parent_directory` (`reflex/utils/build.py:173-193`) also copies to `admin/audit.html` — its docstring reads *"This makes accessing /route and /route/ work in production."* That is the mechanism behind AC 4: the `Caddyfile`'s `try_files {path} {path}/` finds the directory and `file_server` serves its `index.html`, exactly as it does for `/` today. **No Caddyfile change, and the reason is a copy step in Reflex's build rather than an assumption.**
4. **`on_load` accepts an `EventSpec`, and `rx.redirect` returns one.** `app.py:966-970` normalises `on_load` into `self._load_events[route]`; `redirect(path, *, is_external=False, popup=False, replace=False)` is `reflex_base/event/__init__.py:1313-1338`. `replace=True` is the correct flag for a landing route — without it `/admin` leaves a history entry and the browser Back button bounces the admin straight back into the redirect. The docs confirm `rx.redirect` as an `on_load` value (`reflex.dev/docs/api-reference/special-events`, `.../event-triggers`).
5. **A duplicate route raises rather than silently overwriting** — `app.py:945-961` raises `RouteValueError` when the route already exists with a different component. Nothing this story adds collides with `index`.
6. **The `SitemapPlugin` in `rxconfig.py:7` writes every registered route into `public/sitemap.xml`**, which ships into `/srv` and is served publicly by Caddy — the current file already lists the one page (`chat_ui/.web/public/sitemap.xml`). `generate_links_for_sitemap` reads `page.context.get("sitemap", {})` and **skips the page when that value is `None`** (`reflex_base/plugins/sitemap.py:154-161`). That is a documented per-page opt-out reached through `add_page`'s own `context=` kwarg, so it costs no new file and no plugin configuration. See Design decisions for why this story spends it.
7. **`rx.App.admin_dash` does not claim `/admin`.** `app.py:_setup_admin_dash` mounts `starlette_admin` only when `admin_dash` is set *and* `starlette_admin` is importable; `rxconfig.py` sets neither and the package is not in `requirements.txt`, so the frontend route `/admin` is free. Checked because that name collision is exactly the kind that surfaces at compile time rather than at review time.

---

## Patterns to Follow

### The one page registration this repo already has

```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:24-46,55-71
def index() -> rx.Component:
    return rx.fragment(
        rx.el.style(theme.GLOBAL_CSS),
        rx.cond(ChatState.user_id != "", rx.vstack(...), user_id_gate()),
    )

app = rx.App(api_transformer=fastapi_app, stylesheets=[theme.FONTS_HREF], ...)
app.add_page(index)
```

`index` takes no `route=` because its function name derives one. The admin pages must pass `route=` explicitly — the constants, not literals.

### Absolute imports, in the block that already exists

```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:14-17
from chat_ui import theme
from chat_ui.components.chat import chat_input, message_list
from chat_ui.components.shell import empty_state, header, user_id_gate
from chat_ui.state import ChatState
```

One line joins this block, alphabetically before `components.chat`:
`from chat_ui.components.admin_shell import (ROUTE_REGISTER, ROUTE_SUMMARY, VIEW_REGISTER, VIEW_SUMMARY, admin_page)`.

### The wrapper this story fills

```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:289-306
def admin_page(content: rx.Component, active: str) -> rx.Component:
    """The console's page wrapper: the gate, or the masthead over `content`."""
    return rx.fragment(
        rx.el.style(theme.GLOBAL_CSS),
        rx.cond(AdminState.authenticated, rx.vstack(admin_masthead(active), content, ...), admin_gate()),
    )
```

Its docstring carries a direct instruction to this story: *"STORY-010's page functions must not inject a second copy"* of `rx.el.style(theme.GLOBAL_CSS)`. The page functions call `admin_page(...)` and return its result unwrapped.

### The route constants, declared once

```python
# SOURCE: chat_ui/chat_ui/components/admin_shell.py:47-70
# "STORY-010 imports these to register the pages, so each route string is typed
#  once in the codebase and a moved page cannot leave the switch pointing at the
#  old path."
ROUTE_REGISTER = "/admin/audit"
ROUTE_SUMMARY = "/admin/stats"
VIEW_REGISTER = "register"
VIEW_SUMMARY = "summary"
```

### The subprocess probe shape the new test extends

```python
# SOURCE: tests/test_admin_shell.py:162-183
@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
             "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
             "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key")},
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"admin shell probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])
```

`tests/test_admin_shell.py:22-25` names this file as the one STORY-010 extends: *"STORY-010 should extend **this** file with its route-registration probe rather than `tests/test_chat_components_import.py`, which is the chat's smoke test and should stay that."* That supersedes the story's own Technical Note suggesting `test_chat_components_import.py` — the note was written before STORY-009 landed, and both land the same check in the same place either way.

### The FastAPI route table, read the way the reserved-route test reads it

```python
# SOURCE: tests/test_route_reservations.py:13-25
def _harness_route_paths():
    paths = set()
    for route in app.routes:
        if type(route).__name__ == "_IncludedRouter":
            paths.update(r.path for r in route.original_router.routes)
        elif hasattr(route, "path"):
            paths.add(route.path)
    return paths
```

The new probe reuses this shape verbatim against `app.main.app`, sampled **before and after** importing `chat_ui.chat_ui`. That is AC 2 made checkable rather than reviewed.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | One import line; two page functions; three `app.add_page` calls |
| `tests/test_admin_shell.py` | UPDATE (additive) | A second probe: the three routes are registered, `/admin` carries the redirect, and `app.main`'s route table is unchanged by the import |

Not touched, and each for a stated reason:

| File | Why it stays as it is |
|------|----------------------|
| `app/**` | PRD Section 4 and Section 10 — no new or modified endpoint anywhere in this PRD |
| `Caddyfile` | AC 4 — `/admin/*` is deliberately absent from `@backend_routes` and falls through to `file_server`; mechanism verified above |
| `tests/test_route_reservations.py` | AC 3 — it must pass with a **zero-line diff**, which is the whole point of the story |
| `chat_ui/chat_ui/components/admin_shell.py` | The constants are imported, not moved or re-declared |
| `chat_ui/chat_ui/theme.py`, `admin_copy.py` | No new token and no new string: this story renders no text of its own |
| `chat_ui/rxconfig.py` | The sitemap opt-out is per-page through `add_page(context=...)`; the plugin list stays as it is |

---

## Design decisions (settled before code)

**`/admin` is a third page with a redirect, not an alias.** Reflex has no route aliasing — a route maps to exactly one compiled page (`app.py:964`) — so "landing on the register" is either a second registration of the register component at `/admin` or a redirect. The redirect is chosen because it leaves **one canonical URL per view**: the masthead's switch links to `/admin/audit`, the summary's peer link points back to `/admin/audit`, and an admin who bookmarks the page bookmarks the path the switch highlights. Two URLs rendering the same register would leave `_view_link`'s `aria-current` correct on one and quietly wrong on the other, with no test spanning the two. `replace=True`, so the landing route leaves no history entry to bounce off.

**`/admin` renders the shell with empty content, not a blank fragment.** The redirect fires on load, which means it fires after the client connects — so *something* is on screen first. `admin_page(rx.fragment(), VIEW_REGISTER)` puts the gate there for an unauthenticated visitor (the correct screen for them regardless of the redirect) and the masthead for an authenticated one. A bare `rx.fragment()` would flash white. This is the frontend-design skill's *"an empty screen is an invitation to act"* applied to the one screen this story draws. It also stays right after STORY-011: `/admin` never builds a full register it is about to discard, because the content slot it passes is empty by construction.

**The page functions hold no content.** `register.py` and `summary.py` are STORY-011 and STORY-015. Their seam is `admin_page`'s `content` argument, so the two functions here pass `rx.fragment()` with a comment naming the story that replaces it. This story deliberately renders no text: a placeholder string would be user-facing copy with no home in `admin_copy.py`, and it would contradict AC 5 — *"renders the shell from STORY-009 and loads no data until the gate passes."*

**No `title=` or `description=`.** `add_page` defaults the title to `"{route} | {app_name}"` (`reflex_base/constants/route.py:75`). The chat page ships with that default today, and titling only the admin pages would introduce a user-facing string, a copy constant, and an inconsistency with `/` — three things this story's Technical Note ("the only change … is the two `app.add_page` calls and their imports") rules out. Recorded here so the omission reads as a decision rather than an oversight; a titled page set is a whole-app change and belongs in its own story.

**The console's routes are excluded from `sitemap.xml`.** `rxconfig.py:7` enables `SitemapPlugin`, which writes every registered route into `public/sitemap.xml`; that file ships into `/srv` and Caddy serves it publicly. Left alone, this story would publish `/admin`, `/admin/audit` and `/admin/stats` to anyone who fetches `/sitemap.xml`. The gate still holds — PRD Section 9's guarantee is that no data is readable without the token, not that the route is secret — so this is not a vulnerability. It is gratuitous, and Section 9's posture is that the console volunteers nothing. The opt-out is one kwarg per `add_page` call (`context={"sitemap": None}`, `reflex_base/plugins/sitemap.py:154-161`), it adds no file and no configuration, and it stays inside the story's "only the `add_page` calls" constraint. **If `/implement` judges it outside scope, drop it and say so in the report — but do not leave it undecided.**

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Register the three routes in `chat_ui.py`

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:14-17` (the import block), `:24-46` (`index`), `:71` (`app.add_page`)
- **Implement**:

  **1.1** Add one import to the existing block at `:14-17`, before `chat_ui.components.chat` so the block stays alphabetical:
  ```python
  from chat_ui.components.admin_shell import (
      ROUTE_REGISTER,
      ROUTE_SUMMARY,
      VIEW_REGISTER,
      VIEW_SUMMARY,
      admin_page,
  )
  ```
  Import the constants — never retype `"/admin/audit"` or `"/admin/stats"` in this file. `admin_shell.py:52-57` states why in its own comment, and Task 2 asserts the literals are absent from `chat_ui.py`.

  **1.2** Add two page functions after `index()` (`:46`):
  ```python
  def admin_register_page() -> rx.Component:
      return admin_page(rx.fragment(), VIEW_REGISTER)


  def admin_summary_page() -> rx.Component:
      return admin_page(rx.fragment(), VIEW_SUMMARY)
  ```
  Comment the `rx.fragment()` slot once, above both: it is the `content` argument STORY-011 (`register.py`) and STORY-015 (`summary.py`) fill, and it is empty rather than a placeholder because the shell is the whole of what this story renders. **Do not** wrap the result in another `rx.fragment` and **do not** add a second `rx.el.style(theme.GLOBAL_CSS)` — `admin_page` emits it, and its docstring at `admin_shell.py:296-300` says so.

  **1.3** Add the three registrations directly after `app.add_page(index)` (`:71`) and before the `register_lifespan_task` block, so the comment at `:73-77` still sits with the call it explains:
  ```python
  app.add_page(
      admin_register_page,
      route=ROUTE_REGISTER,
      context={"sitemap": None},
  )
  app.add_page(
      admin_summary_page,
      route=ROUTE_SUMMARY,
      context={"sitemap": None},
  )
  # /admin is a landing route, not a third view: it renders the same shell (so an
  # unauthenticated visitor sees the gate rather than a blank frame) and redirects
  # to the register on load. replace=True keeps it out of history, so Back does not
  # bounce off the redirect. Reflex has no route alias, and registering the register
  # at two paths would leave the masthead's aria-current right on one and wrong on
  # the other.
  app.add_page(
      admin_register_page,
      route="/admin",
      on_load=rx.redirect(ROUTE_REGISTER, replace=True),
      context={"sitemap": None},
  )
  ```
  Precede the block with a short comment naming the routing constraint — `/audit` and `/stats` belong to `app/routers/admin.py`, `tests/test_route_reservations.py` and the `Caddyfile`'s `@backend_routes` matcher, so the console lives one level down and needs no Caddyfile change (PRD Section 6). One comment for the block, not one per call. Add a second short comment on the `context={"sitemap": None}` kwarg (once, on the first call) naming `SitemapPlugin` — otherwise it reads as noise.

- **Do not**: touch `init_db()` (`:21`), the `api_transformer` wiring (`:55-64`) or `register_lifespan_task(pii_redactor.load)` (`:78`). The story's Technical Notes name all three, and the comments around them explain why each exists.
- **Validate**:
  ```bash
  cd chat_ui && ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key DATABASE_URL=sqlite:///:memory: \
    PYTHONPATH="$PWD;$PWD/.." python -c "from chat_ui.chat_ui import app; print(sorted(app._unevaluated_pages)); print({k: len(v) for k, v in app._load_events.items()})"
  ```
  Expect `['admin', 'admin/audit', 'admin/stats', 'index']` and `{'index': 0, 'admin/audit': 0, 'admin/stats': 0, 'admin': 1}` — the one load event being the redirect. Note the stored keys carry **no leading slash**: `format_route` strips it (`reflex_base/utils/format.py:315-329`). Do not "fix" that.

### Task 2: Extend `tests/test_admin_shell.py` with the route-registration probe

- **File**: `tests/test_admin_shell.py`
- **Action**: UPDATE (additive — a second `_CHECK_SCRIPT` and its own fixture; do not restructure the existing probe or any existing test)
- **Mirror**: `tests/test_admin_shell.py:80-183` (probe shape), `tests/test_route_reservations.py:13-25` (route-table walk)
- **Implement**: a second module-scoped fixture — `pages_probe` — running a second subprocess script that imports the **real** app object and reports:

  - `import app.main` **first**, snapshot `_harness_route_paths()`; then `from chat_ui.chat_ui import app as reflex_app`; then snapshot again. Report both sets. **AC 2**: they must be equal, and must contain `{"/query", "/audit", "/stats", "/health"}`. This is the strongest available statement of "the console adds no route" — stronger than reading a diff, because it also catches a route added as an import side effect.
  - `sorted(reflex_app._unevaluated_pages)` — **AC 1**: exactly `["admin", "admin/audit", "admin/stats", "index"]`. Assert the chat's `index` is still present in the same assertion, so a registration that displaced it fails here rather than in a browser.
  - `len(reflex_app._load_events["admin"]) == 1`, and `len(...) == 0` for `admin/audit` and `admin/stats` — `/admin` carries the redirect and neither view carries a load event, which is AC 5's *"loads no data until the gate passes"* stated at the route layer. `AdminState.load` must appear in no page's `on_load`.
  - the three admin route keys, each checked against Reflex's reserved set `{"/ping", "/_event", "/_upload"}` and against the backend's `{"/query", "/audit", "/stats", "/health"}` once the leading slash is restored — **AC 3** restated from the console's side, so the reserved-route guarantee is asserted by a test the console owns as well as by the one it must not modify.

  **Subprocess environment** — same `cwd`, `PYTHONPATH`, `ADMIN_TOKEN` and `OPENROUTER_API_KEY` as the existing fixture, **plus `DATABASE_URL` pointed at a throwaway path**. Importing `chat_ui.chat_ui` runs `init_db()` at module scope (`chat_ui.py:21`), which creates `harness_ai.db` in the CWD (`app/config.py:10`, `app/db/database.py:9-25`); without this the test writes a file into `chat_ui/` on every run. Use `sqlite:///` plus a `tmp_path_factory` path, or `sqlite:///:memory:` — and verify whichever is chosen actually leaves `chat_ui/harness_ai.db` absent after the suite, since `:memory:` works here only because `_db_path()` passes the suffix straight to `sqlite3.connect`.

  Add source assertions on `chat_ui.py` alongside the probe, in the shape of the existing `source` fixture tests (`:269-320`): the file contains neither the literal `"/admin/audit"` nor `"/admin/stats"` (they are imported), and it does contain `ROUTE_REGISTER` and `ROUTE_SUMMARY`. `"/admin"` itself **is** a literal in this file — the landing route has no constant, because it is not a view and `admin_shell` has no reason to name it — so do not assert against that one.

  Extend the module docstring: this file now covers the shell **and** its registration, and STORY-011/015 fill the `content` slot rather than adding pages.

- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/test_admin_shell.py -q` — every existing test in the file still passes, plus the new ones.

### Task 3: The untouched-surface check

- **File**: none — a verification pass
- **Action**: VERIFY
- **Implement**: run the regression suites this story's ACs are written against, and confirm each passes with a **zero-line diff** on the test file itself:
  - `tests/test_route_reservations.py` — AC 3, and `git diff --stat -- tests/test_route_reservations.py` must print nothing
  - `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_admin_auth.py`, `tests/test_main.py` — AC 2, the four REST contracts
  - `tests/test_chat_components_import.py`, `tests/test_chat_state.py` — AC 6, the chat surface
  - `git diff main --stat -- app/ Caddyfile` — must print nothing (ACs 2 and 4)
  - `git diff --stat` — must list exactly two paths: `chat_ui/chat_ui/chat_ui.py` and `tests/test_admin_shell.py`
- **Validate**: `ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/ -q` → **418 plus this story's new tests**, nothing previously green now red.

### Task 4: Compile and open the pages (the first run of the console)

- **File**: none — the run cycle
- **Action**: VERIFY
- **Implement**: this is the story `reflex-process-management` is mandated for, and the skill is unavailable — so follow the repo's own documented cycle and record the substitution in the report. From `chat_ui/`, with `ADMIN_TOKEN` and `OPENROUTER_API_KEY` set (README's documented run):
  1. `reflex run`. Watch the compile output: a route failing `verify_route_validity` or a page failing to build raises at compile time, not request time, so a clean compile is the first assertion. **Investigate any warning naming a route or a page — do not proceed past it.**
  2. Open `/` → the chat renders exactly as before (**AC 6**), with the `user_id` gate on a fresh session.
  3. Open `/admin/audit` → the console gate (**AC 5**). Open `/admin/stats` → the same gate. Neither loads data.
  4. Open `/admin` → lands on `/admin/audit`, address bar updated, and **Back does not bounce** (that is `replace=True`).
  5. Submit the configured `ADMIN_TOKEN` → the masthead appears; the switch's active word matches the path on both pages; **Register** ↔ **Summary** navigate without a full page reload (`rx.link` renders a React Router link — `reflex_components_radix/themes/typography/link.py:99-116`). The area under the masthead is empty, which is correct for this story.
  6. Sign out → the gate returns.
  7. `curl -s localhost:8000/health`, `curl -s -H "Authorization: Bearer $ADMIN_TOKEN" localhost:8000/audit`, and the same for `/stats` → unchanged shapes (**AC 2**). Mind the dev-mode backend port; in the container it sits one port behind Caddy.
  8. Stop the server before moving on — a stale dev server holding the port is the failure mode the skill exists to prevent.
- **Validate**: all eight steps observed. If the console cannot be reached at all, check the compiled route file first: `chat_ui/.web/app/routes/[admin].[audit]._index.jsx` must exist (`reflex/compiler/utils.py:679-684`).

### Task 5: Confirm the production path, which dev mode does not exercise

- **File**: none — a verification pass
- **Action**: VERIFY
- **Implement**: dev mode serves routes from the Vite dev server; production serves prerendered static files through Caddy, and **that** is the path AC 4 is about. Confirm it without changing the `Caddyfile`:
  - `docker compose build && docker compose up` (or `reflex export --frontend-only --no-zip` and inspect `.web/build/client/`), then confirm `admin/audit/index.html`, `admin/audit.html`, `admin/stats/index.html` and `admin/stats.html` all exist. Both spellings are expected — the second is `_duplicate_index_html_to_parent_directory` (`reflex/utils/build.py:173-193`), and it is what makes `try_files {path} {path}/` resolve.
  - Against the running container: `/admin/audit` and `/admin/stats` return **200** with the console's HTML, not `/404.html`; `/query`, `/audit`, `/stats`, `/health` still reverse-proxy to the backend (**AC 4**).
  - `curl -s localhost:8000/sitemap.xml` → contains `/` and **none** of the three admin routes (Task 1's `context={"sitemap": None}`). If the sitemap opt-out was dropped, say so in the report and expect three admin entries instead.
  - `git diff --stat -- Caddyfile` → prints nothing.
- **Validate**: all four observations recorded in the report. If the container build is unavailable in the environment, run the `reflex export` half — it is the half that proves the file layout — and record the container half as unverified rather than as passed.

---

## End-to-End Tests

`/implement` executes these:

- [ ] `python -m pytest tests/test_admin_shell.py -q` → the STORY-009 tests plus the new registration probe, all passing
- [ ] `python -m pytest tests/test_route_reservations.py -q` → passes, **and** `git diff --stat -- tests/test_route_reservations.py` prints nothing (AC 3)
- [ ] `python -m pytest tests/test_audit_router.py tests/test_stats_router.py tests/test_admin_auth.py tests/test_main.py -q` → passes unmodified (AC 2)
- [ ] `python -m pytest tests/test_chat_components_import.py tests/test_chat_state.py -q` → passes unmodified (AC 6)
- [ ] `python -m pytest tests/ -q` → 418 plus the new tests, all green
- [ ] `reflex run`, then `/` renders the chat unchanged (AC 6)
- [ ] `/admin/audit` and `/admin/stats` each render the gate; no data loads before the token is accepted (AC 5)
- [ ] `/admin` lands on `/admin/audit` with no extra history entry (AC 1)
- [ ] After the token: both pages render the masthead, the switch highlights the current view, and moving between them does not reload the page
- [ ] `GET /query /audit /stats /health` return their existing shapes against the running app (AC 2)
- [ ] The production export contains `admin/audit/index.html` **and** `admin/audit.html` (and the same pair for `stats`); both routes return 200 through Caddy (AC 4)
- [ ] `/sitemap.xml` lists `/` and no admin route
- [ ] `git diff main --stat -- app/ Caddyfile` → prints nothing (ACs 2, 4)
- [ ] `git diff --stat` → exactly `chat_ui/chat_ui/chat_ui.py` and `tests/test_admin_shell.py`
- [ ] `chat_ui/harness_ai.db` does not exist after the suite runs (the new probe must not write a database into the source tree)

## Validation

```bash
ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/test_admin_shell.py tests/test_route_reservations.py -q
ADMIN_TOKEN=test-token OPENROUTER_API_KEY=test-key python -m pytest tests/ -q
git diff main --stat -- app/ Caddyfile      # must print nothing
git diff --stat                              # exactly two paths
cd chat_ui && reflex run                     # then walk Task 4's eight steps
```

---

## Risks + Mitigations

**Risk 1 — `/admin` renders a page whose redirect never fires, stranding an admin on a blank frame.** `on_load` events run once the client connects to the backend; if the websocket is slow or blocked, the redirect waits. *Mitigation*: `/admin` renders the full shell rather than an empty fragment, so the pre-redirect screen is the gate (unauthenticated) or the masthead (authenticated) — both correct screens in their own right, neither blank. The redirect improves that screen; it is not what makes it valid. Task 4 step 4 observes it.

**Risk 2 — the sitemap opt-out is passed as `{}` or omitted, publishing the admin routes.** `page.context.get("sitemap", {})` skips the page only on an explicit `None`; `{}` is falsy but means *"default configuration"*, not *"exclude"* (`reflex_base/plugins/sitemap.py:154-161`). *Mitigation*: the exact literal is written into Task 1, and Task 5 checks the served `/sitemap.xml` rather than the source.

**Risk 3 — Caddy serves `/404.html` for the nested route in production.** Dev mode would not catch it: Vite resolves routes in-process, Caddy resolves them off the filesystem. *Mitigation*: the mechanism is verified above (prerender writes `admin/audit/index.html`; Reflex's own build step copies it to `admin/audit.html`; `try_files {path} {path}/` finds one of the two), and Task 5 confirms both files exist and both URLs return 200 before this story is called done. If they do not, the fix is **not** a `Caddyfile` edit — AC 4 forbids it — it is a prerender/export problem, and `REFLEX_SSR` / `should_prerender_routes()` (`reflex/utils/exec.py:866-874`) is where to look, since prerendering is what writes the per-route file at all.

**Risk 4 — the new probe writes `harness_ai.db` into `chat_ui/`.** Importing `chat_ui.chat_ui` calls `init_db()` at module scope. The file is gitignored (`.gitignore: *.db`), so it would pass review unnoticed and quietly appear in every contributor's tree. *Mitigation*: Task 2 pins `DATABASE_URL` in the subprocess env, and the E2E list checks the file's absence after the run.

**Risk 5 — a future edit retypes a route literal in `chat_ui.py`, and the masthead's switch drifts from the registered path.** *Mitigation*: Task 2's source assertions fail if `"/admin/audit"` or `"/admin/stats"` appears as a literal in `chat_ui.py`, which is the guard `admin_shell.py:52-57` asks for in prose.

**Risk 6 — registering pages changes what `reflex export` emits in the Docker builder stage, and the image breaks.** The builder runs `reflex export --frontend-only` with placeholder secrets (`Dockerfile:16-27`); the admin pages import `admin_state`, which imports `app.config.settings` and `app.db.database` — both already reached through `app.main` today, and neither constructs the PII analyzer. *Mitigation*: the import chain adds nothing new to the builder (`admin_shell` → `admin_state` → `app.db.database`, all already imported by `app.main`), and Task 5's export/build step is the check.

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given `chat_ui/chat_ui/chat_ui.py`, when the console is added, then `app.add_page(...)` registers `/admin/audit` and `/admin/stats`, and `/admin` lands on the register.
- [ ] Given the app, when its routes are listed, then no route is added to the FastAPI app — `app/routers/` is unchanged and `POST /query`, `GET /audit`, `GET /stats`, `GET /health` keep their exact contracts.
- [ ] Given `tests/test_route_reservations.py`, when the suite runs, then it passes **unmodified** — `/ping`, `/_event` and `/_upload` remain reserved and uncollided.
- [ ] Given the `Caddyfile`, when it is inspected, then it is unchanged — `/admin/*` is not in the `@backend_routes` matcher and falls through to the static `file_server`.
- [ ] Given each admin page, when it is opened, then it renders the shell from STORY-009 and loads no data until the gate passes.
- [ ] Given the existing chat page at `/`, when it is opened after this change, then it renders exactly as before.
- [ ] All tasks completed
- [ ] Full suite green at baseline (418) plus this story's new tests
- [ ] `git diff main --stat -- app/ Caddyfile` prints nothing
- [ ] Follows existing patterns
