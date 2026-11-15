---
story: STORY-012
prd: PRD-016
slug: network-egress-rules
title: Network egress rules — URL parse, IDNA, allowlist, reserved addresses
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Network egress rules — URL parse, IDNA, allowlist, reserved addresses

## Summary

Add the pure network classifier `app/services/action_classifiers/network.py`, which implements PRD-016 F5, Section 6.5's network paragraph and threat T8. `classify_url(url, network_allow=(), *, source_tool="")` returns exactly one `Classification`: `net.allowlisted`, `net.unlisted` or `net.unparsed`. It parses with `urllib.parse.urlsplit` and accepts only `http`/`https`. Any `@` in the authority (userinfo) is `net.unparsed`. The host is lowercased, one trailing dot is stripped, and the host is IDNA-encoded with stdlib `encodings.idna`, so comparison happens in ASCII/punycode form. Every label must then be RFC 1123. A host whose last label is numeric must be a canonical dotted-quad IPv4, or it is an obfuscated IP and therefore `net.unparsed`. Bracketed hosts must be IPv6 with no zone. An IP literal matches only an IP entry, by `ipaddress` equality, and never a wildcard. A name matches an exact entry, or a `*.` wildcard that covers subdomains (never the apex) with at least two suffix labels. `localhost`, `*.localhost` and `metadata.google.internal` are never matched by a wildcard. The module does no DNS, no I/O and reads no settings. It takes the allowlist as a plain argument, as its siblings do, so STORY-013 can call it for `curl`/`wget` URL words. New tests go in `tests/test_action_network.py`.

## User Story

As a security admin
I want every URL a tool call reaches checked against the deployment's host allowlist, with wildcards that can never reach loopback or the metadata endpoint
So that egress is something the deployment wrote rather than something an agent chose.

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-012-network-egress-rules.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`: Section 3 (no DNS, line 32), Section 4 checklist (line 69), Section 6.3 network rows (lines 244-246), Section 6.5 network paragraph (line 270), F5 (lines 493-494), T5 (line 547), T8 (line 550), out of scope (line 569), functional criterion (line 641), evasion corpus (line 659), D5 (line 728)
- Threat model: `.agents/spikes/PRD-016-action-policy-rules/threat-model.md:30` (T8 -> STORY-012, STORY-018)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW (story: small) |
| Systems Affected | `app/services/action_classifiers/` (new module), tests |
| Story | STORY-012 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design`. This story has no UI, and the story's `skills: []` agrees | — |

---

## Design decisions

