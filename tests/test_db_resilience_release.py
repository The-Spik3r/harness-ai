"""PRD-018 STORY-010: a release is made under a journaled record (F7, D13, D14, O2, O8).

`audit_logger.log_query` returns an `AuditRef`. When the audit insert raises
`StorageUnavailableError` the row is fsynced to the journal and the ref carries
`audit_id=None`; when that fails too, `AuditUnavailableError` propagates and
nothing is released (D10, T5). Step 8's decisions ride in the row's own entry
(`journal_decisions`), or are journaled alone when only they failed. A
journaled success is released with `audit_id: null` + `audit_ref` (O2, D14).

Nearly every test is non-`db`: the driver-facing writers (`insert_audit_log`,
`insert_action_decisions`) are stubbed by name in the module that bound them, so
the conftest guard proves zero driver calls. The one `db` test at the end runs a
tools request against a faulted driver and drains the journal back.

Orchestrator rulings applied here: R1 (an unrecordable refusal is refused with
503), R2 (an unrecordable row on a response with decisions is
`ActionAuditError`), R3 (`record()` refuses a journaled ref with `ValueError`;
the pipeline does not call it), R5 (`Retry-After` from the `__context__` chain).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import audit_journal, database, journal_drainer
from app.db.errors import (
    AuditUnavailableError,
    IntegrityError,
    MissingRelationError,
    StorageError,
    StorageUnavailableError,
)
from app.main import app
from app.middleware.auth import require_identity
from app.models.messages import Message, ToolCallSpec
from app.models.schemas import QueryBlockedForbiddenResponse, QuerySuccessResponse
from app.services import action_audit, audit_logger, chat_sessions, query_pipeline
from app.services.action_adapters import ToolCall
from app.services.action_config import BUILT_IN_POLICY
from app.services.action_policy import evaluate
from app.services.audit_logger import AuditRef, log_query
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult, ToolParams
from app.services.query_pipeline import ActionAuditError
from app.services.storage_faults import (
    STORAGE_UNAVAILABLE_DETAIL,
    audit_unavailable_retry_after,
)
from app.services.v1_translate import AUDIT_UNAVAILABLE_MESSAGE
from tests.db_faults import STREAM_EXPIRED, Fault

_HEX = re.compile(r"^[0-9a-f]{32}$")
_CANARY = "CANARY-driver-text-9a3c"
_USER = Identity("dana@release.test", "user")
_OUTAGE_TEXT = f"Hrana: `stream error: STREAM_EXPIRED` {_CANARY}"
_RETRY_AFTER = 7
_READ = ToolCallSpec("call_r", "read", '{"path": "src/a.py"}')
_SHELL = ToolCallSpec("call_s", "shell", '{"command": "rm -rf /"}')
_TOOL_PARAMS = ToolParams(tools=({"type": "function", "function": {"name": "read"}},), tool_choice=None)
_V1_BODY = {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hello world"}]}
_V1_TOOL = {
    "type": "function",
    "function": {"name": "bash", "description": "run", "parameters": {"type": "object"}},
}
_AUDIT_FAILED = {
    "error": {
        "message": "Action audit failed: decisions could not be recorded",
        "type": "api_error", "param": None, "code": "internal_error", "harness": None,
    }
}


def _admin_headers():
    return {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


def _outage(retry_after=_RETRY_AFTER) -> StorageUnavailableError:
    return StorageUnavailableError(_OUTAGE_TEXT, retry_after)


@pytest.fixture
def journal(tmp_path):
    """The module slot, open under `tmp_path` and always closed (the conftest fails a leak)."""
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    yield opened
    audit_journal.close_journal()


def _raiser(exc):
    def _raise(*args, **kwargs):
        raise exc

    return _raise


@pytest.fixture
def audit_outage(monkeypatch):
    """The audit-row insert fails with an outage, as when the retry budget is spent."""
    monkeypatch.setattr(audit_logger, "insert_audit_log", _raiser(_outage()))


@pytest.fixture
def pipeline_stubs(monkeypatch):
    """Usage limits off and step 1's duplicate lookup answering "not a duplicate": no driver call anywhere."""
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
    monkeypatch.setattr(
        query_pipeline, "check_duplicate", lambda *a, **k: SimpleNamespace(is_duplicate=False)
    )


