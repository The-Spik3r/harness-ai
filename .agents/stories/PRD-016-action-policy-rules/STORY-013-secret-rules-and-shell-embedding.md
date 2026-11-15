---
id: STORY-013
prd: PRD-016
slug: secret-rules-and-shell-embedding
title: Secret access rules, and shell embedding of SQL, URLs and secret reads
type: feature
priority: high
complexity: medium
phase: "3 - Classifiers and the engine"
status: done
labels: [backend, security, classifier]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-013-secret-rules-and-shell-embedding.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-013-secret-rules-and-shell-embedding.report.md
commit: pending
depends_on: [STORY-008, STORY-010, STORY-011, STORY-012]
blocks: [STORY-014]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-013: Secret access rules, and shell embedding of SQL, URLs and secret reads

## Description

As a security admin, I want reads of credentials and secret environment variables denied wherever they appear, including inside a shell command, and I want SQL and URLs inside shell commands classified by their own classifiers, so that `psql -c "DROP …"` and `printenv OPENROUTER_API_KEY` are caught for what they are.

## Acceptance Criteria

- [ ] Given a read (tool or shell) of `.env`, `~/.aws/credentials`, `.ssh/id_rsa`, `x.pem`, `.npmrc`, when classified, then `secret.read`; a read of `src/a.ts` stays `fs.read` (completing STORY-011's hook).
- [ ] Given `printenv OPENROUTER_API_KEY`, `echo $AWS_SECRET_ACCESS_KEY`, `echo ${GITHUB_TOKEN}`, and `env` or `printenv` with no arguments, when classified, then `secret.read`; `echo $HOME` and `printenv PATH` do not produce `secret.read`.
- [ ] Given `psql -c "DROP TABLE t"`, `mysql -e "DELETE FROM t"`, `sqlite3 app.db "DROP TABLE t"`, when classified, then the SQL classification (`sql.ddl`, `sql.unscoped_write`) is present and ordered **before** the head's own rule in that segment (PRD Section 6.4).
- [ ] Given `curl https://evil.example/x` and `wget http://169.254.169.254/`, when classified, then the segment yields the head's rule and the network classification (`net.unlisted`), network first.
- [ ] Given an OpenCode `glob` with `pattern: "../../**/.env*"`, or a `grep`/`search_codebase`/`search_files` whose path or include pattern matches a secret glob, when classified, then `secret.read`; a search over a plain directory (`.`, `src/`) stays `fs.read` (PRD D15, a stated limitation).
- [ ] Given `cat .env | grep KEY`, when classified, then `secret.read` is present; given an `env` pattern list replaced in the policy file, then only the configured patterns match.

## Technical Notes

- Orchestrator decision (STORY-012 plan): `classify_url(url, network_allow, *, source_tool=...)` takes plain arguments, so widen `classify_shell` to receive `network_allow` (and the secret globs). A scheme-less curl/wget URL word (`curl evil.com`) is classified as `http://<word>` (curl's own default), not left as `net.unparsed`.
- Orchestrator decision (STORY-011 plan): exempt device targets (`/dev/null`, `/dev/stdout`, `/dev/stderr`, `/dev/tty`, `NUL`, `CON`) before routing a redirect to `paths.classify_write(target, protected, roots, source_tool=...)`. Fill the `classify_read` secret hook and remove the `xfail(strict=True)` marker on the secret-read test in `tests/test_action_paths.py`.
- Orchestrator decision (STORY-010 plan): output redirects (`Segment.redirects`, `>`/`>>` targets) are file writes; route each redirect target through the STORY-011 path rules as an `fs_write` (and `<` targets as `fs_read` for the secrets check), so `ls > ~/.bashrc` under an allowlisted head is caught. The STORY-010 hook is the named comment at step 3 of `_segment_rules`.
- Orchestrator decision (STORY-006 plan): secret env/file globs come compiled from `action_config` (name globs anchored `^...$`, path globs `(?:^|/)...$`, IGNORECASE); `secrets.env` includes `OPENROUTER_*`. Consume them, do not re-translate.
- New `app/services/action_classifiers/secrets.py`: `classify_secret_read(target, policy)`, `classify_env_reference(name, policy)`. Env patterns are globs matched case-insensitively against the variable name.
- Extend `shell.py`: per segment, route embedded targets for heads `psql` (`-c`, `--command`), `mysql` (`-e`, `--execute`), `sqlite3` (second positional), `curl` / `wget` / `http` / `https` (URL arguments), and `cat`, `less`, `more`, `head`, `tail`, `printenv`, `env`, `echo` (paths and `$NAME` / `${NAME}` references). Wire `classify_read`'s secret hook from STORY-011.
- Ordering inside a segment: embedded classifications first, then the head's rule.
- Tests: new `tests/test_action_secrets.py`; extend `tests/test_action_shell.py` with embedding cases.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-008, STORY-010, STORY-011, STORY-012
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Classifiers: embedded classification, secrets), 6.3 (secret row), 6.4, 6.6 (`secrets`), 7 (F3, F6)
