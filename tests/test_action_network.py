"""PRD-016 STORY-012: the network classifier (Sections 6.3 network rows, 6.5, F5; D5; T5; T8; T11).

Table-driven. The URLs and the expected rules are transcribed from the
story's acceptance criteria, Section 6.5 and T8, and written out as literals,
not derived from the module. They are seeds for STORY-018's URL-trick
evasion group; the T8 rows name the trick each one closes.

`classify_url` takes `network_allow` as a plain argument (STORY-012 plan,
decision 1). Some tables pass tuples the loader would refuse (`*.internal`,
`*.com`): the classifier must stay safe for a tuple nobody validated.

Not covered here: `curl`/`wget` URL words inside a shell command
(STORY-013) and how `evaluate()` folds the result (STORY-014).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import inspect
import ipaddress
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import app.services.action_classifiers.network as network
from app.config import settings
from app.services.action_classifiers import NON_GRANTABLE_RULES, RULE_IDS, Classification, Operation
from app.services.action_classifiers.network import classify_url
from app.services.action_config import BUILT_IN_POLICY, get_policy, load

_REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOW = ("registry.npmjs.org", "*.githubusercontent.com")
_NET_RULES = {"net.allowlisted", "net.unlisted", "net.unparsed"}


# --- AC1: exact and wildcard entries ------------------------------------------------


@pytest.mark.parametrize(
    "url, rule",
    [
        ("https://registry.npmjs.org/x", "net.allowlisted"),
        ("https://raw.githubusercontent.com/x", "net.allowlisted"),
        ("https://githubusercontent.com/x", "net.unlisted"),  # the apex is not under `*.`
        ("https://evil.example", "net.unlisted"),
        ("https://a.b.githubusercontent.com/x", "net.allowlisted"),  # any depth
        ("https://evilgithubusercontent.com/", "net.unlisted"),  # a label boundary, not a string suffix
        ("https://registry.npmjs.org.evil.example/", "net.unlisted"),
        ("https://registry.npmjs.org:8443/x", "net.allowlisted"),  # the port is ignored
    ],
)
def test_ac1_allowlist(url, rule):
    assert classify_url(url, ALLOW).rule == rule


def test_ac1_case_and_trailing_dot_are_the_same_host():
    result = classify_url("HTTPS://Registry.NPMJS.org./x", ("Registry.npmjs.org",))
    assert result.rule == "net.allowlisted"
    assert result.detail == "registry.npmjs.org"


# --- AC2: an empty allowlist -------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["https://example.com", "http://8.8.8.8/", "http://[2001:db8::1]/", "http://localhost"]
)
def test_ac2_empty_allowlist_lists_nothing(url):
    assert classify_url(url).rule == "net.unlisted"
    assert classify_url(url, ()).rule == "net.unlisted"
    assert classify_url(url, BUILT_IN_POLICY.network_allow).rule == "net.unlisted"


def test_ac2_built_in_allowlist_is_empty():
    assert BUILT_IN_POLICY.network_allow == ()


# --- AC3: reserved addresses never match a wildcard (T8) ---------------------------

_AC3_URLS = [
    "http://169.254.169.254/latest",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://[::1]",
    "http://10.0.0.1",
]


@pytest.mark.parametrize(
    "allow",
    [
        # The story's literal list. The loader refuses `*.internal` (a one-label
        # wildcard, STORY-007 decision); passed directly it is skipped.
        ("*.amazonaws.com", "*.internal"),
        ("*.amazonaws.com", "*.corp.internal", "*.localhost.example"),
    ],
)
@pytest.mark.parametrize("url", _AC3_URLS)
def test_ac3_reserved_addresses_never_match_a_wildcard(url, allow):
    assert classify_url(url, allow).rule == "net.unlisted"


@pytest.mark.parametrize(
    "url, entry",
    [
        ("http://127.0.0.1", "127.0.0.1"),
        ("http://[::1]", "::1"),
        ("http://[::1]", "0:0::1"),  # `ipaddress` equality, not text
        ("http://[0:0::1]/", "::1"),
        ("http://169.254.169.254/latest", "169.254.169.254"),
        ("http://localhost:8000", "localhost"),
    ],
)
def test_ac3_an_exact_entry_allowlists_a_reserved_address(url, entry):
    assert classify_url(url, ("*.amazonaws.com", entry)).rule == "net.allowlisted"


def test_ac3_metadata_name_only_by_exact_entry():
    url = "http://metadata.google.internal/computeMetadata/v1/"
    assert classify_url(url, ("*.google.internal",)).rule == "net.unlisted"
    assert classify_url(url, ("metadata.google.internal",)).rule == "net.allowlisted"


def test_ac3_localhost_subdomains_never_by_wildcard():
    assert classify_url("http://a.dev.localhost/", ("*.dev.localhost",)).rule == "net.unlisted"
    assert classify_url("http://a.dev.localhost/", ("a.dev.localhost",)).rule == "net.allowlisted"


def test_ac3_ipv4_mapped_ipv6_is_not_the_ipv4_entry():
    # Fails closed: a different literal, so the grantable unlisted, never allowlisted.
    assert classify_url("http://[::ffff:127.0.0.1]/", ("127.0.0.1",)).rule == "net.unlisted"


def test_ac3_an_ip_literal_never_matches_any_wildcard():
    # Even a public address: wildcards match names only. Entries the loader
    # refuses (a numeric suffix) are skipped.
    assert classify_url("http://8.8.8.8/", ("*.8.8.8", "*.8.8", "*.com")).rule == "net.unlisted"


def test_ac3_addresses_are_in_the_reserved_ranges():
    """Sanity: the AC3 hosts are the ranges Section 6.5 names (loopback, link-local, private, reserved)."""
    for text in ("169.254.169.254", "127.0.0.1", "::1", "10.0.0.1"):
        address = ipaddress.ip_address(text)
        assert address.is_loopback or address.is_link_local or address.is_private or address.is_reserved


# --- AC4: unparseable URLs and IDNA (T8) -------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://allowed.com@evil.com/",  # T8: userinfo, the real host is evil.com
        "http://@x.com",
        "ftp://x",
        "file:///etc/passwd",
        "//nohost",
        "not a url",
        "https:evil.com",
        "http:\\\\evil.com",
        "http:///x",
        "http://x:abc/",
        "http://x:99999/",
        "http://[::1",
        "http://[evil.com]/",
        "http://[1.2.3.4]/",
        "http://[fe80::1%25eth0]/",  # a zone id
        "http://2852039166/",  # T8: decimal IP
        "http://127.1/",  # short form
        "http://0177.0.0.1/",  # octal
        "http://0x7f.0.0.1/",  # hex
        "http://1.2.3.0x4/",
        "http://1.2.3.4.5/",
        "http://evil.com\\.allowed.com/",  # a browser reads `\` as `/`: host evil.com
        "http://%31%32%37.0.0.1/",  # percent-encoding
        "http://a..b/",
        "http://ex_ample.com/",
        "http://" + "a" * 64 + ".com/",  # IDNA failure: a label over 63
        "http://℀.com/",  # `℀` NFKC-expands to `a/c`
        "http://straße.de/",  # an IDNA 2003/2008 deviation character
        "http://x‍.com/",  # ZWJ, a deviation character
    ],
)
def test_ac4_unparsed(url):
    assert classify_url(url, ALLOW + ("*.allowed.com", "allowed.com", "x.com")).rule == "net.unparsed"


def test_ac4_userinfo_is_never_echoed():
    """T11: the userinfo can be a credential."""
    result = classify_url("https://user:tok3n@evil.com/", ALLOW)
    assert result.rule == "net.unparsed"
    assert result.detail == "@"
    assert "tok3n" not in result.detail


@pytest.mark.parametrize(
    "url, allow, rule, detail",
    [
        ("http://münchen.de/", ("xn--mnchen-3ya.de",), "net.allowlisted", "xn--mnchen-3ya.de"),
        ("http://MÜNCHEN.de/", ("xn--mnchen-3ya.de",), "net.allowlisted", "xn--mnchen-3ya.de"),
        ("http://ｅｖｉｌ.com/", (), "net.unlisted", "evil.com"),  # fullwidth
        ("http://evil。com/", ("evil.com",), "net.allowlisted", "evil.com"),  # ideographic full stop
        ("http://аpple.com/", ("apple.com",), "net.unlisted", "xn--pple-43d.com"),  # Cyrillic а
    ],
)
def test_ac4_idna_is_compared_in_ascii_form(url, allow, rule, detail):
    result = classify_url(url, allow)
    assert (result.rule, result.detail) == (rule, detail)


@pytest.mark.parametrize(
    "url, rule",
    [
        ("http://a/b@c", "net.unlisted"),  # the `@` is in the path
        ("http://allowed.com#@evil.com", "net.allowlisted"),  # the `@` is in the fragment
        ("http://ev\til.com/", "net.unlisted"),  # urlsplit drops tab, as WHATWG does: evil.com
    ],
)
def test_authority_ends_at_the_first_path_query_or_fragment(url, rule):
    assert classify_url(url, ("allowed.com",)).rule == rule


# --- shape and T11 -----------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://raw.githubusercontent.com/x",
        "https://evil.example",
        "https://allowed.com@evil.com/",
        "http://" + "a" * 60 + ".githubusercontent.com/",
    ],
)
def test_operation_and_detail_shape(url):
    result = classify_url(url, ALLOW, source_tool="web_fetch")
    assert result.operation == Operation("http", url, "web_fetch")
    assert result.rule in _NET_RULES
    assert isinstance(result.detail, str) and len(result.detail) <= 32


def test_detail_keeps_the_end_of_a_long_host():
    host = "a" * 60 + ".githubusercontent.com"
    result = classify_url("https://" + host + "/x", ALLOW)
    assert result.rule == "net.allowlisted"
    assert result.detail == host[-32:]


def test_detail_never_comes_from_an_entry():
    """T11: the detail is the call's host, never the entry that matched."""
    assert classify_url("https://raw.githubusercontent.com/x", ALLOW).detail == "raw.githubusercontent.com"
    detail = classify_url("https://evil.example", ALLOW).detail
    assert detail == "evil.example"
    for entry in ALLOW:
        assert entry.lstrip("*.") not in detail