class _Upstream:
    """An upstream stub that accepts `tools=` and answers with `content` and `calls`."""

    def __init__(self, content="ok", *calls):
        self.content, self.calls, self.sent = content, calls, 0

    def __call__(self, messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        self.sent += 1
        return OpenRouterResult(
            response=self.content, model_used=model, tokens_used=12, tool_calls=self.calls,
            finish_reason="tool_calls" if self.calls else "stop",
        )


def _run(upstream=None, **kwargs):
    return query_pipeline.run_conversation(
        identity=kwargs.pop("identity", _USER),
        messages=kwargs.pop("messages", [Message("user", "list files")]),
        device=None, model="gpt-4", openrouter_api_key=None,
        call_openrouter=upstream or _Upstream(), **kwargs,
    )


def _run_tools(*calls, **kwargs):
    return _run(_Upstream("", *calls), tools=_TOOL_PARAMS, **kwargs)


# --- log_query returns a ref ---------------------------------------------------


def test_log_query_returns_a_ref_with_the_committed_id(monkeypatch):
    seen = []

    def insert(entry):
        seen.append(entry)
        return 41

    monkeypatch.setattr(audit_logger, "insert_audit_log", insert)

    ref = log_query("dana", "hello")

    assert ref == AuditRef(41, seen[0].write_id)
    assert _HEX.match(ref.write_id)
    with pytest.raises(Exception):
        ref.audit_id = 1  # frozen


def test_log_query_journals_on_storage_unavailable_and_returns_a_null_id(
    journal, audit_outage, caplog
):
    with caplog.at_level(logging.DEBUG):
        ref = log_query("dana", "hello", response="hi")

    assert ref.audit_id is None and _HEX.match(ref.write_id)
    (entry,) = journal.pending()
    assert entry.audit is not None and entry.audit.write_id == ref.write_id
    assert entry.write_id == ref.write_id and entry.decisions == ()
    assert "audit row journaled" in caplog.text
    assert _CANARY not in caplog.text  # the driver text is not ours to log


def test_log_query_journals_the_decisions_in_the_same_entry(journal, audit_outage):
    seen = []

    def journal_decisions(write_id):
        seen.append(write_id)
        return _rows(write_id, 2)

    ref = log_query("dana", "hello", journal_decisions=journal_decisions)

    assert seen == [ref.write_id]
    (entry,) = journal.pending()
    assert [d.write_id for d in entry.decisions] == [f"{ref.write_id}:0", f"{ref.write_id}:1"]


def test_journal_decisions_is_not_called_on_the_healthy_path(monkeypatch):
    monkeypatch.setattr(audit_logger, "insert_audit_log", lambda entry: 5)

    ref = log_query("dana", "hello", journal_decisions=_raiser(AssertionError("built eagerly")))

    assert ref.audit_id == 5


def test_log_query_journal_full_raises_audit_unavailable(tmp_path, audit_outage):
    audit_journal.open_journal(str(tmp_path / "tiny"), 1, 2)
    try:
        with pytest.raises(AuditUnavailableError, match="full"):
            log_query("dana", "hello")
    finally:
        audit_journal.close_journal()


def test_log_query_with_no_journal_open_raises_audit_unavailable(audit_outage):
    assert audit_journal.current() is None
    with pytest.raises(AuditUnavailableError):
        log_query("dana", "hello")


@pytest.mark.parametrize(
    "failure",
    [IntegrityError("c", "x"), MissingRelationError("audit_logs", "x"), StorageError("plain")],
    ids=["integrity", "missing-relation", "plain-storage-error"],
)
def test_log_query_statement_failure_is_not_journaled(journal, monkeypatch, failure):
    monkeypatch.setattr(audit_logger, "insert_audit_log", _raiser(failure))

    with pytest.raises(type(failure)):
        log_query("dana", "hello")

    assert journal.pending() == []




# --- record: keys, the decisions-only entry, R3, O8 ----------------------------


def _decisions(count):
    return [
        evaluate(ToolCall(f"call_{i}", "read", json.dumps({"path": f"a{i}"})), _USER, BUILT_IN_POLICY)
        for i in range(count)
    ]


def _rows(write_id, count, audit_id=None):
    return action_audit.decision_rows(_decisions(count), _USER, write_id, audit_id)


def test_decision_rows_key_by_the_write_id_and_share_one_timestamp():
    rows = _rows("a" * 32, 3, audit_id=9)

    assert [r.write_id for r in rows] == [f"{'a' * 32}:{i}" for i in range(3)]
    assert {r.audit_id for r in rows} == {9} and len({r.timestamp for r in rows}) == 1


def test_record_keys_decisions_by_the_audit_write_id(monkeypatch):
    written = []
    monkeypatch.setattr(
        action_audit, "insert_action_decisions", lambda rows: written.extend(rows) or [1, 2]
    )
    ref = AuditRef(41, "c" * 32)

    ids = action_audit.record(_decisions(2), _USER, audit_ref=ref)

    assert ids == [1, 2]
    assert [r.write_id for r in written] == [f"{ref.write_id}:0", f"{ref.write_id}:1"]
    assert {r.audit_id for r in written} == {41}


def test_record_decisions_exhausted_journal_a_decisions_only_entry(journal, monkeypatch, caplog):
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(_outage()))
    ref = AuditRef(41, "d" * 32)

    with caplog.at_level(logging.DEBUG):
        assert action_audit.record(_decisions(2), _USER, audit_ref=ref) == []

    (entry,) = journal.pending()
    assert entry.audit is None and entry.audit_id == 41 and entry.write_id == ref.write_id
    assert [d.write_id for d in entry.decisions] == [f"{ref.write_id}:0", f"{ref.write_id}:1"]
    assert "action decisions journaled" in caplog.text and _CANARY not in caplog.text
    # R6: the same write_id twice is refused by the journal. The row committed
    # (audit_id is an int), so its write_id was never journaled and is unique.
    with pytest.raises(ValueError, match="already pending"):
        journal.append(None, _rows(ref.write_id, 1, 41), audit_id=41, write_id=ref.write_id)


