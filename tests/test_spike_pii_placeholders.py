"""PRD-012 STORY-012: the pure parts of scripts/spike_pii_placeholders.py, and its guards.

The spike calls a live model and asserts nothing; nothing here reaches the
network. What is tested is what its outcomes depend on:
- (b) and (c) differ from production **only** in the placeholder string;
- numbering is by first appearance and stable over a growing conversation;
- (c) restores what it masked, including a JSON number token;
- the tool parser, the workspace and the three checkers;
- the decision rules R0-R5;
- one stubbed agent loop through the real run_conversation(profile="code").

The tokenizer-only analyzer serves the `code` policy, so no NER model loads.
"""

import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import scripts.spike_pii_placeholders as spike
from app.config import settings
from app.services import pii_policy
from app.services.openrouter_client import OpenRouterResult
from app.services.pii_policy import get_pii_policy
from app.services.pii_redactor import redact_for_policy
from tests.test_query_pipeline_pii_profiles import _SHIPPED_CODE_SETTINGS

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CORPORA = _REPO_ROOT / "tests" / "corpora" / "pii"
_SAMPLES = sorted(
    path for group in ("code", "json") for path in (_CORPORA / group).iterdir() if path.is_file()
)


@pytest.fixture(autouse=True)
def _shipped_code_policy(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    for name, value in _SHIPPED_CODE_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    pii_policy.load()  # conftest's _default_pii_policy restores the policies afterwards
    yield


@pytest.fixture
def code_policy():
    return get_pii_policy("code")


@pytest.fixture
def pattern(code_policy):
    return spike.placeholder_pattern(code_policy.entities)


# --- AC 5: never collected, and importing does nothing ---


def test_the_spike_is_not_collected():
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "scripts"],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 5, completed.stdout + completed.stderr  # 5: no tests collected
    assert not Path(spike.__file__).name.startswith("test_")
    assert not Path(spike.__file__).stem.endswith("_test")


def test_importing_the_spike_builds_no_analyzer_and_opens_no_connection():
    """In a fresh interpreter: in this one, other tests build and reset the singletons."""
    probe = (
        "import scripts.spike_pii_placeholders\n"
        "from app.services import pii_redactor\n"
        "from app.db import database\n"
        "assert pii_redactor._analyzer is None, pii_redactor._analyzer\n"
        "assert pii_redactor._pattern_analyzer is None, pii_redactor._pattern_analyzer\n"
        "assert database._client is None, database._client\n"
    )
    env = {**os.environ, "OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    completed = subprocess.run(
        [sys.executable, "-c", probe], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=120, env=env
    )
    assert completed.returncode == 0, completed.stderr


def test_the_database_url_is_never_taken_from_dotenv(monkeypatch):
    monkeypatch.delenv("HARNESS_TEST_LIBSQL_URL", raising=False)
    assert spike._database_url([]) == "http://127.0.0.1:8080"
    assert spike._database_url(["--database-url", "http://localhost:9"]) == "http://localhost:9"
    assert spike._database_url(["--database-url=http://localhost:9"]) == "http://localhost:9"


def test_guards_refuse_a_remote_database_and_transcripts_in_the_repo(tmp_path):
    with pytest.raises(SystemExit):
        spike._guard_local("libsql://example.turso.io", allow_remote=False)
    spike._guard_local("libsql://example.turso.io", allow_remote=True)
    spike._guard_local("http://127.0.0.1:8080", allow_remote=False)
    with pytest.raises(SystemExit):
        spike._guard_outside_repo(_REPO_ROOT / "transcripts")
    spike._guard_outside_repo(tmp_path)


def test_a_dummy_key_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-key")
    assert spike.main(["--model", "any/model"]) == 1
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


# --- schemes: parity with production (F-2) ---