def test_detail_of_a_bad_scheme_is_the_scheme():
    assert classify_url("ftp://x").detail == "ftp"


def test_net_rules_are_in_the_vocabulary():
    assert _NET_RULES <= set(RULE_IDS)
    assert "net.unparsed" in NON_GRANTABLE_RULES


# --- bad entries --------------------------------------------------------------------


def test_bad_entries_are_skipped():
    allow = [None, 3, "", "*.", "*.com", "not a host!", "example.com"]
    assert classify_url("https://example.com", allow).rule == "net.allowlisted"
    for url in ("https://a.com", "https://x.example.com", "https://com", "https://not"):
        assert classify_url(url, allow).rule == "net.unlisted", url


@pytest.mark.parametrize("allow", [None, (), [None]])
def test_empty_or_none_allowlist(allow):
    assert classify_url("https://example.com", allow).rule == "net.unlisted"


# --- never raises -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, b"http://x", 123, "http://" + "a." * 100_000 + "com", "\x00", ""],
    # Explicit ids: pytest puts the test id in an environment variable, and
    # Windows refuses one over 32767 characters.
    ids=["none", "bytes", "int", "long", "nul", "empty"],
)
def test_never_raises(value):
    result = classify_url(value, ALLOW, source_tool="t")
    assert result.rule == "net.unparsed"
    if not isinstance(value, str):
        assert result == Classification("net.unparsed", Operation("http", "", "t"), "")