def test_record_refuses_a_journaled_ref(journal, monkeypatch):
    # PRD-018 D13, R3: a journaled row's decisions already ride in its entry.
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(AssertionError("wrote")))

    with pytest.raises(ValueError, match="journaled AuditRef"):
        action_audit.record(_decisions(1), _USER, audit_ref=AuditRef(None, "e" * 32))

    assert journal.pending() == []


def test_record_without_a_ref_never_journals(journal, monkeypatch):
    # PRD-018 O8: a direct call (PRD-023's pre-execution write) commits or raises.
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(_outage()))

    with pytest.raises(StorageUnavailableError):
        action_audit.record(_decisions(1), _USER)

    assert journal.pending() == []


def test_insert_action_decisions_never_journals(journal, monkeypatch):
    # PRD-018 O8, AC 5: the database function itself never journals.
    monkeypatch.setattr(database, "_unit_of_work", _raiser(_outage()))

    with pytest.raises(StorageUnavailableError):
        database.insert_action_decisions(_rows("f" * 32, 1))

    assert journal.pending() == []


def test_record_decisions_journal_failure_raises_audit_unavailable(monkeypatch):
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(_outage()))
    assert audit_journal.current() is None

    with pytest.raises(AuditUnavailableError):
        action_audit.record(_decisions(1), _USER, audit_ref=AuditRef(41, "9" * 32))


# --- the pipeline: step 8 --------------------------------------------------------


