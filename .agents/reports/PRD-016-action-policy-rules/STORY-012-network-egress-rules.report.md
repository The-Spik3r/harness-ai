---
story: STORY-012
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-012-network-egress-rules.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 33c5327
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-012: Network egress rules — URL parse, IDNA, allowlist, reserved addresses

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-012-network-egress-rules.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `33c5327`

## Summary

New pure module `app/services/action_classifiers/network.py` (PRD-016 F5, Section 6.3 network rows, Section 6.5, D5, T5, T8, T11):

- `classify_url(url, network_allow=(), *, source_tool="") -> Classification` returns exactly one of `net.allowlisted`, `net.unlisted` or `net.unparsed`.
- Parsing (`_host`, first failure wins, each one `net.unparsed`): a non-`str` input; `urlsplit` raising; a scheme other than `http`/`https`; any `@` in the authority (the detail is `"@"`, never the userinfo); no host or a bad port; a bracketed host that is not a zone-free IPv6 address; IDNA deviation characters (`ß`, `ς`, ZWNJ, ZWJ) or an IDNA codec failure; a numeric last label that is not a canonical dotted quad (an obfuscated IPv4); and a host that is not RFC 1123 after IDNA.
- Matching: an IP literal matches only an IP entry, by `ipaddress` equality, and never a wildcard. A name matches an exact entry, or a `*.` suffix of at least two labels at any depth, never the apex. Wildcards never match `localhost`, `*.localhost` or `metadata.google.internal`. Entries are lowercased, and malformed ones are skipped.
- The detail comes from the call, never from an entry, and is capped at 32 characters, keeping the tail. The module never raises (an internal error gives `net.unparsed` with detail `""`). It does no settings access, no I/O and no DNS; the residual DNS risk (`*.nip.io`, rebinding) is in the docstring for STORY-018 and STORY-020.

Orchestrator decisions applied:
1. Plain-argument signature.
2. AC3 is tested with the story's `*.internal` passed directly and with `*.corp.internal`.
3. IDNA deviation characters are `net.unparsed`.
4. Wildcards never match `localhost`, `*.localhost` or `metadata.google.internal`.
5. No DNS, with the gap documented in the docstring.
6. and 7. Delegated to STORY-013 and STORY-015; the orchestrator recorded both in those stories, and this commit carries those edits.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `classify_url`, `_host`, `_entries`, `_allowlisted`, `_is_name`, `_cap_tail`, module docstring | `app/services/action_classifiers/network.py` | ✅ |
| 2 | AC tables, T8 seeds, T11 detail, bad entries, never-raises, purity / no-DNS, loader round trip | `tests/test_action_network.py` | ✅ |
| 3 | Targeted regression run | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| `tests/test_action_network.py` | ✅ 96 passed |
| Targeted set (`test_action_network`, `test_action_vocabulary`, `test_action_config`, `test_untouched_app`) | ✅ 324 passed, 0 failed, 0 skipped |
| Full suite | Deferred to the orchestrator (user decision) |
| E2E | ✅ 3/3: fresh-process import loads only the package chain and no `socket`; the AC URLs classify unchanged with `socket` lookups monkeypatched to raise; the backend imports |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_classifiers/network.py` | CREATE | +240 |
| `tests/test_action_network.py` | CREATE | +391 |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-012-network-egress-rules.plan.md` | CREATE (archived) | +229 |
| `.agents/reports/PRD-016-action-policy-rules/STORY-012-network-egress-rules.report.md` | CREATE | this file |
| `.agents/stories/PRD-016-action-policy-rules/STORY-012-network-egress-rules.md` | UPDATE | frontmatter |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE | regenerated |
| `.agents/stories/PRD-016-action-policy-rules/STORY-013-*.md`, `STORY-015-*.md`, `STORY-018-*.md`, `STORY-020-*.md` | UPDATE | the orchestrator's note edits, carried in this commit |

## Deviations from Plan

- **Signature (deliberate, recorded in the plan as decision 1):** the story and F5 write `classify_url(url, policy)`. The implemented signature is `classify_url(url, network_allow=(), *, source_tool="")`, which matches the sibling classifiers.
- **The story's numeric-host rule is generalized:** the story says a host that is "all digits or fewer than four parts" is unparsed. The module instead treats a host as unparsed when its last label is numeric (decimal, or hex starting with `0x`) and the host is not a canonical dotted quad, which covers the story's cases and more.
- **IP literals never match a wildcard, public ones included.** This is stricter than the story note, which excludes only loopback, link-local, private and reserved addresses.
- Otherwise none.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_network.py` | AC1 allowlist table (exact, wildcard, apex, depth, label boundary, port) and case/trailing dot; AC2 empty allowlist (default, `()`, built-in); AC3 reserved addresses under two wildcard lists, exact IP/name entries, metadata name, `*.localhost`, IPv4-mapped, IP never by wildcard, range sanity; AC4 29 unparsed URLs, userinfo never echoed, IDNA ASCII comparison (punycode, fullwidth, ideographic stop, Cyrillic lookalike), authority boundary; operation/detail shape, tail cap, detail never from entry, bad-scheme detail, vocabulary; bad entries skipped; never raises; internal error fails closed; AC5 source scan, fresh-process import (no settings, no `socket`), runtime no-DNS; loader round trip from a policy file |

## Acceptance Criteria

- [x] AC1: `registry.npmjs.org` and `*.githubusercontent.com` give `net.allowlisted` for the two listed URLs, and the apex and `evil.example` give `net.unlisted` (`test_ac1_allowlist`).
- [x] AC2: with an empty allowlist, a parseable URL is `net.unlisted` (`test_ac2_empty_allowlist_lists_nothing`).
- [x] AC3: none of the reserved addresses matches `*.amazonaws.com`/`*.internal`, and an exact `127.0.0.1` entry gives `net.allowlisted` (`test_ac3_reserved_addresses_never_match_a_wildcard`, `test_ac3_an_exact_entry_allowlists_a_reserved_address`).
- [x] AC4: userinfo, bad schemes, no host, a decimal IP and IDNA failures are `net.unparsed`, and IDNA hosts are compared in punycode (`test_ac4_unparsed`, `test_ac4_idna_is_compared_in_ascii_form`).
- [x] AC5: no settings, no DNS and no I/O (`test_network_module_stays_pure`, `test_importing_network_loads_no_settings_and_no_socket`, `test_no_dns_lookup_at_classification`).
- [x] Backend imports without error.