def test_internal_error_fails_closed(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("bug")

    monkeypatch.setattr(network, "urlsplit", _boom)
    assert classify_url("https://registry.npmjs.org/x", ALLOW) == Classification(
        "net.unparsed", Operation("http", "https://registry.npmjs.org/x", ""), ""
    )


# --- AC5: purity and no DNS ----------------------------------------------------------


def test_network_module_stays_pure():
    """PRD-016 Section 6.12: no settings, no I/O, no DNS, no `app` import but the vocabulary."""
    source = inspect.getsource(network)

    assert "settings" not in vars(network)
    for forbidden in ("socket", "getaddrinfo", "gethostbyname", "urllib.request", "http.client", "open(", "os."):
        assert forbidden not in source, forbidden
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    app_imports = [line for line in imports if " app." in line or line.startswith("from app")]
    assert app_imports == ["from app.services.action_classifiers import Classification, Operation"]


def test_importing_network_loads_no_settings_and_no_socket():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.services.action_classifiers.network; "
            "print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.'))); "
            "print('socket' in sys.modules)",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    modules, has_socket = completed.stdout.strip().splitlines()
    assert modules == str(
        ["app", "app.services", "app.services.action_classifiers", "app.services.action_classifiers.network"]
    )
    assert has_socket == "False"


def test_no_dns_lookup_at_classification(monkeypatch):
    def _no_dns(*_a, **_k):
        raise AssertionError("classify_url must not touch the network")

    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        monkeypatch.setattr(socket, name, _no_dns)
    expected = {
        "https://registry.npmjs.org/x": "net.allowlisted",
        "https://raw.githubusercontent.com/x": "net.allowlisted",
        "https://githubusercontent.com/x": "net.unlisted",
        "https://evil.example": "net.unlisted",
        "http://169.254.169.254/latest": "net.unlisted",
        "http://localhost:8000": "net.unlisted",
        "https://allowed.com@evil.com/": "net.unparsed",
        "http://2852039166/": "net.unparsed",
        "http://münchen.de/": "net.unlisted",
    }
    for url, rule in expected.items():
        assert classify_url(url, ALLOW).rule == rule, url


# --- the loader's entries are the classifier's entries -------------------------------


def test_entries_from_a_policy_file(tmp_path, monkeypatch):
    path = tmp_path / "action_policy.yaml"
    path.write_text(
        'network:\n  allow: [registry.npmjs.org, "*.githubusercontent.com", 127.0.0.1]\n', encoding="utf-8"
    )
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(path))
    load()
    allow = get_policy().network_allow
    assert classify_url("https://registry.npmjs.org/x", allow).rule == "net.allowlisted"
    assert classify_url("https://raw.githubusercontent.com/x", allow).rule == "net.allowlisted"
    assert classify_url("https://githubusercontent.com/x", allow).rule == "net.unlisted"
    assert classify_url("http://127.0.0.1", allow).rule == "net.allowlisted"
    assert classify_url("http://[::1]", allow).rule == "net.unlisted"