def test_step8_row_journaled_releases_with_null_id_and_ref(journal, audit_outage, pipeline_stubs):
    result = _run()

    assert isinstance(result, QuerySuccessResponse)
    assert result.audit_id is None
    (entry,) = journal.pending()
    assert result.audit_ref == entry.write_id and _HEX.match(result.audit_ref)


def test_step8_row_journaled_carries_its_decisions_in_the_same_entry(
    journal, audit_outage, pipeline_stubs, monkeypatch
):
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(AssertionError("wrote")))
    # PRD-018 R3: the pipeline does not call record() for a journaled ref.
    monkeypatch.setattr(action_audit, "record", _raiser(AssertionError("record called")))

    result = _run_tools(_READ, _SHELL)

    assert result.audit_id is None and result.tool_outcome is not None
    (entry,) = journal.pending()
    assert entry.audit is not None and entry.audit.write_id == result.audit_ref
    assert [d.write_id for d in entry.decisions] == [f"{result.audit_ref}:0", f"{result.audit_ref}:1"]
    assert [d.tool_call_id for d in entry.decisions] == ["call_r", "call_s"]
    assert [d.decision for d in entry.decisions] == ["allow", "deny"]


def test_step8_decisions_journaled_alone_after_the_row_committed(
    journal, pipeline_stubs, monkeypatch
):
    monkeypatch.setattr(audit_logger, "insert_audit_log", lambda entry: 41)
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(_outage()))

    result = _run_tools(_READ, _SHELL)

    assert result.audit_id == 41 and _HEX.match(result.audit_ref)
    (entry,) = journal.pending()
    assert entry.audit is None and entry.audit_id == 41 and entry.write_id == result.audit_ref
    assert [d.write_id for d in entry.decisions] == [f"{result.audit_ref}:0", f"{result.audit_ref}:1"]


def test_step8_decisions_journal_failure_is_todays_d8_path(pipeline_stubs, monkeypatch):
    marked = []
    monkeypatch.setattr(audit_logger, "insert_audit_log", lambda entry: 41)
    monkeypatch.setattr(action_audit, "insert_action_decisions", _raiser(_outage()))
    monkeypatch.setattr(query_pipeline, "mark_audit_log_failed", lambda *a: marked.append(a))
    assert audit_journal.current() is None

    with pytest.raises(ActionAuditError) as raised:
        _run_tools(_READ)

    assert isinstance(raised.value.__cause__, AuditUnavailableError)
    assert [m[0] for m in marked] == [41]


def test_step8_row_unrecordable_on_a_tools_response_is_action_audit_error(
    audit_outage, pipeline_stubs, monkeypatch
):
    # PRD-018 6.7, R2: no row exists, so nothing is marked failed.
    marked = []
    monkeypatch.setattr(query_pipeline, "mark_audit_log_failed", lambda *a: marked.append(a))
    upstream = _Upstream("", _READ)

    with pytest.raises(ActionAuditError) as raised:
        _run(upstream, tools=_TOOL_PARAMS)

    assert isinstance(raised.value.__cause__, AuditUnavailableError)
    assert marked == [] and upstream.sent == 1


def test_step8_row_unrecordable_without_decisions_is_audit_unavailable(audit_outage, pipeline_stubs):
    # `tools=` set, but the response has no calls: it behaves like any other request.
    with pytest.raises(AuditUnavailableError):
        _run(_Upstream("just text"), tools=_TOOL_PARAMS)


# --- refusal rows (R1) -----------------------------------------------------------

_AUDITOR = Identity("rev@release.test", "auditor")  # lacks query:submit


def test_refusal_row_journaled_keeps_the_refusal_shape(journal, audit_outage, pipeline_stubs):
    result = _run(identity=_AUDITOR)

    assert isinstance(result, QueryBlockedForbiddenResponse)
    (entry,) = journal.pending()
    assert entry.audit.denied_permission == result.required_permission


