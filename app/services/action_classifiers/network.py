"""The network classifier: URL parse, IDNA, host allowlist, reserved addresses (PRD-016 Sections 6.3, 6.5, F5).

`classify_url(url, network_allow)` returns exactly one of `net.allowlisted`,
`net.unlisted` or `net.unparsed` (Section 6.3's network rows). It takes the
policy's `network.allow` entries as a plain argument, the way
`classify_shell` takes `shell_allow` and `classify_write` takes
`workspace_roots` (STORY-012 plan, decision 1; F5 writes `classify_url(url,
policy)`). STORY-014 calls `classify_url(op.target, policy.network_allow,
source_tool=op.source_tool)` and wraps the result in a tuple; STORY-013
calls it for each URL word of `curl`/`wget`.

Parsing (`_host`), first failure wins, every failure `net.unparsed` (the
non-grantable D5 outcome, so a host nobody can read is never grantable):

1. Not a `str`.
2. `urllib.parse.urlsplit` raises (`[::1` unclosed, a bracketed non-IP such
   as `[evil.com]`, a netloc that NFKC turns into `/?#@:`, `℀.com`).
   urlsplit strips leading C0/space and drops tab/CR/LF anywhere, as WHATWG
   does; the adapters already refuse line breaks in `http` targets.
3. The scheme is not `http`/`https` (`ftp://x`, `file:///etc/passwd`, the
   empty scheme of `//nohost` and `not a url`).
4. Any `@` in the authority (T8: `https://allowed.com@evil.com/` goes to
   `evil.com`). The detail is `"@"`, never the userinfo, which can be a
   credential (`user:token@host`, T11). An `@` after the first `/?#` is not
   in the authority, as browsers agree.
5. No host (`https:evil.com`, `http:\\\\evil.com`, `http:///x`) or a port
   that is not a number in range. The port is otherwise ignored: the
   allowlist is per host.
6. A bracketed host must be an IPv6 literal without a zone id (`%`).
7. A name host loses one trailing `.` (the same DNS name), then is
   IDNA-encoded with the stdlib codec (`encodings.idna`, IDNA 2003) and
   compared in ASCII (punycode) form: `münchen.de` is `xn--mnchen-3ya.de`,
   fullwidth `ｅｖｉｌ.com` and `evil。com` are `evil.com`, and a Cyrillic
   lookalike `аpple.com` is `xn--pple-43d.com`, which cannot match
   `apple.com`. A codec failure is `net.unparsed`. So is a non-ASCII host
   holding an IDNA 2003/2008 *deviation* character (`ß`, `ς`, ZWNJ, ZWJ):
   the codec maps `straße.de` to `strasse.de`, while an IDNA 2008 / UTS 46
   client reaches `xn--strae-oqa.de`, a different host, so either
   comparison could allow a host the client never reaches.
8. The ASCII host is over 253 characters or a label is not RFC 1123. This
   refuses `evil.com\\.allowed.com` (urlsplit keeps the `\\` in the host; a
   browser reads it as a path separator to `evil.com`), percent-encoding,
   `_`, an empty label and other junk, rather than calling them a
   grantable `net.unlisted`.
9. A host whose last label is numeric (digits, or `0x` hex) is an IPv4
   attempt, as WHATWG parses it, and must be a canonical dotted quad;
   anything else is an obfuscated IP: `2852039166`, `127.1`, `0177.0.0.1`,
   `0x7f.0.0.1`, `1.2.3.4.5` (stricter than the story's "all digits or
   fewer than four parts", and the loader's "last label not all digits",
   `action_config._is_hostname`).

Matching (Section 6.5, T8):

- An IP literal matches only an IP entry, by `ipaddress` equality
  (`[0:0::1]` is entry `::1`), and **never a wildcard**, public or not --
  stricter than excluding the loopback, link-local, private and reserved
  ranges. The loader already refuses a wildcard over a numeric label; this
  holds anyway for a tuple nobody validated. An IPv4-mapped
  `[::ffff:127.0.0.1]` is not entry `127.0.0.1`: it is `net.unlisted`.
- A name matches an exact entry, or a `*.` entry whose suffix has at least
  two labels (`*.com` and `*.internal` are skipped here as the loader
  refuses them, STORY-007), at any depth below the suffix and never the
  apex: `*.githubusercontent.com` matches `a.b.githubusercontent.com`, not
  `githubusercontent.com` or `evilgithubusercontent.com`. `localhost`,
  any `*.localhost` (RFC 6761 loopback names) and `metadata.google.internal`
  are never matched by a wildcard, only by an exact entry (orchestrator
  decision, STORY-012 plan, open question 1).
- Entries are compared lowercased; an entry that is not a `str` or matches
  none of the three shapes is skipped.

Every classification's `operation` is `Operation("http", url, source_tool)`
with the **whole input** as the target. The `detail` comes from the call,
never from an entry (T11), at most 32 characters keeping the **end** (the
registrable domain names the host): the canonical ASCII host or IP for
`net.allowlisted`/`net.unlisted`; for `net.unparsed` the scheme for a bad
scheme, `"@"` for userinfo, the raw host for a bad host, and `""` when
there is no host or no `str`.

Never raises: any `Exception` is `net.unparsed` with detail `""`, the
strictest outcome and non-grantable (T5). `BaseException` is not caught.

Pure (PRD-016 Section 6.12): no settings, no I/O and **no DNS** (PRD Section
3 and Out of scope). The residual risk, for STORY-018 and STORY-020: a
wildcard over a domain whose names *resolve* to a private address
(`*.nip.io` matching `127.0.0.1.nip.io`, or DNS rebinding under an
allowlisted wildcard) is matched by name. Only an operator's entry opens
such a domain.
"""

