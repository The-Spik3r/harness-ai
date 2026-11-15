"""PRD-016 STORY-011: the path classifier (Sections 6.3 filesystem rows, 6.5, F4; D11; T6; Risk 4).

Table-driven. The paths and the expected rules are transcribed from the
story's acceptance criteria, Section 6.5 and T6, and written out as literals,
not derived from the module. They are seeds for STORY-018's path-trick
evasion group; the T6 rows name the trick each one closes.

Real globs: `BUILT_IN_POLICY.protected_paths.compiled` (importing
`action_config` here is fine; only the module under test must stay pure).

Secret reads (STORY-013 filled the hook, F4) are checked here at the path
level; `tests/test_action_secrets.py` covers them end to end, and
`tests/test_action_shell.py` the shell output redirects (STORY-013). Not
covered here: how `evaluate()` folds the result (STORY-014).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import builtins
import inspect
import pathlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

import app.services.action_classifiers.paths as paths
from app.services.action_classifiers import RULE_IDS, Classification, Operation
from app.services.action_classifiers.paths import NormalizedPath, classify_read, classify_write, normalize_path
from app.services.action_config import BUILT_IN_POLICY

_REPO_ROOT = Path(__file__).resolve().parents[1]

P = BUILT_IN_POLICY.protected_paths.compiled
SECRET_FILES = BUILT_IN_POLICY.secrets.files.compiled
ROOTS = ("/home/dev/projects",)
WIN_ROOTS = ("C:\\Repo",)
BS = "\\"

_WRITE_RULES = {"fs.write_in_workspace", "fs.write_outside_workspace", "fs.write_protected"}


def _w(path, roots=()):
    return classify_write(path, P, roots).rule


# --- AC1: normalize_path ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw, text",
    [
        # The AC's four.
        ("src" + BS + "a.ts", "src/a.ts"),
        ("C:" + BS + "Repo" + BS + "x", "c:/Repo/x"),
        ("a//b/./c", "a/b/c"),
        ("a/b/../c", "a/c"),
        # Plan decision 3.
        ("./", "."),
        ("", "."),
        ("/../etc", "/etc"),
        ("../../etc/passwd", "../../etc/passwd"),
        ("a/../../b", "../b"),
        (BS + BS + "srv" + BS + "share" + BS + "x", "//srv/share/x"),
        ("///x", "/x"),
        ("C:x", "c:x"),
        ("c:/a/../../b", "c:/b"),
        (".git/config/", ".git/config"),
        ("~/../x", "~/x"),
    ],
)
def test_normalize_path(raw, text):
    assert normalize_path(raw).text == text
    assert str(normalize_path(raw)) == text


@pytest.mark.parametrize(
    "raw, anchor, parts",
    [
        ("src/a.ts", "", ("src", "a.ts")),
        ("/etc/hosts", "/", ("etc", "hosts")),
        ("//srv/share/x", "//", ("srv", "share", "x")),
        ("C:/Repo/x", "c:/", ("Repo", "x")),
        ("C:x", "c:", ("x",)),
        (BS + BS + "?" + BS + "C:" + BS + "x", "//", ("?", "C:", "x")),
    ],
)
def test_anchor_and_parts(raw, anchor, parts):
    assert normalize_path(raw) == NormalizedPath(anchor, parts)


def test_tilde_stays_a_literal_segment():
    p = normalize_path("~/x")
    assert p.parts[0] == "~"
    assert p.home and not p.is_absolute and not p.escapes
    assert normalize_path("~user/x").home
    assert not normalize_path("src/~/x").home


@pytest.mark.parametrize(
    "raw, absolute, escapes",
    [
        ("../x", False, True),
        ("a/../../b", False, True),
        ("a/../b", False, False),
        ("/../x", True, False),
        ("C:/../x", True, False),
        ("C:../x", False, True),
        ("//srv/s", True, False),
    ],
)
def test_absolute_and_escape_flags(raw, absolute, escapes):
    p = normalize_path(raw)
    assert p.is_absolute is absolute
    assert p.escapes is escapes


_ALL_PATHS = [
    "src/a.ts",
    "C:\\Repo\\x",
    "a//b/./c",
    "a/b/../c",
    "~/x",
    "../../etc/passwd",
    "/etc/hosts",
    "/home/dev/projects/app/x.ts",
    "/home/dev/projects2/x",
    ".env",
    "./.env",
    "config/../.env",
    ".ENV.local",
    "/home/dev/projects/app/.env.local",
    ".github/workflows/ci.yml",
    ".git/config",
    "id_rsa",
    "x.pem",
    "x.pem.",
    "x.pem::$DATA",
    ".git",
    "\\\\?\\C:\\Repo\\a",
    "C:x",
    ".",
]


def test_normalize_and_classify_touch_no_filesystem(monkeypatch):
    """AC1/AC5: no call opens, stats or resolves anything."""

    def _forbidden(*_a, **_k):
        raise AssertionError("the path classifier touched the filesystem")

    for target, name in [
        (builtins, "open"),
        (os, "stat"),
        (os, "lstat"),
        (os, "readlink"),
        (os, "listdir"),
        (os.path, "realpath"),
        (os.path, "exists"),
        (pathlib.Path, "resolve"),
        (pathlib.Path, "exists"),
    ]:
        monkeypatch.setattr(target, name, _forbidden)
    for raw in _ALL_PATHS:
        normalize_path(raw)
        classify_write(raw, P, ROOTS + WIN_ROOTS)
        classify_read(raw, SECRET_FILES)


# --- AC2: containment ------------------------------------------------------------


@pytest.mark.parametrize(
    "path, roots, rule",
    [
        # The AC.
        ("src/a.ts", (), "fs.write_in_workspace"),
        ("../../etc/passwd", (), "fs.write_outside_workspace"),
        ("/etc/hosts", (), "fs.write_outside_workspace"),
        ("/home/dev/projects/app/x.ts", ROOTS, "fs.write_in_workspace"),
        ("/home/dev/projects2/x", ROOTS, "fs.write_outside_workspace"),
        # Plan decision 5.
        ("/home/dev/projects", ROOTS, "fs.write_in_workspace"),
        ("/home/dev/projects/../other/x", ROOTS, "fs.write_outside_workspace"),
        ("src/a.ts", ROOTS, "fs.write_in_workspace"),
        (".", (), "fs.write_in_workspace"),
        ("~/x", ROOTS, "fs.write_outside_workspace"),
        ("~/../x", (), "fs.write_outside_workspace"),
        ("C:x", WIN_ROOTS, "fs.write_outside_workspace"),
        ("c:/Repo/src/a.ts", WIN_ROOTS, "fs.write_in_workspace"),
        ("C:\\Repo\\src\\a.ts", WIN_ROOTS, "fs.write_in_workspace"),
        ("C:/RepoX/a", WIN_ROOTS, "fs.write_outside_workspace"),
        # Case-exact except the drive letter: fails closed (decision 5).
        ("c:/repo/a", ("C:/Repo",), "fs.write_outside_workspace"),
        ("/HOME/dev/projects/x", ROOTS, "fs.write_outside_workspace"),
        ("//srv/share/x", ("/srv/share",), "fs.write_outside_workspace"),
        ("//srv/share/x", ("//srv/share",), "fs.write_in_workspace"),
        ("\\\\?\\C:\\Repo\\a", ("C:/Repo",), "fs.write_outside_workspace"),
        # A root of `/` is the operator's choice.
        ("/etc/hosts", ("/",), "fs.write_in_workspace"),
        # PRD-016 STORY-018: a segment of only dots and spaces is outside (Win32 reads it as another name).
        ("a/.../b", (), "fs.write_outside_workspace"),
        (".../x", (), "fs.write_outside_workspace"),
        (". ./x", (), "fs.write_outside_workspace"),
        (".. /x", (), "fs.write_outside_workspace"),
        ("/home/dev/projects/.../x", ROOTS, "fs.write_outside_workspace"),
        ("/home/dev/projects/. ./x", ROOTS, "fs.write_outside_workspace"),
        # ...and the near misses stay inside.
        ("src/a.b", (), "fs.write_in_workspace"),
        ("a.b/c", (), "fs.write_in_workspace"),
        ("...x/y", (), "fs.write_in_workspace"),
        ("x../y", (), "fs.write_in_workspace"),
        ("./a", (), "fs.write_in_workspace"),
        # Protection still wins over containment.
        (".../.env", (), "fs.write_protected"),
    ],
)
def test_containment(path, roots, rule):
    assert _w(path, roots) == rule


@pytest.mark.parametrize("roots", [(None, "rel", 3, "/home/dev/projects"), None, ("~/x", "C:x")])
def test_bad_root_entries_are_skipped(roots):
    assert _w("src/a.ts", roots) == "fs.write_in_workspace"
    expected = "fs.write_in_workspace" if roots and "/home/dev/projects" in roots else "fs.write_outside_workspace"
    assert _w("/home/dev/projects/x", roots) == expected


# --- AC3: protection before containment (T6) -------------------------------------

_AC3 = [
    ".env",
    "./.env",
    "config/../.env",
    ".ENV.local",
    "/home/dev/projects/app/.env.local",
    ".github/workflows/ci.yml",
    ".git/config",
    "id_rsa",
    "x.pem",
]

_T6 = [
    "src" + BS + ".." + BS + ".ENV",  # mixed separators, `..` and case
    "C:" + BS + "Repo" + BS + ".git" + BS + "config",  # Windows absolute
    ".GitHub/Workflows/CI.yml",  # case
    "a/.ssh/id_ed25519",  # any depth
    "x.pem.",  # Win32 trailing dot (fold)
    "x.pem::$DATA",  # NTFS stream (fold)
    ".git./config",  # trailing dot on a directory (fold)
    ".git",  # the directory itself (probe)
    ".github/workflows",  # the directory itself (probe)
    "../.env",  # escaping, still protected first
    "~/.ssh/config",  # home, still protected first
    ".circleci/config.yml",
    "Jenkinsfile",
    ".gitlab-ci.yml",
    "deploy/server.key",
    "\\\\?\\C:\\Repo\\.env",  # the `\\?\` prefix
    "src/id_utils.py",  # `id_*` over-matches, as the PRD writes it (STORY-006 decision 6)
]


@pytest.mark.parametrize("roots", [(), ROOTS], ids=["no-roots", "roots"])
@pytest.mark.parametrize("path", _AC3 + _T6)
def test_protected_paths(path, roots):
    assert _w(path, roots) == "fs.write_protected"


@pytest.mark.parametrize("path", ["src/env.ts", ".gitignore", "x.pem.txt", "docs/github/workflows.md", ".github/README.md"])
def test_near_misses_are_not_protected(path):
    assert _w(path) == "fs.write_in_workspace"


def test_protection_is_checked_before_containment():
    assert _w("/home/dev/projects/app/.env.local", ROOTS) == "fs.write_protected"
    assert _w("/home/dev/projects/app/x.ts", ROOTS) == "fs.write_in_workspace"


# --- detail and operation (T11) --------------------------------------------------


def test_protected_detail_is_the_matched_tail():
    assert classify_write("/home/dev/projects/app/.env.local", P, ROOTS).detail == ".env.local"
    assert classify_write("a/.git", P).detail == ".git"
    assert classify_write("x.pem::$DATA", P).detail == "x.pem"


@pytest.mark.parametrize("path", ["/home/dev/projects2/x", "/etc/hosts", "/home/dev/projects/app/x.ts"])
def test_detail_is_never_a_root(path):
    result = classify_write(path, P, ROOTS)
    assert result.detail == normalize_path(path).text
    assert result.detail != ROOTS[0]


def test_detail_is_capped_keeping_the_tail():
    path = "d/" * 50 + "x.ts"
    detail = classify_write(path, P).detail
    assert len(detail) == 32
    assert detail.endswith("x.ts")


def test_write_operation_carries_the_input_as_given():
    raw = "C:" + BS + "Repo" + BS + "a.ts"
    result = classify_write(raw, P, WIN_ROOTS, source_tool="write")
    assert result == Classification("fs.write_in_workspace", Operation("fs_write", raw, "write"), "c:/Repo/a.ts")


# --- AC4: reads and the STORY-013 secret hook ------------------------------------


def test_read_is_fs_read():
    assert classify_read("src/a.ts", SECRET_FILES, source_tool="read") == Classification(
        "fs.read", Operation("fs_read", "src/a.ts", "read"), "src/a.ts"
    )
    assert classify_read(".").rule == "fs.read"


# PRD-016 STORY-013 (F4): the hook is filled, so the xfail(strict=True) marker
# is gone; the parametrization is widened to STORY-013 AC1's five paths, the
# directory probe (`.ssh` matches `.ssh/**`) and the fixed `/proc/*/environ`
# rule (decision D-J).
@pytest.mark.parametrize(
    "path",
    [".env", "~/.aws/credentials", ".ssh/id_rsa", "x.pem", ".npmrc", ".ssh", "/proc/self/environ"],
)
def test_read_of_a_secret_glob_is_secret_read(path):
    assert classify_read(path, SECRET_FILES).rule == "secret.read"


# --- every rule produced is in the vocabulary -------------------------------------


@pytest.mark.parametrize("roots", [(), ROOTS + WIN_ROOTS], ids=["no-roots", "roots"])
@pytest.mark.parametrize("path", _ALL_PATHS + _T6)
def test_every_rule_produced_is_a_path_rule(path, roots):
    write = classify_write(path, P, roots, source_tool="t")
    read = classify_read(path, SECRET_FILES, source_tool="t")
    assert write.rule in _WRITE_RULES and write.rule in RULE_IDS
    assert read.rule in {"fs.read", "secret.read"} and read.rule in RULE_IDS
    assert write.operation == Operation("fs_write", path, "t")
    assert read.operation == Operation("fs_read", path, "t")
    for result in (write, read):
        assert isinstance(result.detail, str) and len(result.detail) <= 32


# --- never raises ----------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, b".env", 123, "a/" * 100_000, "../" * 50_000, "\x00", "C:", "//", "~"],
    # Explicit ids: pytest puts the test id in an environment variable, and
    # Windows refuses one over 32767 characters.
    ids=["none", "bytes", "int", "long", "deep-escape", "nul", "bare-drive", "bare-unc", "bare-tilde"],
)
def test_never_raises(value):
    assert isinstance(normalize_path(value), NormalizedPath)
    assert classify_write(value, P, ROOTS).rule in _WRITE_RULES
    # PRD-016 STORY-013 decision D-M: a read that cannot be classified (a
    # non-`str`) is secret.read, the strictest read outcome; a `str` still is
    # fs.read.
    expected = "fs.read" if isinstance(value, str) else "secret.read"
    assert classify_read(value, SECRET_FILES).rule == expected


def test_non_string_write_is_protected_with_empty_detail():
    assert classify_write(None, P, source_tool="t") == Classification(
        "fs.write_protected", Operation("fs_write", "", "t"), ""
    )
    # PRD-016 STORY-013 decision D-M: a non-`str` read is secret.read, not fs.read.
    assert classify_read(None, source_tool="t") == Classification("secret.read", Operation("fs_read", "", "t"), "")


@pytest.mark.parametrize("protected", [[None, "x", 3], None, ()])
def test_bad_protected_entries_are_skipped(protected):
    assert classify_write("src/a.ts", protected).rule == "fs.write_in_workspace"


def test_protected_is_a_required_argument():
    with pytest.raises(TypeError):
        classify_write("src/a.ts")  # type: ignore[call-arg]


def test_internal_error_fails_closed(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("bug")

    monkeypatch.setattr(paths, "normalize_path", _boom)
    assert classify_write("src/a.ts", P) == Classification(
        "fs.write_protected", Operation("fs_write", "src/a.ts", ""), ""
    )
    # PRD-016 STORY-013 decision D-M: an internal error on a read is secret.read.
    assert classify_read("src/a.ts").rule == "secret.read"


# --- AC5: purity -----------------------------------------------------------------


def test_paths_module_stays_pure():
    """PRD-016 Section 6.12: no settings, no file I/O, no `app` import but the vocabulary."""
    source = inspect.getsource(paths)

    assert "settings" not in vars(paths)
    assert "open(" not in source
    # `NormalizedPath(` is this module's own class; no pathlib `Path(`.
    assert not re.search(r"(?<![A-Za-z])(Pure\w*)?Path\(", source)
    assert "pathlib" not in source
    assert "os." not in source
    assert ".resolve(" not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    app_imports = [line for line in imports if " app." in line or line.startswith("from app")]
    assert app_imports == ["from app.services.action_classifiers import Classification, Operation"]


def test_importing_paths_loads_no_settings():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.services.action_classifiers.paths; "
            "print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.')))",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == str(
        ["app", "app.services", "app.services.action_classifiers", "app.services.action_classifiers.paths"]
    )