def test_refusal_row_unrecordable_raises(audit_outage, pipeline_stubs):
    # PRD-018 D10/T5, R1: a refusal is a release, so it is refused with 503, not returned.
    with pytest.raises(AuditUnavailableError):
        _run(identity=_AUDITOR)


# --- /query ----------------------------------------------------------------------


def _query_upstream(monkeypatch):
    monkeypatch.setattr(
        "app.routers.query.call_openrouter",
        lambda *a, **k: OpenRouterResult(response="Hi there!", model_used="gpt-4", tokens_used=12),
    )


def test_query_journaled_success_is_200_with_a_null_id_and_the_ref(
    journal, audit_outage, pipeline_stubs, monkeypatch
):
    _query_upstream(monkeypatch)

    response = TestClient(app).post("/query", json={"prompt": "hi"}, headers=_admin_headers())

    assert response.status_code == 200
    body = response.json()
    (entry,) = journal.pending()
    assert body["audit_id"] is None and body["audit_ref"] == entry.write_id
    assert body["response"] == "Hi there!"


def test_query_audit_unavailable_is_503_and_releases_nothing(
    audit_outage, pipeline_stubs, monkeypatch, caplog
):
    _query_upstream(monkeypatch)

    with caplog.at_level(logging.DEBUG):
        response = TestClient(app).post("/query", json={"prompt": "hi"}, headers=_admin_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_DETAIL}
    assert response.headers["Retry-After"] == str(_RETRY_AFTER)  # R5: from the context chain
    assert "Hi there!" not in response.text and _CANARY not in response.text
    assert _CANARY not in caplog.text


def test_query_foreign_session_refusal_unrecordable_is_503_not_403(monkeypatch):
    # PRD-018 R1: the refusal row of /query's own ownership check.
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)
    monkeypatch.setattr(chat_sessions, "owns", lambda *a, **k: False)
    monkeypatch.setattr("app.routers.query.log_query", _raiser(AuditUnavailableError("journal is full")))

    response = TestClient(app).post(
        "/query",
        json={"prompt": "hi", "session_id": "6f0f3c52-7b4c-4a53-9f0c-4d6a2b7f9a11"},
        headers=_admin_headers(),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_DETAIL}
    assert response.headers["Retry-After"] == "1"


# --- /v1 -------------------------------------------------------------------------


@pytest.fixture
def v1(monkeypatch):
    app.dependency_overrides[require_identity] = lambda: _USER
    monkeypatch.setattr("app.routers.v1.call_openrouter", _Upstream("Hello from the model."))
    yield TestClient(app)
    app.dependency_overrides.pop(require_identity, None)


def _data_events(text):
    return [line[len("data: "):] for line in text.splitlines() if line.startswith("data: ")]


def test_v1_journaled_success_sends_the_ref_header_and_ref_id(
    v1, journal, audit_outage, pipeline_stubs
):
    response = v1.post("/v1/chat/completions", json=_V1_BODY)

    assert response.status_code == 200
    (entry,) = journal.pending()
    body = response.json()
    assert body["harness"]["audit_id"] is None and body["harness"]["audit_ref"] == entry.write_id
    assert body["id"] == f"chatcmpl-harness-ref-{entry.write_id}"
    assert response.headers["X-Harness-Audit-Ref"] == entry.write_id
    assert "X-Harness-Audit-Id" not in response.headers


def test_v1_healthy_success_keeps_the_audit_id_header_only(v1, pipeline_stubs, monkeypatch):
    monkeypatch.setattr(audit_logger, "insert_audit_log", lambda entry: 41)

    response = v1.post("/v1/chat/completions", json=_V1_BODY)

    assert response.status_code == 200
    assert response.headers["X-Harness-Audit-Id"] == "41"
    assert "X-Harness-Audit-Ref" not in response.headers  # PRD-018 R4
    assert response.json()["id"] == "chatcmpl-harness-41"
    assert _HEX.match(response.json()["harness"]["audit_ref"])