1. **Signature: plain arguments, not `policy`.** The story and F5 write `classify_url(url, policy)`. The siblings take the policy's data as arguments: `classify_shell(command, shell_allow=(), *, source_tool="")` (`shell.py:1286`) and `classify_write(path, protected, workspace_roots=(), *, source_tool="")` (`paths.py:218`), per STORY-011 plan decision 1 (`paths.py:3-9`). Mirror them with `classify_url(url, network_allow=(), *, source_tool="") -> Classification`. The default `()` is the built-in value (`action_config.py:178-180`), and with it every URL is `net.unlisted` or `net.unparsed`. STORY-014 calls `classify_url(op.target, policy.network_allow, source_tool=op.source_tool)`. STORY-013 will call it for each URL word of `curl`/`wget`, and it will have to thread `network_allow` into `classify_shell` (today it takes only `shell_allow`). This deviation from the story text is deliberate. Record it in the report.
2. **One `Classification`**, as F5 says and as `classify_write` already does (`paths.py:7-9`). STORY-014 wraps it in a tuple.
3. **Parse order (first failure wins, each one `net.unparsed`):**
   1. A non-`str` gives detail `""` and target `""`.
   2. `urlsplit(url)` raises `ValueError`. Probed on 3.12.10: an unclosed `[::1`, a bracketed non-IP `[evil.com]`, and NFKC-invalid netlocs such as `℀.com` all raise. Note that `urlsplit` strips leading/trailing C0 and space and removes tab/CR/LF anywhere, as WHATWG does (`http://ev\til.com` becomes host `evil.com`). The adapter already refuses line breaks in `http` targets (`action_adapters.py:412-424`).
   3. The scheme (which urlsplit lowercases) is not `http`/`https`. This covers `ftp://x`, `file:///etc/passwd`, and the empty scheme of `//nohost` and `not a url`. `https:evil.com` and `http:\\evil.com` parse with an empty netloc, so they fail at step 5.
   4. An `@` anywhere in `netloc` (userinfo, T8), including an empty user (`http://@x.com`). The detail is `"@"`, never the userinfo, which can be a credential (`user:token@host`, T11). `urlsplit` stops the netloc at the first `/?#`, so `http://a/b@c` (an `@` in the path) and `http://allowed.com#@evil.com` (host `allowed.com`) are fine. Both agree with browsers.
   5. `hostname` is `None` or empty, or `.port` raises (`x:abc`, `x:99999`). The port is otherwise ignored, because the allowlist is per host.
   6. **Bracketed host** (`netloc` host part starts with `[`): `ipaddress.ip_address(host)` must be an `IPv6Address`, and a `%` (zone id, `[fe80::1%25eth0]`) is `net.unparsed`. Otherwise it goes to the IP-literal path.
   7. **Name host:** strip exactly one trailing `.` (`registry.npmjs.org.` is the same DNS name; `a..` keeps an empty label and fails). If the host is non-ASCII and holds an IDNA2003/IDNA2008 *deviation* character (U+00DF `ß`, U+03C2 `ς`, U+200C ZWNJ, U+200D ZWJ), it is `net.unparsed`. Otherwise `host.encode("idna").decode("ascii").lower()`; a `UnicodeError` is `net.unparsed` (IDNA failure). Rationale for the deviation set: probed, stdlib `encodings.idna` is IDNA 2003 and maps `straße.de` to `strasse.de`, while IDNA2008/UTS46-nontransitional clients reach `xn--strae-oqa.de`, a different host. Comparing either form could allow a host the client never reaches, so fail closed. Other nameprep mappings agree with what clients do: fullwidth `ｅｖｉｌ.com` and `evil。com` become `evil.com`, and a ZWSP is dropped. A lookalike such as Cyrillic `аpple.com` becomes `xn--pple-43d.com` and so cannot match `apple.com`.
   8. The ASCII host is longer than 253 characters, or a label does not match RFC 1123 (`[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?`, the same as `action_config._HOST_LABEL` at `action_config.py:536`). The regex is duplicated in the module because a pure module cannot import `action_config`. This catches `evil.com\.allowed.com` (urlsplit keeps the `\` in the host, while a browser reads it as a path separator to `evil.com`, which a wildcard `*.allowed.com` would otherwise match), percent-encoding (`%31%32%37.0.0.1`), `_`, spaces and other junk. All of them are `net.unparsed`, the non-grantable D5 outcome, rather than a grantable `net.unlisted`.
   9. **Numeric last label = an IPv4 attempt** (WHATWG: a host whose last label is numeric is parsed as IPv4). If the last label is all digits or `0x` hex, the host must parse as `ipaddress.IPv4Address`, which on 3.12 refuses leading zeros, short forms and hex. Otherwise it is an obfuscated IP and therefore `net.unparsed`: `2852039166`, `127.1`, `0177.0.0.1`, `0x7f.0.0.1`, `1.2.3.0x4`, `1.2.3.4.5`. This generalizes the story's "all digits or fewer than four parts" rule and mirrors the loader's "last label not all digits" (`action_config.py:549-558`).
4. **Matching.**
   - **IP literal** (from step 6 or step 9): `net.allowlisted` if and only if an entry parses with `ipaddress.ip_address` and is equal to it, so `[0:0::1]` equals entry `::1`. **Never by wildcard.** This is stricter than the story note's `is_loopback / is_link_local / is_private / is_reserved` exclusion, because it excludes every literal, public ones included. It is also already true by construction, because the loader refuses a wildcard whose suffix ends in a numeric label (`action_config.py:549-591`). The classifier enforces it anyway (defence in depth against an unvalidated tuple), and a test asserts the four predicates hold for the AC3 addresses. An IPv4-mapped `[::ffff:127.0.0.1]` does not equal entry `127.0.0.1`, so it is `net.unlisted` and fails closed.
   - **Name:** exact match against a lowercased, non-wildcard, non-IP entry gives `net.allowlisted`. Otherwise, for each `*.` entry whose lowercased suffix is a valid hostname of **at least two labels** (re-checked here, mirroring the STORY-007 refusal at `action_config.py:576-585`; a `*.com` or `*.internal` passed directly is skipped), `host.endswith("." + suffix)` gives `net.allowlisted`. That covers any depth (`a.b.githubusercontent.com`), but not the apex and not `evilgithubusercontent.com`. Exception: a host in `_NEVER_BY_WILDCARD` (`localhost`, `metadata.google.internal`) or ending in `.localhost` (RFC 6761 loopback names) is never matched by a wildcard, only by an exact entry (Section 6.5). Everything else is `net.unlisted`.
   - Entries that are not `str`, or that match none of the three shapes, are skipped.
5. **`operation` and `detail`.** `Operation("http", url, source_tool)` with the whole input as the target, as `sql.py`/`shell.py`/`paths.py` do it (`paths.py:76-81`). The detail always comes from the call, never from an entry (T11), and is at most 32 characters. For allowlisted and unlisted it is the canonical ASCII host, keeping the **end** (the registrable domain names it), as `paths._cap_tail` does (`paths.py:181-182`). For unparsed it is the scheme for a bad scheme (`ftp`), `"@"` for userinfo, the raw host text for a bad, obfuscated or IDNA-failing host, and `""` for no host or a non-`str`.
6. **Never raises.** Any `Exception` becomes `net.unparsed` with detail `""`. That is the strictest outcome and non-grantable (T5), so a bug fails closed. `BaseException` is not caught (`shell.py:1295-1296`).
7. **No DNS.** PRD Section 3 (line 32) and Out of scope (lines 121, 569) exclude DNS resolution explicitly, so this is not an open question. The residual risk goes in the module docstring for STORY-018/020: a wildcard over a name that *resolves* to a private address (`*.nip.io`, `127.0.0.1.nip.io`, or DNS rebinding under an allowlisted wildcard) is matched by name. Only an exact operator choice opens such a domain.

---

## Patterns to Follow

### Module shape: docstring cites PRD and decisions, pure, never raises, keyword-only `source_tool`
```python
# SOURCE: app/services/action_classifiers/paths.py:218-243
def classify_write(path: str, protected, workspace_roots=(), *, source_tool: str = "") -> Classification:
    """Classify a write of `path` (PRD-016 F4, Section 6.5). Never raises.
    ...
    """
    op = Operation(kind="fs_write", target=path if isinstance(path, str) else "", source_tool=source_tool)
    try:
        if not isinstance(path, str):
            return Classification("fs.write_protected", op, "")
        ...
    except Exception:
        return Classification("fs.write_protected", op, "")
```

### Loader side: what an entry can be (the classifier matches exactly these three shapes)
```python
# SOURCE: app/services/action_config.py:536, 549-591
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
def _is_hostname(value): ... return not labels[-1].isdigit()
def _check_network_entry(source, entry):
    ipaddress.ip_address(entry) | _is_hostname(entry) | "*." + hostname with "." in it
    # "Case is accepted as written; STORY-012 matches case-insensitively."
```

### Vocabulary
```python
# SOURCE: app/services/action_classifiers/__init__.py:31, 69-72, 88-101, 106-131
OperationKind = Literal["shell", "sql", "fs_write", "fs_read", "http"]
"net.allowlisted", "net.unlisted", "net.unparsed"      # net.unparsed is in NON_GRANTABLE_RULES
Operation(kind, target, source_tool); Classification(rule, operation, detail)
```

### Error handling (fail closed, the strictest rule of the family)
```python
# SOURCE: app/services/action_classifiers/shell.py:1286-1310 / sql.py:314-336
    except Exception:
        return (Classification("shell.unclassifiable", op, _first_word(command)),)
```

### Tests: table-driven literals from the ACs, never-raises, purity via source scan + subprocess import
```python
# SOURCE: tests/test_action_paths.py:1-45 (header, env setdefault, imports), 333-343 (never raises with explicit ids),
#         363-371 (internal error via monkeypatch), 377-411 (purity: source scan + fresh-process sys.modules)
def test_importing_paths_loads_no_settings():
    completed = subprocess.run([sys.executable, "-c", "import sys, app.services.action_classifiers.paths; print(sorted(...))"], ...)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_classifiers/network.py` | CREATE | `classify_url` (F5) plus private helpers; docstring documents decisions 1-7 |
| `tests/test_action_network.py` | CREATE | The five ACs, the T8 evasion seeds, never-raises, purity / no-DNS |

No pre-existing module changes. `action_config.py` already validates and stores `network_allow`. The `__init__.py` vocabulary already holds the three ids and the `http` kind. `action_policy`/`evaluate` wiring is STORY-014's, and shell embedding is STORY-013's.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `network.py`

- **File**: `app/services/action_classifiers/network.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring in the `paths.py:1-89` style: the PRD sections (6.3 network rows, 6.5, F5, T8, T5, T11, D5), the parse order (decision 3), the matching (decision 4), the detail (decision 5), never-raises (decision 6), and the no-DNS residual risk (decision 7). Name STORY-013 as the shell caller and STORY-014 as the engine caller, with the exact call.
  - Imports: `ipaddress`, `re`, `from typing import Optional`, `from urllib.parse import urlsplit`, `from app.services.action_classifiers import Classification, Operation`. Use `str.encode("idna")`, which loads `encodings.idna` through the codec registry; an explicit `import encodings.idna` is fine too. Do not import `socket`, `urllib.request` or `action_config`.
  - Constants: `_DETAIL_MAX = 32`, `_SCHEMES = frozenset({"http", "https"})`, `_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")` (comment: same as `action_config._HOST_LABEL`, applied after lowercasing), `_NUMERIC_LABEL = re.compile(r"[0-9]+|0x[0-9a-f]*")`, `_IDNA_DEVIATIONS = frozenset("ßς‌‍")`, `_NEVER_BY_WILDCARD = frozenset({"localhost", "metadata.google.internal"})`.
  - `_cap_tail(text)`.
  - `_host(url) -> tuple[Optional[str|IPv4Address|IPv6Address], Optional[str]]`, or a small private frozen dataclass. It returns either the canonical name or IP, or the unparsed detail, following decision 3. Implementer's choice of shape. Keep it one function with early returns and a comment per step.
  - `_entries(network_allow)`: split the entries into `(ips: tuple, exact: frozenset[str], suffixes: tuple[str, ...])`, lowercased, skipping non-`str` and malformed entries and single-label wildcard suffixes (decision 4).
  - `classify_url(url, network_allow=(), *, source_tool="") -> Classification`, with the docstring as in `paths.py:219-229`: what each rule means, the STORY-014/013 call shape, and never raises.
- **Mirror**: `app/services/action_classifiers/paths.py:91-102, 181-182, 218-243`
- **Validate**: `.venv/Scripts/python -c "from app.services.action_classifiers.network import classify_url; print(classify_url('https://registry.npmjs.org/x', ('registry.npmjs.org',)).rule)"` prints `net.allowlisted`, and `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints `OK`.

### Task 2: Create `tests/test_action_network.py`

- **File**: `tests/test_action_network.py`
- **Action**: CREATE
- **Implement** (header as in `tests/test_action_paths.py:1-45`: a docstring citing PRD-016 STORY-012, F5, 6.5 and T8, the `os.environ.setdefault` lines, and the literals transcribed from the ACs rather than derived from the module):
  - **AC1** (parametrized): with `ALLOW = ("registry.npmjs.org", "*.githubusercontent.com")`, `https://registry.npmjs.org/x` and `https://raw.githubusercontent.com/x` give `net.allowlisted`; `https://githubusercontent.com/x` (apex) and `https://evil.example` give `net.unlisted`. Add `https://a.b.githubusercontent.com/x` (depth) giving allowlisted, `https://evilgithubusercontent.com/` giving unlisted, and case and trailing dot (`HTTPS://Registry.NPMJS.org./x`, entry `Registry.npmjs.org`) giving allowlisted.
  - **AC2**: with an empty allowlist (the default and `()`), a handful of parseable URLs (`https://example.com`, `http://8.8.8.8/`, `http://[2001:db8::1]/`, `http://localhost`) give `net.unlisted`.
  - **AC3**: with `("*.amazonaws.com", "*.internal")` passed directly (the loader would refuse `*.internal`, STORY-007 decision; the test says so), also with `("*.amazonaws.com", "*.corp.internal", "*.localhost.example")`, the URLs `http://169.254.169.254/latest`, `http://localhost:8000`, `http://127.0.0.1`, `http://[::1]` and `http://10.0.0.1` all give `net.unlisted`. With exact `127.0.0.1` listed, `http://127.0.0.1` gives `net.allowlisted`, and so does `[::1]` with `::1` or `0:0::1` listed. With `*.google.internal`, `http://metadata.google.internal/` gives `net.unlisted`, but listing it exactly gives allowlisted. With `*.dev.localhost`, `http://a.dev.localhost` gives `net.unlisted`. `[::ffff:127.0.0.1]` with `127.0.0.1` listed gives `net.unlisted`. A sanity assert: each AC3 address is `is_loopback or is_link_local or is_private or is_reserved`, or is the name `localhost`.
  - **AC4** (parametrized, `net.unparsed`): `https://allowed.com@evil.com/`, `http://@x.com`, `https://user:tok3n@evil.com` (and assert the detail is `"@"` with `tok3n` absent from the detail), `ftp://x`, `file:///etc/passwd`, `//nohost`, `not a url`, `https:evil.com`, `http:\\evil.com`, `http:///x`, `http://x:abc/`, `http://x:99999/`, `http://[::1`, `http://[evil.com]/`, `http://[fe80::1%25eth0]/`, `http://2852039166/`, `http://127.1/`, `http://0177.0.0.1/`, `http://0x7f.0.0.1/`, `http://1.2.3.4.5/`, `http://evil.com\.allowed.com/` (with `*.allowed.com` listed), `http://%31%32%37.0.0.1/`, `http://a..b/`, `http://ex_ample.com/`, the IDNA failure `http://` + `"a"*64` + `.com/`, `http://℀.com/`, `http://straße.de/` (deviation). IDNA ASCII form: `http://münchen.de/` is allowlisted by entry `xn--mnchen-3ya.de` and has detail `xn--mnchen-3ya.de`, `http://ｅｖｉｌ.com/` is unlisted with detail `evil.com`, and the Cyrillic `http://аpple.com/` with `apple.com` listed is unlisted.
  - **Shape/T11**: `operation == Operation("http", url, source_tool)`. The detail is at most 32 characters and is never an entry that does not appear in the URL. For example, with `*.githubusercontent.com` listed, the detail for `raw.githubusercontent.com` is the host, and for `evil.example` no entry text appears in the detail. Every rule returned is in `{"net.allowlisted", "net.unlisted", "net.unparsed"}`, which is a subset of `RULE_IDS`.
  - **Bad entries skipped**: `[None, 3, "", "*.", "*.com", "not a host!"]` plus `"example.com"` still allowlists `https://example.com` and allowlists nothing else.
  - **Never raises** (explicit ids, as in `test_action_paths.py:333-343`): `None`, `b"http://x"`, `123`, `"http://" + "a." * 100_000 + "com"`, `"\x00"`, `""`. The result is `net.unparsed`, with `Operation("http", "", t)` for non-`str` inputs. Internal error: monkeypatch `network.urlsplit` to raise `RuntimeError`, which gives `net.unparsed` with detail `""`.
  - **AC5 purity**: a source scan in the style of `test_action_paths.py:377-395`: `settings` is not in `vars(network)`; there is no `socket`, `getaddrinfo`, `gethostbyname`, `urllib.request`, `http.client`, `open(` or `os.`; the only `app` import is `from app.services.action_classifiers import Classification, Operation`. A fresh-process import (`test_action_paths.py:397-411`) shows that the `sys.modules` `app.*` set is exactly the package chain, and that `socket` is not in `sys.modules`. Verified: `socket` is not loaded by `urllib.parse`/`ipaddress`/`encodings.idna`/`app.services.action_classifiers`. A runtime no-DNS test: monkeypatch `socket.getaddrinfo`, `socket.gethostbyname` and `socket.create_connection` to raise `AssertionError`, then run every AC URL. They must classify unchanged.
  - **Loader round trip** (one test): write a policy file with `network: allow: [registry.npmjs.org, "*.githubusercontent.com", 127.0.0.1]`, load it the way `tests/test_action_config.py:989-1004` does (`get_policy()` after setting `ACTION_POLICY_FILE`), and check `classify_url(..., get_policy().network_allow)` against AC1/AC3. This proves the entries the loader keeps are the ones the classifier reads. If that fixture pattern is heavy, use `BUILT_IN_POLICY.network_allow == ()` together with AC2 instead, and note it.
- **Mirror**: `tests/test_action_paths.py` (structure, ids, purity), `tests/test_action_config.py:989-1004` (file load)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_network.py -q -p no:cacheprovider`

### Task 3: Targeted regression run

- No pre-existing module changes, so the targeted set is `tests/test_action_network.py tests/test_action_vocabulary.py tests/test_action_config.py tests/test_untouched_app.py`. `tests/test_untouched_app.py` exists and was in STORY-011's targeted set when `paths.py` was added (STORY-011 report, line 51). It does not name `paths` explicitly, so a new module should need no registration. If it fails, read it before changing anything.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest <those files> -q -p no:cacheprovider`, and record the exact counts. Full suite: deferred to orchestrator (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints `OK`
- [ ] A fresh-process import of `app.services.action_classifiers.network` loads no `app.config`/settings and no `socket`
- [ ] The AC tables pass with `socket` lookups monkeypatched to raise

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_network.py tests/test_action_vocabulary.py tests/test_action_config.py -q -p no:cacheprovider
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| `urlsplit` and browsers/curl disagree about the host (backslash, `@`, brackets, tabs) | Any `@` is unparsed. A strict RFC 1123 label check after IDNA makes every non-hostname character unparsed. Bracketed hosts must be IPv6 |
| IDNA 2003 (stdlib) and IDNA 2008/UTS46 map a host differently | Deviation characters are unparsed (decision 3.7). Everything else is compared in its ASCII form |
| Obfuscated IPv4 (decimal, octal, hex, short form) reaches a private address under a name rule | A numeric last label must be a canonical dotted quad, or it is unparsed (decision 3.9) |
| A wildcard matches a private address | IP literals never match wildcards (decision 4). Loopback names are excluded too. Names that *resolve* privately (`*.nip.io`, DNS rebinding) are out of scope (no DNS, PRD line 569). Documented for STORY-018/020 |
| Story/PRD signature `classify_url(url, policy)` is not followed | Same deviation as STORY-011 decision 1, for consistency with siblings. STORY-014 passes `policy.network_allow` |
| AC3's `*.internal` is refused by the loader | The test passes the tuple directly, which is the classifier's defensive skip, and also uses a two-label `*.corp.internal` |

## Open questions for the orchestrator

1. `_NEVER_BY_WILDCARD` adds `metadata.google.internal` and `*.localhost` beyond the PRD's literal list (Section 6.5 lists `localhost`, `127.0.0.0/8`, `::1`, link-local and `169.254.169.254`). They are cheap and only remove wildcard reach, never exact entries. Drop them if the orchestrator prefers the PRD's list verbatim.
2. `curl evil.com` (a scheme-less URL) is a STORY-013 concern. `classify_url` reads it as `net.unparsed`, so STORY-013 must decide whether to prefix `http://` for curl words or leave them unparsed.
3. `Operation.target` is the whole URL, query string included (sibling convention). Whether the audit should redact query strings is a STORY-015 question.

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given an allowlist of `registry.npmjs.org` and `*.githubusercontent.com`, when `classify_url` runs on `https://registry.npmjs.org/x` and `https://raw.githubusercontent.com/x`, then `net.allowlisted`; on `https://githubusercontent.com/x` (apex) and `https://evil.example`, then `net.unlisted`.
- [ ] Given an empty allowlist, when any parseable `http(s)` URL is classified, then `net.unlisted`.
- [ ] Given `http://169.254.169.254/latest`, `http://localhost:8000`, `http://127.0.0.1`, `http://[::1]`, `http://10.0.0.1` with `*.amazonaws.com` and `*.internal` allowlisted, when classified, then none matches a wildcard (`net.unlisted`); listing `127.0.0.1` exactly makes it `net.allowlisted`.
- [ ] Given `https://allowed.com@evil.com/`, `ftp://x`, `file:///etc/passwd`, `//nohost`, `not a url`, a decimal-IP host such as `http://2852039166/`, or an IDNA failure, when classified, then `net.unparsed`; an IDNA hostname is compared in its ASCII (punycode) form.
- [ ] Given the module, when imported, then it reads no settings and performs no DNS lookup or other I/O.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (pure, never raises, keyword-only `source_tool`, T11 detail)