import ipaddress
import re
from typing import Union
from urllib.parse import urlsplit

from app.services.action_classifiers import Classification, Operation

_DETAIL_MAX = 32
_SCHEMES = frozenset({"http", "https"})
#: One RFC 1123 label, the same as `action_config._HOST_LABEL`, applied after
#: lowercasing. Duplicated: a pure module cannot import `action_config`.
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
#: A last label WHATWG would read as an IPv4 part (decimal, octal or hex).
_NUMERIC_LABEL = re.compile(r"[0-9]+|0x[0-9a-f]*")
#: IDNA 2003 / 2008 deviation characters: `ß`, `ς`, ZWNJ, ZWJ (step 7).
_IDNA_DEVIATIONS = frozenset("ßς‌‍")
#: Names a wildcard never matches (besides any `*.localhost`), only an exact entry.
_NEVER_BY_WILDCARD = frozenset({"localhost", "metadata.google.internal"})

_IP = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _cap_tail(text: str) -> str:
    return text[-_DETAIL_MAX:]


def _is_name(host: str) -> bool:
    """A lowercased ASCII RFC 1123 hostname whose last label is not numeric."""
    if not host or len(host) > 253:
        return False
    labels = host.split(".")
    return all(_LABEL.fullmatch(label) for label in labels) and not _NUMERIC_LABEL.fullmatch(labels[-1])