def test_v1_journaled_stream_ends_normally_with_the_ref_in_every_chunk_id(
    v1, journal, audit_outage, pipeline_stubs
):
    response = v1.post("/v1/chat/completions", json={**_V1_BODY, "stream": True})

    assert response.status_code == 200
    (entry,) = journal.pending()
    events = _data_events(response.text)
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert chunks and {c["id"] for c in chunks} == {f"chatcmpl-harness-ref-{entry.write_id}"}


def test_v1_audit_unavailable_is_503_storage_unavailable(v1, audit_outage, pipeline_stubs):
    response = v1.post("/v1/chat/completions", json=_V1_BODY)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "message": AUDIT_UNAVAILABLE_MESSAGE, "type": "api_error", "param": None,
            "code": "storage_unavailable", "harness": None,
        }
    }
    assert response.headers["Retry-After"] == str(_RETRY_AFTER)
    assert _CANARY not in response.text and "Hello from the model." not in response.text
    assert "not sent" not in response.text  # step 8 runs after the upstream call


def test_v1_audit_unavailable_after_stream_commit_is_one_error_event(v1, audit_outage, pipeline_stubs):
    response = v1.post("/v1/chat/completions", json={**_V1_BODY, "stream": True})

    assert response.status_code == 200
    events = _data_events(response.text)
    assert "[DONE]" not in events and len(events) == 1
    assert json.loads(events[0])["error"]["code"] == "storage_unavailable"
    assert _CANARY not in response.text


def test_v1_tools_request_with_an_unrecordable_row_is_500_internal_error(
    v1, audit_outage, pipeline_stubs, monkeypatch
):
    # PRD-018 6.7 / R2: tools keep PRD-017's 500 internal_error.
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
    monkeypatch.setattr("app.routers.v1.call_openrouter", _Upstream("", _READ, _SHELL))

    response = v1.post("/v1/chat/completions", json={**_V1_BODY, "tools": [_V1_TOOL]})

    assert response.status_code == 500
    assert response.json() == _AUDIT_FAILED
    for leaked in ("call_r", "src/a.py", "rm -rf", _CANARY):
        assert leaked not in response.text


# --- the Retry-After rule --------------------------------------------------------


def test_audit_unavailable_retry_after_walks_the_context_chain():
    try:
        try:
            raise _outage(9)
        except StorageUnavailableError:
            raise AuditUnavailableError("journal is full")
    except AuditUnavailableError as direct:
        assert audit_unavailable_retry_after(direct) == 9

    try:
        try:
            raise _outage(4)
        except StorageUnavailableError:
            try:
                raise OSError("disk")
            except OSError as io:
                raise AuditUnavailableError("write failed") from io
    except AuditUnavailableError as through_oserror:
        assert audit_unavailable_retry_after(through_oserror) == 4

    assert audit_unavailable_retry_after(AuditUnavailableError("no outage")) == 1


# --- db: the journal round trip --------------------------------------------------


def test_a_journaled_tools_request_drains_back_with_its_decisions_linked(faulty_db, journal):
    faulty_db.add(Fault(STREAM_EXPIRED, sql="INSERT INTO AUDIT_LOGS", times=3))

    result = _run_tools(_READ, _SHELL)

    assert result.audit_id is None
    (entry,) = journal.pending()
    assert entry.write_id == result.audit_ref and len(entry.decisions) == 2
    with database.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"] == 0

    assert journal_drainer.drain_once(journal) is journal_drainer.DrainOutcome.DRAINED

    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM audit_logs WHERE write_id = ?", (result.audit_ref,)
        ).fetchone()
        decisions = conn.execute(
            "SELECT audit_id, write_id FROM action_decisions ORDER BY id"
        ).fetchall()
    assert row is not None
    assert [(d["audit_id"], d["write_id"]) for d in decisions] == [
        (row["id"], f"{result.audit_ref}:0"),
        (row["id"], f"{result.audit_ref}:1"),
    ]
    assert journal.pending() == []