@pytest.mark.parametrize("path", _SAMPLES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_fixed_scheme_is_redact_for_policy(path, code_policy):
    text = path.read_text(encoding="utf-8")
    assert tuple(spike.FixedScheme().redact(text, code_policy)) == tuple(redact_for_policy(text, code_policy))


@pytest.mark.parametrize("path", _SAMPLES, ids=lambda p: f"{p.parent.name}/{p.name}")
@pytest.mark.parametrize("persistent", [False, True])
def test_indexed_scheme_differs_from_production_only_in_the_suffix(path, persistent, code_policy):
    text = path.read_text(encoding="utf-8")
    indexed, entities = spike.IndexedScheme(persistent).redact(text, code_policy)
    expected = redact_for_policy(text, code_policy)

    assert spike.re.sub(r"<([A-Z_]+?)_\d+>", r"<\1>", indexed) == expected.text
    assert entities == expected.entities


def test_the_chat_policy_is_never_renumbered():
    chat = get_pii_policy("chat")
    scheme = spike.IndexedScheme(persistent=True)
    sentinel = object()
    original = spike._ORIGINAL_REDACT
    try:
        spike._ORIGINAL_REDACT = lambda text, policy: sentinel
        assert scheme.redact("mail jane.doe@example.com", chat) is sentinel
    finally:
        spike._ORIGINAL_REDACT = original


def test_control_masks_nothing(code_policy):
    assert spike.ControlScheme().redact("mail jane.doe@example.com", code_policy) == ("mail jane.doe@example.com", [])


def test_redaction_disabled_masks_nothing(monkeypatch, code_policy):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    assert spike.IndexedScheme(False).redact("mail jane.doe@example.com", code_policy) == ("mail jane.doe@example.com", [])


# --- numbering ---


def test_numbering_is_by_first_appearance_per_type(code_policy):
    scheme = spike.IndexedScheme(persistent=False)
    text = (
        "Write to bob.stone@example.org, then jane.doe@example.com, then bob.stone@example.org again. "
        "Call +1 415 555 0134."
    )
    redacted, _ = scheme.redact(text, code_policy)

    assert redacted == (
        "Write to <EMAIL_ADDRESS_1>, then <EMAIL_ADDRESS_2>, then <EMAIL_ADDRESS_1> again. "
        "Call <PHONE_NUMBER_1>."
    )


def test_numbering_is_stable_over_a_growing_conversation(code_policy):
    """Arm (b) restarts every send, yet the unchanged prefix renumbers identically."""
    scheme = spike.IndexedScheme(persistent=False)
    first = ["Owner: jane.doe@example.com", "Backup: bob.stone@example.org"]
    later = first + ["New: ana.ruiz@example.com and jane.doe@example.com"]

    scheme.begin_request()
    before = [scheme.redact(m, code_policy)[0] for m in first]
    scheme.begin_request()
    after = [scheme.redact(m, code_policy)[0] for m in later]

    assert after[:2] == before
    assert after[2] == "New: <EMAIL_ADDRESS_3> and <EMAIL_ADDRESS_1>"


def test_b_restarts_on_every_send_and_c_does_not(code_policy):
    b, c = spike.IndexedScheme(persistent=False), spike.IndexedScheme(persistent=True)
    for scheme in (b, c):
        scheme.begin_request()
        scheme.redact("jane.doe@example.com", code_policy)
        scheme.begin_request()

    assert b.redact("bob.stone@example.org", code_policy)[0] == "<EMAIL_ADDRESS_1>"
    assert c.redact("bob.stone@example.org", code_policy)[0] == "<EMAIL_ADDRESS_2>"


# --- restoration ---


def test_c_restores_what_it_masked_and_counts_unknown_placeholders(code_policy):
    scheme = spike.IndexedScheme(persistent=True)
    scheme.redact("Owner jane.doe@example.com, phone +1 415 555 0134", code_policy)

    restored, unresolved = scheme.restore(
        'owner = "<EMAIL_ADDRESS_1>"  # call <PHONE_NUMBER_1>, not <EMAIL_ADDRESS_9>'
    )

    assert restored == 'owner = "jane.doe@example.com"  # call +1 415 555 0134, not <EMAIL_ADDRESS_9>'
    assert unresolved == 1


def test_b_never_restores(code_policy):
    scheme = spike.IndexedScheme(persistent=False)
    scheme.redact("jane.doe@example.com", code_policy)
    assert scheme.restore("<EMAIL_ADDRESS_1>") == ("<EMAIL_ADDRESS_1>", 0)


def test_a_json_number_token_is_quoted_then_restored_bare(code_policy):
    scheme = spike.IndexedScheme(persistent=True)
    document = '{"owner": "jane.doe@example.com", "phone": 14155550134}'

    redacted, entities = scheme.redact(document, code_policy)

    assert redacted == '{"owner": "<EMAIL_ADDRESS_1>", "phone": "<PHONE_NUMBER_1>"}'
    assert spike.json.loads(redacted)
    assert scheme.restore(redacted) == (document, 0)


# --- placeholder counting ---


def test_placeholder_pattern_counts_fixed_indexed_and_ner_placeholders(pattern):
    text = "<EMAIL_ADDRESS> <EMAIL_ADDRESS_12> <PERSON> <IBAN_CODE_3> <div> <email_address> <NOT_A_TYPE>"
    assert pattern.findall(text) == ["<EMAIL_ADDRESS>", "<EMAIL_ADDRESS_12>", "<PERSON>", "<IBAN_CODE_3>"]


# --- tool parser ---


def test_each_tool_parses():
    assert spike.parse_tool_call("<read_file><path>a.json</path></read_file>") == spike.ToolCall(
        "read_file", {"path": "a.json"}
    )
    assert spike.parse_tool_call(
        "Fixing it.\n<replace_in_file><path>a.py</path><old>x = 1</old><new>x = 2</new></replace_in_file>"
    ) == spike.ToolCall("replace_in_file", {"path": "a.py", "old": "x = 1", "new": "x = 2"})
    assert spike.parse_tool_call("<write_file><path>b.py</path><content>\nprint(1)\n</content></write_file>") == (
        spike.ToolCall("write_file", {"path": "b.py", "content": "print(1)"})
    )
    assert spike.parse_tool_call("All done. <done/>") == spike.ToolCall("done", {})
    assert spike.parse_tool_call("<done>") == spike.ToolCall("done", {})


def test_a_placeholder_inside_an_argument_is_content():
    reply = '<write_file><path>u.json</path><content>{"email": "<EMAIL_ADDRESS_1>"}</content></write_file>'
    call = spike.parse_tool_call(reply)
    assert call.arguments["content"] == '{"email": "<EMAIL_ADDRESS_1>"}'


def test_content_may_contain_its_own_closing_tag_once():
    reply = "<write_file><path>t.xml</path><content>a</content>b</content></write_file>"
    assert spike.parse_tool_call(reply).arguments["content"] == "a</content>b"


@pytest.mark.parametrize(
    "reply",
    [
        "I will read the file now.",
        "<read_file><path>a.json</path>",
        "<replace_in_file><path>a.py</path><new>x</new></replace_in_file>",
        "<write_file/>",
    ],
)
def test_malformed_calls_are_parse_errors(reply):
    assert isinstance(spike.parse_tool_call(reply), spike.ParseError)


# --- workspace ---


def test_workspace_read_returns_the_raw_content_unfenced():
    workspace = spike.Workspace({"./a.txt": "mail jane.doe@example.com"})
    assert workspace.apply(spike.ToolCall("read_file", {"path": "a.txt"})).result == "mail jane.doe@example.com"
    assert workspace.apply(spike.ToolCall("read_file", {"path": "b.txt"})).result.startswith("error:")


def test_workspace_replace_hits_misses_and_refuses_ambiguity():
    workspace = spike.Workspace({"a.py": "x = 1\ny = 1\n"})

    miss = workspace.apply(spike.ToolCall("replace_in_file", {"path": "a.py", "old": "z = 1", "new": "z = 2"}))
    ambiguous = workspace.apply(spike.ToolCall("replace_in_file", {"path": "a.py", "old": " = 1", "new": " = 2"}))
    hit = workspace.apply(spike.ToolCall("replace_in_file", {"path": "a.py", "old": "x = 1", "new": "x = 2"}))

    assert miss.replace_miss and "not found" in miss.result
    assert not ambiguous.replace_miss and "not unique" in ambiguous.result
    assert not hit.replace_miss and workspace.files["a.py"] == "x = 2\ny = 1\n"


def test_workspace_write_stores_placeholders_as_written_and_done_ends():
    workspace = spike.Workspace({})
    workspace.apply(spike.ToolCall("write_file", {"path": "b.py", "content": 'EMAIL = "<EMAIL_ADDRESS>"'}))
    assert workspace.files["b.py"] == 'EMAIL = "<EMAIL_ADDRESS>"'
    assert workspace.apply(spike.ToolCall("done", {})).done


# --- checkers ---


def _fixture_edit(content: str) -> str:
    """Flip pobrien's `active`, textually, the way a careful agent would."""
    start = content.index('"username": "pobrien"')
    at = content.index('"active": true', start)
    return content[:at] + '"active": false' + content[at + len('"active": true'):]


def _files(task_id: str) -> dict:
    return spike.TASKS[task_id].files()


def test_fixture_checker(pattern):
    files = _files("fixture")
    edited = _fixture_edit(files["fixtures/seed-users.json"])
    check = spike.TASKS["fixture"].check

    assert check({"fixtures/seed-users.json": edited}, pattern) == (True, "ok")
    assert not check({"fixtures/seed-users.json": files["fixtures/seed-users.json"]}, pattern)[0]  # no edit
    with_placeholder = edited.replace("patrick.obrien@example.org", "<EMAIL_ADDRESS>")
    correct, reason = check({"fixtures/seed-users.json": with_placeholder}, pattern)
    assert not correct and "placeholder" in reason
    assert not check({"fixtures/seed-users.json": edited[:-10]}, pattern)[0]  # broken JSON
    assert not check({}, pattern)[0]


def test_first_customer_contact_reads_the_corpus():
    assert spike.first_customer_contact() == ("jane.doe@example.com", "+1 415 555 0134")


def test_test_checker(pattern):
    check = spike.TASKS["test"].check
    good = (
        "from billing_seed import CUSTOMERS\n\n"
        "def test_first_customer():\n"
        '    assert CUSTOMERS[0].email == "jane.doe@example.com"\n'
        '    assert CUSTOMERS[0].phone == "+1 415 555 0134"\n'
    )
    path = "tests/test_billing_contacts.py"

    assert check({path: good}, pattern) == (True, "ok")
    assert not check({path: good.replace("jane.doe@example.com", "<EMAIL_ADDRESS>")}, pattern)[0]
    assert not check({path: good.replace("+1 415 555 0134", "+1 415 555 0000")}, pattern)[0]
    assert not check({path: good + "def broken(:\n"}, pattern)[0]
    assert not check({}, pattern)[0]


def test_rename_checker(pattern):
    check = spike.TASKS["rename"].check
    original = _files("rename")["deploy/staging-values.yaml"]
    renamed = original.replace("  oncall-phone:", "  oncallPhone:").replace(
        "  SUPPORT_CONTACT_EMAIL:", "  SUPPORT_EMAIL:"
    )
    path = "deploy/staging-values.yaml"

    assert check({path: renamed}, pattern) == (True, "ok")
    assert not check({path: original}, pattern)[0]
    assert not check({path: renamed.replace("maria.lopez@example.com", "<EMAIL_ADDRESS>")}, pattern)[0]
    assert not check({path: renamed.replace("maria.lopez@example.com", "maria@example.com")}, pattern)[0]


def test_instructions_carry_no_pii(code_policy):
    for task in spike.TASKS.values():
        assert redact_for_policy(task.instruction, code_policy).entities == [], task.id


# --- decision rules ---


def _runs(correct: dict[str, list[list[bool]]], sent: int = 5) -> list:
    """{arm: [[task1 run1, run2, ...], [task2 ...], [task3 ...]]} -> TaskRuns."""
    rows = []
    for arm, per_task in correct.items():
        for task_index, outcomes in enumerate(per_task):
            for run, ok in enumerate(outcomes, start=1):
                rows.append(
                    spike.TaskRun(arm=arm, task=f"t{task_index}", run=run, correct=ok, sent=0 if arm == "control" else sent)
                )
    return rows


_ALL = [[True] * 3] * 3
_NONE = [[False] * 3] * 3


def test_r2_keeps_a_when_it_does_not_fail():
    decision = spike.decide(_runs({"control": _ALL, "a": _ALL, "b": _ALL, "c": _ALL}))
    assert (decision.rule, decision.outcome) == ("R2", "a")


def test_r2_notes_b_when_it_scores_well_above_a_that_still_passes():
    # 6/9 = control 9/9 - 1/3 exactly, so (a) does not fail; no task fails every run.
    a = [[True, True, False], [True, False, True], [False, True, True]]
    decision = spike.decide(_runs({"control": _ALL, "a": a, "b": _ALL, "c": _ALL}))
    assert (decision.rule, decision.outcome) == ("R2", "a")
    assert "Future Considerations" in decision.detail  # (b) 9/9 - (a) 6/9 >= 1/3


def test_r2_does_not_note_b_when_the_gap_is_small():
    a = [[True] * 3, [True] * 3, [True, True, False]]  # 8/9
    decision = spike.decide(_runs({"control": _ALL, "a": a, "b": _ALL, "c": _ALL}))
    assert decision.outcome == "a"
    assert "Future Considerations" not in decision.detail


def test_r1_a_task_failing_every_run_fails_the_arm():
    a = [[True] * 3, [True] * 3, [False] * 3]  # 6/9: within 1/3 of control, but t2 always fails
    decision = spike.decide(_runs({"control": _ALL, "a": a, "b": _ALL, "c": _ALL}))
    assert (decision.rule, decision.outcome) == ("R3", "b")


def test_r3_picks_b_when_a_fails_and_b_does_not():
    decision = spike.decide(_runs({"control": _ALL, "a": _NONE, "b": _ALL, "c": _ALL}))
    assert (decision.rule, decision.outcome) == ("R3", "b")


def test_r4_justifies_c_but_does_not_adopt_it():
    decision = spike.decide(_runs({"control": _ALL, "a": _NONE, "b": _NONE, "c": _ALL}))
    assert (decision.rule, decision.outcome) == ("R4", "c justified, not adopted")
    assert "PII at rest" in decision.detail


def test_r5_keeps_a_when_everything_fails():
    decision = spike.decide(_runs({"control": _ALL, "a": _NONE, "b": _NONE, "c": _NONE}))
    assert (decision.rule, decision.outcome) == ("R5", "a")


def test_r0_is_inconclusive_when_control_cannot_do_the_tasks():
    control = [[True] * 3, [False] * 3, [False] * 3]  # 3/9 < 2/3
    decision = spike.decide(_runs({"control": control, "a": _NONE, "b": _NONE, "c": _NONE}))
    assert (decision.rule, decision.outcome) == ("R0", "inconclusive")


def test_a_task_that_sent_no_placeholder_under_a_invalidates_the_run():
    rows = _runs({"control": _ALL, "a": _ALL, "b": _ALL, "c": _ALL}, sent=0)
    decision = spike.decide(rows)
    assert decision.outcome == "invalid"
    assert spike.invalid_tasks(rows) == ["t0", "t1", "t2"]


def test_decision_needs_all_four_arms():
    assert spike.decide(_runs({"a": _ALL, "c": _ALL})).outcome == "not computed"


def test_success_is_an_exact_fraction():
    rows = _runs({"control": [[True, False, True]]})
    assert spike.success(rows, "control") == Fraction(2, 3)


def test_report_prints_both_tables_and_the_decision():
    rows = _runs({"control": _ALL, "a": _ALL, "b": _ALL, "c": _ALL})
    for row in rows:
        row.task = list(spike.TASKS)[int(row.task[1])]
    text = spike.report(rows, {"model": "stub/model"})

    assert "| a | fixture | 3/3 |" in text
    assert "| control | 9/9 | 1.00 | 0 |" in text
    assert "outcome: **a**" in text


# --- the loop, end to end through the real pipeline (stub upstream) ---


class _ScriptedAgent:
    """read_file, then write_file of the edited whole file as it saw it, then done."""

    def __init__(self):
        self.seen: list = []

    def __call__(self, messages, model, api_key=None, params=None):
        self.seen.append(list(messages))
        turn = len(self.seen)
        if turn == 1:
            reply = "<read_file><path>fixtures/seed-users.json</path></read_file>"
        elif turn == 2:
            edited = _fixture_edit(messages[-1].content)
            reply = f"<write_file><path>fixtures/seed-users.json</path><content>\n{edited}\n</content></write_file>"
        else:
            reply = "<done/>"
        return OpenRouterResult(response=reply, model_used=model, tokens_used=10)


@pytest.mark.parametrize(
    "arm, correct, placeholder_sent",
    [("control", True, False), ("a", False, True), ("b", False, True), ("c", True, True)],
)
def test_the_loop_through_run_conversation(temp_db, arm, correct, placeholder_sent):
    agent = _ScriptedAgent()

    outcome = spike.run_task(
        spike.TASKS["fixture"], arm, 1, model="stub/model", nonce="pytest", max_turns=5, upstream_call=agent
    )

    assert outcome.aborted is None, outcome.aborted
    assert outcome.turns == 3
    assert outcome.correct is correct, outcome.reason
    assert (outcome.sent > 0) is placeholder_sent
    # The model read the file masked (or not) by the arm's own scheme...
    seen = agent.seen[1][-1].content
    assert {"control": "patrick.obrien@example.org", "a": "<EMAIL_ADDRESS>", "b": "<EMAIL_ADDRESS_", "c": "<EMAIL_ADDRESS_"}[arm] in seen
    # ...and only (c) got the real values back into the file.
    if arm in ("a", "b"):
        assert outcome.in_artifact > 0 and outcome.in_output > 0
    if arm == "c":
        assert outcome.in_output > 0 and outcome.in_artifact == 0 and outcome.unresolved == 0


def test_an_upstream_error_aborts_and_is_incorrect_even_if_the_workspace_passes(temp_db):
    """The file is already right when <done/> fails to arrive: still incorrect."""
    agent = _ScriptedAgent()

    def flaky(messages, model, api_key=None, params=None):
        if len(agent.seen) == 2:
            raise spike.OpenRouterError("OpenRouter request failed: 502 Bad Gateway")
        return agent(messages, model, api_key, params)

    outcome = spike.run_task(
        spike.TASKS["fixture"], "control", 1, model="stub/model", nonce="pytest-flaky", max_turns=5, upstream_call=flaky
    )

    assert outcome.aborted == "upstream error: OpenRouter request failed: 502 Bad Gateway"
    assert outcome.reason == "ok"  # the checker passed...
    assert outcome.correct is False  # ...but the agent never finished


def test_the_patch_is_removed_after_the_run(temp_db):
    spike.run_task(
        spike.TASKS["fixture"], "c", 1, model="stub/model", nonce="pytest-unpatch", max_turns=5,
        upstream_call=_ScriptedAgent(),
    )
    assert spike.query_pipeline._redact is spike._ORIGINAL_REDACT


def test_a_blocked_send_aborts_the_task_run(temp_db):
    """The same user id twice: the second run's first send is a duplicate (F-4)."""
    task = spike.TASKS["fixture"]
    spike.run_task(task, "a", 1, model="stub/model", nonce="pytest-dup", max_turns=5, upstream_call=_ScriptedAgent())

    again = spike.run_task(task, "a", 1, model="stub/model", nonce="pytest-dup", max_turns=5, upstream_call=_ScriptedAgent())

    assert again.aborted is not None and "Duplicate" in again.aborted
    assert not again.correct