def _host(url: str) -> tuple[Union[str, _IP, None], str]:
    """`(host, "")` for a name or an IP literal, else `(None, detail)` (module docstring, steps 2-9)."""
    # Step 2: urlsplit itself refuses the malformed brackets and NFKC tricks.
    try:
        parts = urlsplit(url)
    except ValueError:
        return None, ""
    # Step 3: the scheme, which urlsplit lowercases.
    if parts.scheme not in _SCHEMES:
        return None, _cap_tail(parts.scheme)
    # Step 4: userinfo, never echoed (T11).
    if "@" in parts.netloc:
        return None, "@"
    # Step 5: a host, and a port that parses.
    raw = parts.hostname
    if not raw:
        return None, ""
    try:
        parts.port
    except ValueError:
        return None, _cap_tail(raw)
    # Step 6: a bracketed host is IPv6, zone-free.
    if parts.netloc.startswith("["):
        if "%" in raw:
            return None, _cap_tail(raw)
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            return None, _cap_tail(raw)
        if not isinstance(address, ipaddress.IPv6Address):
            return None, _cap_tail(raw)
        return address, ""
    # Step 7: one trailing dot, deviation characters, IDNA to ASCII.
    name = raw[:-1] if raw.endswith(".") else raw
    if not name.isascii() and _IDNA_DEVIATIONS.intersection(name):
        return None, _cap_tail(raw)
    try:
        host = name.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None, _cap_tail(raw)
    # Step 9 first on the labels' shape: a numeric last label is an IPv4 attempt.
    labels = host.split(".")
    if labels and _NUMERIC_LABEL.fullmatch(labels[-1]):
        try:
            return ipaddress.IPv4Address(host), ""
        except ValueError:
            return None, _cap_tail(raw)
    # Step 8: RFC 1123 after IDNA.
    if not _is_name(host):
        return None, _cap_tail(raw)
    return host, ""


def _entries(network_allow) -> tuple[tuple[_IP, ...], frozenset, tuple[str, ...]]:
    """The entries as `(ips, exact names, wildcard suffixes)`, lowercased; malformed ones skipped."""
    ips: list = []
    exact: set = set()
    suffixes: list = []
    for entry in network_allow or ():
        if not isinstance(entry, str):
            continue
        entry = entry.lower()
        try:
            ips.append(ipaddress.ip_address(entry))
            continue
        except ValueError:
            pass
        if entry.startswith("*."):
            suffix = entry[2:]
            # At least two labels (STORY-007's refusal, re-checked for an unvalidated tuple).
            if _is_name(suffix) and "." in suffix:
                suffixes.append(suffix)
        elif _is_name(entry):
            exact.add(entry)
    return tuple(ips), frozenset(exact), tuple(suffixes)


def _allowlisted(host: Union[str, _IP], network_allow) -> bool:
    ips, exact, suffixes = _entries(network_allow)
    if not isinstance(host, str):
        # An IP literal: equality with an IP entry, never a wildcard.
        return any(host == ip for ip in ips)
    if host in exact:
        return True
    if host in _NEVER_BY_WILDCARD or host.endswith(".localhost"):
        return False
    return any(host.endswith("." + suffix) for suffix in suffixes)


def classify_url(url: str, network_allow=(), *, source_tool: str = "") -> Classification:
    """Classify a request to `url` (PRD-016 F5, Section 6.5). Never raises.

    `net.allowlisted`: the host is an exact entry, or under a `*.` entry (a
    name, never an IP literal or a loopback/metadata name). `net.unlisted`:
    a URL that parses but matches nothing (grantable, `action:net:egress`).
    `net.unparsed`: anything that cannot be read as one `http(s)` host
    (non-grantable, D5). `network_allow` is `policy.network_allow`; the
    default `()` is the built-in value, with which nothing is allowlisted.
    STORY-014 calls `classify_url(op.target, policy.network_allow,
    source_tool=op.source_tool)`; STORY-013 the same for each `curl`/`wget`
    URL word. A non-`str` URL or any exception is `net.unparsed` with
    detail `""`.
    """
    op = Operation(kind="http", target=url if isinstance(url, str) else "", source_tool=source_tool)
    try:
        if not isinstance(url, str):
            return Classification("net.unparsed", op, "")
        host, detail = _host(url)
        if host is None:
            return Classification("net.unparsed", op, detail)
        shown = _cap_tail(str(host))
        if _allowlisted(host, network_allow):
            return Classification("net.allowlisted", op, shown)
        return Classification("net.unlisted", op, shown)
    except Exception:
        return Classification("net.unparsed", op, "")

