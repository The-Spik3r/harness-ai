---
id: STORY-012
prd: PRD-016
slug: network-egress-rules
title: Network egress rules — URL parse, IDNA, allowlist, reserved addresses
type: feature
priority: high
complexity: small
phase: "3 - Classifiers and the engine"
status: done
labels: [backend, security, classifier]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-012-network-egress-rules.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-012-network-egress-rules.report.md
commit: 33c5327
depends_on: [STORY-006]
blocks: [STORY-013]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-012: Network egress rules — URL parse, IDNA, allowlist, reserved addresses

## Description

As a security admin, I want every URL a tool call reaches checked against the deployment's host allowlist, with wildcards that can never reach loopback or the metadata endpoint, so that egress is something the deployment wrote rather than something an agent chose.

## Acceptance Criteria

- [ ] Given an allowlist of `registry.npmjs.org` and `*.githubusercontent.com`, when `classify_url` runs on `https://registry.npmjs.org/x` and `https://raw.githubusercontent.com/x`, then `net.allowlisted`; on `https://githubusercontent.com/x` (apex) and `https://evil.example`, then `net.unlisted`.
- [ ] Given an empty allowlist, when any parseable `http(s)` URL is classified, then `net.unlisted`.
- [ ] Given `http://169.254.169.254/latest`, `http://localhost:8000`, `http://127.0.0.1`, `http://[::1]`, `http://10.0.0.1` with `*.amazonaws.com` and `*.internal` allowlisted, when classified, then none matches a wildcard (`net.unlisted`); listing `127.0.0.1` exactly makes it `net.allowlisted`.
- [ ] Given `https://allowed.com@evil.com/`, `ftp://x`, `file:///etc/passwd`, `//nohost`, `not a url`, a decimal-IP host such as `http://2852039166/`, or an IDNA failure, when classified, then `net.unparsed`; an IDNA hostname is compared in its ASCII (punycode) form.
- [ ] Given the module, when imported, then it reads no settings and performs no DNS lookup or other I/O.

## Technical Notes

- New `app/services/action_classifiers/network.py`: `classify_url(url, policy) -> Classification`.
- `urllib.parse.urlsplit`; host lowercased and IDNA-encoded with `encodings.idna`; `ipaddress.ip_address` for literals, with `is_loopback`, `is_link_local`, `is_private` and `is_reserved` excluded from wildcard matching (PRD Section 6.5, T8).
- A host that is all digits (or a dotted form with fewer than four parts) is an obfuscated IP: classify it `net.unparsed` rather than guessing.
- Tests: new `tests/test_action_network.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 6.3 (network rows), 6.5, 7 (F5), 9.2 (T8)
