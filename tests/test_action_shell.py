"""PRD-016 STORY-009: the shell classifier, part 1 (Sections 6.3 shell rows, 6.4, 6.8, F3; D3, D5, D16; T2, T12).

Table-driven. The command lines and the expected segments are transcribed
from the story's acceptance criteria, PRD Section 6.8 and the plan's shlex
verification table, and written out as literals, not derived from the module.
These cases are the seed of STORY-018's evasion corpus; the "evasion seeds"
section names the shlex hole each one closes.

Until STORY-010 adds the head rules, every readable segment classifies as the
placeholder `shell.unlisted` (plan decision 1).

Not covered here: what a head means (`shell.destructive`, `-c` as
`shell.inline_interpreter`, STORY-010), embedded SQL/URLs/secrets
(STORY-013), and how `evaluate()` folds the classifications (STORY-014).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import inspect
import shlex

import pytest

import app.services.action_classifiers.shell as shell
from app.services.action_classifiers import RULE_IDS, Classification, Operation
from app.services.action_classifiers.shell import (
    MAX_DEPTH,
    REDIRECTS,
    SEPARATORS,
    Redirect,
    Segment,
    ShellParse,
    classify_shell,
    parse_shell,
)

BS = "\\"


def _segments(cmd):
    parse = parse_shell(cmd)
    assert parse.unclassifiable is None, parse.unclassifiable
    return [(s.argv, s.joined_by) for s in parse.segments]


def _heads(cmd):
    return [s.head for s in parse_shell(cmd).segments]


def _rules(cmd):
    return tuple(c.rule for c in classify_shell(cmd))


def _nested(depth, inner="ls"):
    """`bash -c` nested `depth` times around `inner`, quoted by shlex (not by hand)."""
    text = inner
    for _ in range(depth):
        text = "bash -c " + shlex.quote(text)
    return text


# --- AC 1: segments ------------------------------------------------------------

_STORY_SEGMENTS = [
    (("npm", "test"), None),
    (("rm", "-rf", "build"), "&&"),
    (("ls",), ";"),
    (("wc", "-l"), "|"),
    (("echo", "x"), "&"),
]


def test_story_line_segments_with_semicolon():
    assert _segments("npm test && rm -rf build; ls | wc -l & echo x") == _STORY_SEGMENTS


def test_story_line_segments_with_newline():
    expected = list(_STORY_SEGMENTS)
    expected[2] = (("ls",), "\n")
    assert _segments("npm test && rm -rf build\nls | wc -l & echo x") == expected


@pytest.mark.parametrize(
    "cmd,expected",
    [
        # A newline after `&&` is a continuation, not an empty segment.
        ("a &&\nb", [(("a",), None), (("b",), "&&")]),
        ("a && \n b", [(("a",), None), (("b",), "&&")]),
        ("a |\nb", [(("a",), None), (("b",), "|")]),
        ("a\n\nb", [(("a",), None), (("b",), "\n")]),
        ("a\n \nb", [(("a",), None), (("b",), "\n")]),
        ("a ;\n b", [(("a",), None), (("b",), ";")]),
        ("\na", [(("a",), None)]),
        ("a\r\nb", [(("a",), None), (("b",), "\n")]),
        ("a\rb", [(("a",), None), (("b",), "\n")]),
        ("a;", [(("a",), None)]),
        ("a &", [(("a",), None)]),
        ("a\n", [(("a",), None)]),
        ("a |& b", [(("a",), None), (("b",), "|&")]),
        ("a || b", [(("a",), None), (("b",), "||")]),
        ("a;b", [(("a",), None), (("b",), ";")]),
    ],
)
def test_separators(cmd, expected):
    assert _segments(cmd) == expected


@pytest.mark.parametrize(
    "cmd,argv",
    [
        # shlex alone returns a quoted `;` as `;` (plan probe 3); the
        # sentinels keep it an argument.
        ("echo ';'", ("echo", ";")),
        ('echo ";"', ("echo", ";")),
        ("echo " + BS + ";", ("echo", ";")),
        ("find . -exec rm {} " + BS + "; -print", ("find", ".", "-exec", "rm", "{}", ";", "-print")),
        ("rm -r ';' -f /", ("rm", "-r", ";", "-f", "/")),
        ("echo '\n'", ("echo", "\n")),
        ("echo 'a|b&c<d>e'", ("echo", "a|b&c<d>e")),
        ('echo "a' + BS + '"b;c" d', ("echo", 'a"b;c', "d")),
        ('echo "' + BS + ';"', ("echo", BS + ";")),
    ],
)
def test_quoted_operators_stay_arguments(cmd, argv):
    assert _segments(cmd) == [(argv, None)]


def test_rm_with_quoted_semicolon_keeps_its_flags():
    (segment,) = parse_shell("rm -r ';' -f /").segments
    assert segment.head == "rm"
    assert segment.args == ("-r", ";", "-f", "/")


@pytest.mark.parametrize(
    "cmd,argv,redirects",
    [
        ("npm test 2>&1", ("npm", "test"), (Redirect(">&", "1", "2"),)),
        ("a 2>>err", ("a",), (Redirect(">>", "err", "2"),)),
        ("cmd &>/dev/null", ("cmd",), (Redirect("&>", "/dev/null", None),)),
        ("x >| y", ("x",), (Redirect(">|", "y", None),)),
        ("cat < .env", ("cat",), (Redirect("<", ".env", None),)),
        ("cat 2< a > b", ("cat",), (Redirect("<", "a", "2"), Redirect(">", "b", None))),
        ("> out", (), (Redirect(">", "out", None),)),
    ],
)
def test_redirects_leave_argv(cmd, argv, redirects):
    (segment,) = parse_shell(cmd).segments
    assert segment.argv == argv
    assert segment.redirects == redirects


def test_redirect_then_pipe():
    parse = parse_shell("npm test 2>&1 | tee log")
    first, second = parse.segments
    assert first.argv == ("npm", "test")
    assert first.redirects == (Redirect(">&", "1", "2"),)
    assert (second.argv, second.joined_by) == (("tee", "log"), "|")


def test_background_after_redirect():
    assert _segments("cmd &>/dev/null &") == [(("cmd",), None)]


# --- AC 2: head ----------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "r''m -rf /",
        '"rm" -rf /',
        BS + "rm -rf /",
        "/usr/bin/rm -rf /",
        '"C:' + BS + "Program Files" + BS + "x" + BS + 'rm.exe" x',
        "rm.EXE x",
        "./bin/rm x",
    ],
)
def test_head_is_rm(cmd):
    assert _heads(cmd) == ["rm"]
    assert _rules(cmd) == ("shell.unlisted",)


# --- AC 3: wrappers and assignments ---------------------------------------------


@pytest.mark.parametrize(
    "cmd,wrappers,assignments",
    [
        ("sudo rm x", ("sudo",), ()),
        ("env FOO=1 rm x", ("env",), ("FOO=1",)),
        ("FOO=1 rm x", (), ("FOO=1",)),
        ("nohup rm x", ("nohup",), ()),
        ("time rm x", ("time",), ()),
        ("xargs rm", ("xargs",), ()),
        ("doas rm x", ("doas",), ()),
        ("sudo -u root rm x", ("sudo",), ()),
        ("sudo -uroot rm x", ("sudo",), ()),
        ("sudo --user=root -E rm x", ("sudo",), ()),
        ("env -i FOO=1 rm x", ("env",), ("FOO=1",)),
        ("xargs -I{} -n1 rm", ("xargs",), ()),
        ("xargs -0 -i{} rm", ("xargs",), ()),
        ("timeout -s KILL 5 rm x", ("timeout",), ()),
        ("nice -n 10 rm x", ("nice",), ()),
        ("command rm x", ("command",), ()),
        ("builtin rm x", ("builtin",), ()),
        ("exec rm x", ("exec",), ()),
        ("stdbuf -oL rm x", ("stdbuf",), ()),
        ("setsid -f rm x", ("setsid",), ()),
        ("A=1 sudo B=2 env C+=3 nohup rm x", ("sudo", "env", "nohup"), ("A=1", "B=2", "C+=3")),
        ("/usr/bin/sudo -- rm x", ("sudo",), ()),
        ("time -p rm x", ("time",), ()),
    ],
)
def test_wrappers_and_assignments_are_stripped(cmd, wrappers, assignments):
    (segment,) = parse_shell(cmd).segments
    assert segment.head == "rm"
    assert segment.argv[segment.head_index] in ("rm",)
    assert segment.wrappers == wrappers
    assert segment.assignments == assignments
    assert segment.unclassifiable is None


@pytest.mark.parametrize(
    "cmd,head,wrappers,assignments",
    [
        ("env", "env", ("env",), ()),
        ("sudo -l", "sudo", ("sudo",), ()),
        ("FOO=1", "", (), ("FOO=1",)),
        ("env FOO=1", "env", ("env",), ("FOO=1",)),
    ],
)
def test_wrapper_or_assignment_without_a_command(cmd, head, wrappers, assignments):
    (segment,) = parse_shell(cmd).segments
    assert (segment.head, segment.wrappers, segment.assignments) == (head, wrappers, assignments)
    assert segment.head_index == len(segment.argv)
    assert segment.args == ()
    assert segment.unclassifiable is None


# --- AC 4: unclassifiable --------------------------------------------------------

_UNCLASSIFIABLE = [
    # The story's list.
    "ls $(cat x)",
    "ls `cat x`",
    'echo "$(x)"',
    'echo "`x`"',
    'eval "$C"',
    "source x.sh",
    ". x.sh",
    "diff <(a) <(b)",
    "tee >(x)",
    "cat <<< x",
    "$CMD arg",
    '"$CMD" arg',
    "${CMD} arg",
    "echo 'x",
    'echo "x',
    "echo x" + BS,
    _nested(MAX_DEPTH + 1),
    # The recursion reads the inner script.
    "bash -c 'ls $(x)'",
    'bash -c "eval x"',
    "sh -ec 'source y'",
    "sudo bash -lc 'eval x'",
    # Wrapped evaluators.
    "command eval x",
    "sudo source x",
]


@pytest.mark.parametrize("cmd", _UNCLASSIFIABLE)
def test_unclassifiable(cmd):
    assert "shell.unclassifiable" in _rules(cmd)


@pytest.mark.parametrize(
    "cmd,detail",
    [
        ("ls $(cat x)", "$("),
        ("ls `cat x`", "`"),
        ("diff <(a) <(b)", "<("),
        ("tee >(x)", ">("),
        ("cat <<< x", "<<<"),
        ("echo 'x", "'"),
        ('echo "x', '"'),
        ("echo x" + BS, BS),
        ("eval x", "eval"),
        ("$CMD arg", "$CMD"),
        (_nested(MAX_DEPTH + 1), "depth > 3"),
    ],
)
def test_unclassifiable_detail_names_the_fragment(cmd, detail):
    assert detail in [c.detail for c in classify_shell(cmd) if c.rule == "shell.unclassifiable"]


def test_depth_three_is_readable_and_four_is_not():
    assert "shell.unclassifiable" not in _rules(_nested(MAX_DEPTH))
    assert _rules(_nested(MAX_DEPTH)) == ("shell.unlisted",) * (MAX_DEPTH + 1)
    assert "shell.unclassifiable" in _rules(_nested(MAX_DEPTH + 1))
    assert parse_shell("ls", MAX_DEPTH + 1).unclassifiable == "depth > 3"


# --- Evasion seeds found in planning (STORY-018's corpus) -----------------------


def test_comment_does_not_swallow_the_next_command():
    # shlex's default commenters="#" eats the newline: `rm` became an argument of `ls`.
    assert _segments("ls # c\nrm x") == [(("ls",), None), (("rm", "x"), "\n")]


def test_hash_mid_word_is_not_a_comment():
    # shlex starts a comment mid-word, bash does not: the `rm` was lost.
    assert _segments("echo a#b; rm -rf /") == [(("echo", "a#b"), None), (("rm", "-rf", "/"), ";")]


def test_line_continuation_joins_the_word():
    assert _heads("r" + BS + "\nm -rf /") == ["rm"]


@pytest.mark.parametrize(
    "cmd",
    [
        "{rm,-rf,/}",  # brace expansion: bash runs `rm -rf /`
        "rm {-rf,/}",
        "echo {1..5}",
        "/bin/r? -rf /",  # glob head
        "/bin/r* -rf /",
        "(rm -rf /)",  # subshell
        "{ rm -rf /; }",  # brace group
        "$'" + BS + "x72m' -rf /",  # ANSI-C quoting: shlex cannot decode it
        '$"rm" -rf /',
        "C:" + BS + "Windows" + BS + "System32" + BS + "cmd.exe /c x",  # shlex ate the backslashes
        "de^l /s x",  # cmd's caret escape
        "%COMSPEC% /c x",
        "r$x -rf /",
        "sudo --bogus rm",  # an option outside the wrapper's table
        "sudo -e /etc/passwd",
        "env -S 'rm -rf /'",  # re-splits a string into argv
        "env --split-string='rm -rf /'",
        "timeout",  # missing positional
        "sudo -u",  # missing value
        "bash -c",  # -c with no script
        "bash -c -o",  # `-o` takes the word that would be the script
        "cat <<EOF\nx\nEOF",  # here-document (plan decision 5)
        "cat <<'EOF' > f\nx\nEOF",
        "a ;; b",
        "a ;& b",
        "a ; ; b",
        "| a",
        "; a",
        "a &&",
        "a ||\n",
        "a |",
        "ls >",
        "ls > | b",
        '""',
        "''",
        "",
        "   ",
        "# only a comment",
        '"a\x00b"',
        "a\x00b",
        "echo ",
        "echo ''",
        ":(){ :|:& };:",  # fork bomb: head `:(){` (STORY-010 adds shell.destructive)
        "! rm x",
    ],
)
def test_evasion_seed_is_unclassifiable(cmd):
    assert "shell.unclassifiable" in _rules(cmd)


def test_sudo_bogus_names_no_head():
    (segment,) = parse_shell("sudo --bogus rm").segments
    assert segment.unclassifiable == "--bogus"
    assert segment.head == "sudo"
    assert segment.head_index == len(segment.argv)


# --- Not over-blocked -------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd,expected",
    [
        ("awk '{print $(NF)}' f", [(("awk", "{print $(NF)}", "f"), None)]),
        ("git commit -m 'use `x`'", [(("git", "commit", "-m", "use `x`"), None)]),
        ("echo $HOME", [(("echo", "$HOME"), None)]),
        ("echo ${GITHUB_TOKEN}", [(("echo", "${GITHUB_TOKEN}"), None)]),
        ("echo $AWS_SECRET_ACCESS_KEY", [(("echo", "$AWS_SECRET_ACCESS_KEY"), None)]),
        ("echo ${x,,}", [(("echo", "${x,,}"), None)]),
        (
            "find . -name '*.py' -exec grep x {} +",
            [(("find", ".", "-name", "*.py", "-exec", "grep", "x", "{}", "+"), None)],
        ),
        ("[ -f x ] && rm x", [(("[", "-f", "x", "]"), None), (("rm", "x"), "&&")]),
        ("[[ -n x ]]", [(("[[", "-n", "x", "]]"), None)]),
        ("ls -la # list", [(("ls", "-la"), None)]),
        ("npm install " + BS + "\n  --save x", [(("npm", "install", "--save", "x"), None)]),
        ('echo "a b" c', [(("echo", "a b", "c"), None)]),
        ('echo "' + BS + '$(x)"', [(("echo", "$(x)"), None)]),
        ("echo " + BS + "$(x)", [(("echo", "$(x)"), None)]),
        ("echo '#' x", [(("echo", "#", "x"), None)]),
        ("echo {}", [(("echo", "{}"), None)]),
        ("echo 'a{b,c}'", [(("echo", "a{b,c}"), None)]),
        ("git log --format=%H", [(("git", "log", "--format=%H"), None)]),
    ],
)
def test_not_over_blocked(cmd, expected):
    assert _segments(cmd) == expected
    assert "shell.unclassifiable" not in _rules(cmd)


def test_s4_argv_join_round_trips():
    # Mirrors tests/test_action_adapters.py::test_argv_element_round_trips_through_shlex:
    # the adapter single-quotes substitution text, which is literal to bash.
    line = shlex.join(["rm", "$(x)", "`id`"])
    (segment,) = parse_shell(line).segments
    assert segment.argv == ("rm", "$(x)", "`id`")
    assert _rules(line) == ("shell.unlisted",)


@pytest.mark.parametrize("args", [["-rf", "a;b"], ["two words", "it's \"quoted\""], ["a|b", "<x>", "&"]])
def test_s4_argv_join_round_trips_operators(args):
    (segment,) = parse_shell(shlex.join(["rm", *args])).segments
    assert segment.argv == ("rm", *args)


# --- AC 5: interface and purity ---------------------------------------------------


def test_interface_fields():
    assert [f.name for f in dataclasses.fields(ShellParse)] == ["text", "depth", "segments", "unclassifiable"]
    assert [f.name for f in dataclasses.fields(Segment)] == [
        "argv", "head_index", "head", "assignments", "wrappers",
        "redirects", "joined_by", "unclassifiable", "inline",
    ]
    assert [f.name for f in dataclasses.fields(Redirect)] == ["op", "target", "fd"]
    assert SEPARATORS == frozenset({";", "&&", "||", "|", "|&", "&", "\n"})
    assert REDIRECTS == frozenset({">", ">>", "<", ">&", "<&", "&>", "&>>", ">|", "<>"})
    assert MAX_DEPTH == 3
    for cls in (ShellParse, Segment, Redirect):
        assert cls.__dataclass_params__.frozen


def test_parse_shell_returns_segments_and_args():
    parse = parse_shell("sudo git push origin main")
    assert isinstance(parse, ShellParse)
    assert (parse.text, parse.depth, parse.unclassifiable) == ("sudo git push origin main", 0, None)
    (segment,) = parse.segments
    assert segment.head == "git"
    assert segment.head_index == 1
    assert segment.args == ("push", "origin", "main")
    assert segment.inline is None


def test_inline_script_is_parsed_one_level_down():
    (segment,) = parse_shell("bash -c 'ls -l'").segments
    assert segment.head == "bash"
    assert segment.inline is not None
    assert segment.inline.depth == 1
    assert segment.inline.text == "ls -l"
    assert [s.head for s in segment.inline.segments] == ["ls"]


@pytest.mark.parametrize(
    "cmd,script",
    [
        ("bash -lc 'ls'", "ls"),
        ("sh -e -c 'ls' arg0", "ls"),
        ("bash -o pipefail -c 'ls'", "ls"),
        ("bash --rcfile x -c 'ls'", "ls"),
        ("bash --norc -c 'ls'", "ls"),
        ("/bin/zsh -c ls", "ls"),
        ("dash -c ls", "ls"),
        ("ksh -c ls", "ls"),
        ("xargs sh -c 'ls'", "ls"),
    ],
)
def test_inline_option_forms(cmd, script):
    (segment,) = parse_shell(cmd).segments
    assert segment.inline is not None and segment.inline.text == script


def test_bash_running_a_script_file_is_not_inline():
    (segment,) = parse_shell("bash script.sh").segments
    assert segment.inline is None
    assert segment.unclassifiable is None


def test_placeholder_until_story_010():
    # STORY-010 replaces this placeholder with the head rules (plan decision 1).
    assert classify_shell("ls") == (Classification("shell.unlisted", Operation("shell", "ls", ""), "ls"),)


def test_inline_classifications_come_before_the_segment_own():
    # PRD 6.4: what is embedded goes before the head's own rule.
    assert _rules("bash -c 'ls $(x)'") == ("shell.unclassifiable", "shell.unlisted")
    assert [c.detail for c in classify_shell("bash -c 'cat x | wc'; ls")] == ["cat", "wc", "bash", "ls"]


def test_whole_input_failure_is_one_classification():
    assert classify_shell("ls; echo $(x)") == (
        Classification("shell.unclassifiable", Operation("shell", "ls; echo $(x)", ""), "$("),
    )


_ALL = (
    ["npm test && rm -rf build; ls | wc -l & echo x", "bash -c 'ls $(x)'", "sudo --bogus rm"]
    + _UNCLASSIFIABLE
    + ["rm -r ';' -f /", "ls # c\nrm x", "cat <<EOF\nx\nEOF", "x" * 100, "$" + "y" * 100]
)


@pytest.mark.parametrize("cmd", _ALL)
def test_every_rule_produced_is_a_shell_rule(cmd):
    result = classify_shell(cmd, source_tool="bash")
    assert isinstance(result, tuple) and result
    for classification in result:
        assert classification.rule in RULE_IDS
        assert classification.rule.startswith("shell.")
        assert classification.operation == Operation("shell", cmd, "bash")
        assert isinstance(classification.detail, str)
        assert len(classification.detail) <= 32


@pytest.mark.parametrize(
    "value",
    [None, b"ls", 123, "a" * 200_000, "'" * 10001, "a;" * 5000, _nested(8)],
    # Explicit ids: pytest puts the test id in an environment variable, and
    # Windows refuses one over 32767 characters.
    ids=["none", "bytes", "int", "long", "quotes", "many-segments", "nested-8"],
)
def test_never_raises(value):
    result = classify_shell(value)
    assert isinstance(result, tuple) and result
    assert isinstance(parse_shell(value), ShellParse)


def test_non_string_is_unclassifiable_with_empty_detail():
    assert classify_shell(None, source_tool="t") == (
        Classification("shell.unclassifiable", Operation("shell", "", "t"), ""),
    )


def test_internal_error_becomes_unclassifiable(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("bug")

    monkeypatch.setattr(shell, "_scan", _boom)
    assert parse_shell("ls -l") == ShellParse("ls -l", 0, (), "")
    assert _rules("ls -l") == ("shell.unclassifiable",)


def test_shell_module_stays_pure():
    """PRD-016 Section 6.12: no settings, no file I/O, no `app` import but the vocabulary."""
    source = inspect.getsource(shell)

    assert "settings" not in vars(shell)
    assert "open(" not in source
    assert "Path(" not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    app_imports = [line for line in imports if " app." in line or line.startswith("from app")]
    assert app_imports == ["from app.services.action_classifiers import Classification, Operation, RuleId"]
