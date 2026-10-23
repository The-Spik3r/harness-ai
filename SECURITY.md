# Security Policy

Harness AI sits in the path of LLM traffic that may carry sensitive prompts, so a
vulnerability here can expose data that never should have left a deployment. Reports
are taken seriously, and this document says how to send one and what to expect back.

## Supported versions

This is an actively developed project with a single `main` line of development. Security
fixes land on `main`; there is no separate long-term support branch. If you run a fork or
a pinned commit, confirm the issue reproduces against the current `main` before reporting,
and expect any fix to be delivered there.

| Version | Supported |
|---|---|
| `main` (latest) | ✅ |
| Older commits / forks | ❌ — rebase onto `main` |

## Reporting a vulnerability

**Please do not open a public issue, pull request, or discussion for a security report.**
A public report tells everyone about the weakness before there is a fix.

Report privately through GitHub:

1. Go to the repository's **Security** tab → **Report a vulnerability**
   (GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).
2. Describe the issue with enough detail to reproduce it:
   - what the vulnerability is and the impact you believe it has,
   - the steps, request, or payload that triggers it,
   - the affected component or file, if you know it,
   - any proof-of-concept, logs, or configuration needed to see it.

If private reporting is unavailable to you, open a **minimal** public issue that says only
*"security report — requesting a private channel"* with no technical detail, and a
maintainer will open a private advisory to continue in.

### What to expect

This is a small open-source project, so these are good-faith targets rather than a
contractual SLA:

- **Acknowledgement** within about 5 business days.
- **An initial assessment** — whether it is confirmed, needs more information, or is out of
  scope — once the report has been reviewed.
- **Updates** as a fix is worked on, and notice when it lands on `main`.
- **Credit** for the report in the advisory or release notes, if you want it. Tell us the
  name or handle to use, or ask to stay anonymous.

Please give a reasonable window to ship a fix before disclosing publicly. Coordinated
disclosure keeps users safe while the hole is open.

## Scope

**In scope** — anything that undermines the controls the project exists to provide:

- Bypassing the pipeline — reaching OpenRouter without passing identity resolution,
  authorization, the usage gate, the duplicate check, the pattern check, or PII redaction.
- **PII leakage** — unredacted personal data reaching the provider under the `chat` profile,
  or reaching a caller in a response, outside the limitations already documented in
  [`docs/features.md`](docs/features.md#pii-redaction).
- **Authentication or authorization flaws** — resolving to the wrong identity or role,
  escalating privilege, or acting on a self-declared `user_id` instead of the verified
  token.
- **Cross-tenant access** — reading, writing, or probing another account's chat
  transcripts, audit rows, or usage counters.
- **Audit integrity** — causing a request to leave no audit row, or to write a false one.
- **Secret exposure** — leaking `ADMIN_TOKEN`, `TURSO_AUTH_TOKEN`, `OPENROUTER_API_KEY`, or
  a user token through logs, errors, or responses.
- **Denial of service** reachable by an authenticated caller, such as a pattern regex that
  backtracks catastrophically (see [`docs/features.md`](docs/features.md#pattern-policy)).

**Out of scope** — these are known trade-offs or operator responsibilities, documented
rather than secret:

- The accepted weaknesses already written up in the README and `docs/` — the per-account
  duplicate scope, the post-upgrade duplicate gap, budget overshoot, the fixed rate window,
  and the `code` profile's unmasked fenced blocks and response.
- A deployment that disables a control on purpose (`PII_REDACTION_ENABLED=false`,
  `RBAC_ENABLED=false`, `USAGE_LIMITS_ENABLED=false`, `CHAT_HISTORY_ENABLED=false`).
- Misconfiguration of the operator's own environment — a leaked `.env`, a world-readable
  Turso token, a database exposed to the public internet.
- Vulnerabilities in third-party dependencies, unless this project uses them in a way that
  makes the issue exploitable here — report those upstream, and tell us if we need to pin
  or patch.
- Anything requiring an attacker who already holds a valid `admin` credential.

## A note on handling sensitive data in reports

A good report sometimes needs a sample prompt or payload to prove the point. Please use
**invented** data, never a real person's PII or a production secret. If the only way to show
the issue is with real data, say so and share the minimum needed through the private
advisory — do not attach it to anything public.
