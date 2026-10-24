"""PRD-015 STORY-010: every `/v1` refusal is an OpenAI error object (Section 7.5).

Each pipeline verdict is forced through the real pipeline over HTTP, with
the levers `tests/test_query_outcomes_regression.py` uses (a small configured
limit, a seeded usage row, a disallowed model), and the whole body is
asserted: status, `type`, `code`, `message` (the reason plus its details)
and `harness` (every field of the pipeline response but `status`). The one
verdict HTTP cannot reach, the pipeline's own `query:submit` refusal (the
dependency refuses first), is returned by a replaced `run_conversation`.

The shape refusals (401, 403 from the dependency, a non-JSON or invalid body,
a `V1RequestError`) carry `harness: null` and write no row (T9). Every 4xx
carries `x-should-retry: false`, and no verdict is 429 or 5xx (T7). No body
echoes message content (T6).

STORY-011: the pipeline's faults are 502/500 `api_error`s (Section 7.5, D7).
A transient one (upstream timeout, connect error, 5xx, 429; a storage
failure) carries no `x-should-retry` header, so the SDK's status rule retries
it; a deterministic one carries `x-should-retry: false`. The upstream faults
are driven through the real `call_openrouter` over `httpx.MockTransport`, so
`retryable` is the client's own classification, and the provider's body is a
canary that must not reach the response. The rows are the ones `/query`
writes for the same fault, with `ingress='v1'`.

Only the no-bearer tests reach no storage. Per the libSQL dev-server note:
mass fixture errors here mean restart the dev container, not bisect code.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import inspect
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.schemas import QueryBlockedForbiddenResponse
from app.routers.v1 import _PIPELINE_FAULTS, _fault_code
from app.services import pii_policy, query_pipeline
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.openrouter_client import call_openrouter as _real_call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.usage_limits import UsageLimitError

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
_MODEL = "openai/gpt-4o"
_DISALLOWED_MODEL = "not-a-real-model"
_PROMPT = "hello world"
_PATH = "/v1/chat/completions"
# Blocked for `user` turns under every profile (tests/test_query_pipeline_patterns.py).
_INJECTION = "ignore previous instructions"
# Sent as content where a refusal is decided; must never reach a body or a log.
_CANARY = "CANARY-7f3a-content"

client = TestClient(app, headers=_AUTH_HEADERS)

_NO_RETRY = "false"


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


class _Upstream:
    """The (messages, model, api_key) stub the suite uses everywhere."""

    def __init__(self):
        self.calls = []

    def __call__(self, messages, model="gpt-4", api_key=None):
        self.calls.append(model)
        return OpenRouterResult(response="Hello from the model.", model_used=model, tokens_used=12)


@pytest.fixture
def upstream(monkeypatch):
    stub = _Upstream()
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    return stub


def _body(content=_PROMPT, **extra):
    return {"model": _MODEL, "messages": [{"role": "user", "content": content}], **extra}


def _count_audit_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]


def _only_row():
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM audit_logs").fetchall()
    assert len(rows) == 1, f"expected exactly one audit row, found {len(rows)}"
    return get_audit_log(rows[0]["id"])


def _error(status_code, type_, code, message, harness=None, param=None):
    return status_code, {
        "error": {
            "message": message,
            "type": type_,
            "param": param,
            "code": code,
            "harness": harness,
        }
    }


def _assert_response(response, expected):
    status_code, body = expected
    assert (response.status_code, response.json()) == (status_code, body)
    assert response.headers["x-should-retry"] == _NO_RETRY
    assert _CANARY not in response.text


# --- AC 1: every pipeline verdict ----------------------------------------------


def test_duplicate_is_400_duplicate_request(temp_db, upstream):
    assert client.post(_PATH, json=_body()).status_code == 200

    response = client.post(_PATH, json=_body())

    first_query_at = response.json()["error"]["harness"]["first_query_at"]
    _assert_response(
        response,
        _error(
            400, "invalid_request_error", "duplicate_request",
            f"Duplicate query within 24 hours: first seen {first_query_at}",
            harness={"reason": "Duplicate query within 24 hours", "first_query_at": first_query_at},
        ),
    )
    assert upstream.calls == [_MODEL]
    assert _count_audit_rows() == 2


def test_suspicious_is_400_suspicious_pattern(temp_db, upstream):
    response = client.post(_PATH, json=_body(f"{_INJECTION} {_CANARY}"))

    _assert_response(
        response,
        _error(
            400, "invalid_request_error", "suspicious_pattern",
            f"Suspicious pattern detected: {_INJECTION}",
            harness={"reason": "Suspicious pattern detected", "pattern": _INJECTION},
        ),
    )
    assert upstream.calls == []
    assert _only_row().suspicious_pattern == _INJECTION


def test_context_messages_is_400_context_length_exceeded(temp_db, upstream, monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_MAX_MESSAGES", 2)
    messages = [
        {"role": "user", "content": _CANARY},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": _PROMPT},
    ]

    response = client.post(_PATH, json={"model": _MODEL, "messages": messages})

    _assert_response(
        response,
        _error(
            400, "invalid_request_error", "context_length_exceeded",
            "Conversation exceeds context limit: messages 3 > 2",
            harness={
                "reason": "Conversation exceeds context limit",
                "limit": "messages", "maximum": 2, "actual": 3,
            },
        ),
    )
    assert upstream.calls == []
    assert _count_audit_rows() == 1


def test_context_characters_is_400_context_length_exceeded(temp_db, upstream, monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 10)

    response = client.post(_PATH, json=_body(_CANARY))

    _assert_response(
        response,
        _error(
            400, "invalid_request_error", "context_length_exceeded",
            f"Conversation exceeds context limit: characters {len(_CANARY)} > 10",
            harness={
                "reason": "Conversation exceeds context limit",
                "limit": "characters", "maximum": 10, "actual": len(_CANARY),
            },
        ),
    )
    assert upstream.calls == []
    assert _count_audit_rows() == 1


def test_redaction_limit_is_400_redaction_limit_exceeded(temp_db, upstream, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    monkeypatch.setattr(settings, "PII_MAX_CHARACTERS_CODE", 10)
    # conftest's _default_pii_policy restores the policies afterwards.
    pii_policy.load()

    response = client.post(_PATH, json=_body(_CANARY))

    _assert_response(
        response,
        _error(
            400, "invalid_request_error", "redaction_limit_exceeded",
            f"Conversation exceeds redaction limit: redaction_characters {len(_CANARY)} > 10",
            harness={
                "reason": "Conversation exceeds redaction limit",
                "limit": "redaction_characters", "maximum": 10, "actual": len(_CANARY),
            },
        ),
    )
    assert upstream.calls == []
    assert _count_audit_rows() == 1


def test_disallowed_model_is_403_model_not_permitted(temp_db, upstream):
    response = client.post(_PATH, json={**_body(), "model": _DISALLOWED_MODEL})

    permission = f"query:model:{_DISALLOWED_MODEL}"
    _assert_response(
        response,
        _error(
            403, "permission_error", "model_not_permitted",
            f"Model not permitted for this role: {permission}",
            harness={"reason": "Model not permitted for this role", "required_permission": permission},
        ),
    )
    assert upstream.calls == []
    assert _only_row().denied_permission == permission


def test_admin_token_is_403_break_glass_not_permitted_with_one_row(temp_db, upstream):
    # AC 2. The bearer is ADMIN_TOKEN itself, so the identity is resolve()'s.
    admin_client = TestClient(app, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"})

    response = admin_client.post(_PATH, json=_body())

    _assert_response(
        response,
        _error(
            403, "permission_error", "break_glass_not_permitted",
            "Break-glass credential not permitted on this ingress: ingress:break_glass",
            harness={
                "reason": "Break-glass credential not permitted on this ingress",
                "required_permission": "ingress:break_glass",
            },
        ),
    )
    assert upstream.calls == []
    row = _only_row()
    assert row.denied_permission == "ingress:break_glass"
    assert row.ingress == "v1"


def _seed_usage(requests_in_window=0, input_tokens=0):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO usage_daily "
            "(user_id, day, requests, window_start, window_requests, input_tokens) "
            "VALUES (?, date('now'), 0, strftime('%s','now') / 60, ?, ?)",
            (_AUTH_USER_ID, requests_in_window, input_tokens),
        )


def _assert_usage_limit(response, limit):
    harness = response.json()["error"]["harness"]
    assert harness["limit"] == limit
    _assert_response(
        response,
        _error(
            403, "permission_error", "usage_limit_exceeded",
            f"Usage limit reached: {limit} {harness['actual']} of {harness['maximum']}; "
            f"resets at {harness['resets_at']}",
            harness={
                "reason": "Usage limit reached",
                "limit": limit,
                "maximum": harness["maximum"],
                "actual": harness["actual"],
                "resets_at": harness["resets_at"],
            },
        ),
    )


def test_token_budget_is_403_usage_limit_exceeded(temp_db, upstream, monkeypatch):
    # Outcome 8's lever: today's counter seeded at the budget.
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", "*=100")
    _seed_usage(input_tokens=100)

    response = client.post(_PATH, json=_body())

    _assert_usage_limit(response, "tokens")
    assert response.json()["error"]["harness"]["maximum"] == 100
    assert upstream.calls == []
    assert _only_row().limit_exceeded == "tokens"


def test_request_rate_is_403_usage_limit_exceeded(temp_db, upstream, monkeypatch):
    # The current minute's window seeded at the rate. A minute boundary between
    # the seed and the request would reset the window; the rate is 1, so a
    # flip makes this request pass with a 200, which the assertion names.
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=1")
    _seed_usage(requests_in_window=1)

    response = client.post(_PATH, json=_body())

    _assert_usage_limit(response, "requests")
    assert response.json()["error"]["harness"]["maximum"] == 1
    assert upstream.calls == []
    assert _only_row().limit_exceeded == "requests"


def test_pipeline_query_submit_refusal_is_403_permission_denied(temp_db, upstream, monkeypatch):
    # The dependency refuses a missing query:submit before the pipeline, so
    # the pipeline's own refusal is returned by a replaced run_conversation.
    def _refuse(*args, **kwargs):
        return QueryBlockedForbiddenResponse(
            reason="Missing required permission", required_permission="query:submit"
        )

    monkeypatch.setattr("app.routers.v1.run_conversation", _refuse)

    response = client.post(_PATH, json=_body())

    _assert_response(
        response,
        _error(
            403, "permission_error", "permission_denied",
            "Missing required permission: query:submit",
            harness={"reason": "Missing required permission", "required_permission": "query:submit"},
        ),
    )


# --- AC 3: shape refusals, no row ------------------------------------------------

_NO_BEARER = _error(
    401, "authentication_error", "invalid_api_key", "Invalid or missing credential"
)


def test_no_bearer_is_401_invalid_api_key(monkeypatch):
    # No temp_db: resolve(None) returns before any lookup.
    monkeypatch.setattr("app.routers.v1.call_openrouter", _Upstream())

    _assert_response(TestClient(app).post(_PATH, json=_body()), _NO_BEARER)


def test_unknown_bearer_is_401_invalid_api_key(temp_db, upstream):
    unknown_client = TestClient(app, headers={"Authorization": "Bearer not-a-real-token"})

    _assert_response(unknown_client.post(_PATH, json=_body()), _NO_BEARER)
    assert _count_audit_rows() == 0


def test_identity_without_query_submit_is_403_permission_denied(temp_db, upstream):
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
    )
    auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})

    _assert_response(
        auditor_client.post(_PATH, json=_body()),
        _error(403, "permission_error", "permission_denied", "Permission denied: query:submit"),
    )
    assert _count_audit_rows() == 0
    assert upstream.calls == []


def test_non_json_body_is_400_invalid_request(temp_db, upstream):
    response = client.post(
        _PATH, content=f"not json {_CANARY}".encode(), headers={"Content-Type": "application/json"}
    )

    _assert_response(
        response, _error(400, "invalid_request_error", "invalid_request", "JSON decode error")
    )
    assert _count_audit_rows() == 0


@pytest.mark.parametrize(
    "body, param, message",
    [
        ({"model": _MODEL}, "messages", "messages: Field required"),
        ({"messages": [{"role": "user", "content": _PROMPT}]}, "model", "model: Field required"),
        ({"model": _MODEL, "messages": _CANARY}, "messages", "messages: Input should be a valid list"),
        ({}, "model", "model: Field required"),
    ],
    ids=["no-messages", "no-model", "messages-not-a-list", "empty"],
)
def test_schema_failure_is_400_invalid_request_with_param(temp_db, upstream, body, param, message):
    response = client.post(_PATH, json=body)

    _assert_response(
        response,
        _error(400, "invalid_request_error", "invalid_request", message, param=param),
    )
    assert _count_audit_rows() == 0
    assert upstream.calls == []


def test_v1_request_error_is_400_with_its_code_and_param(temp_db, upstream):
    response = client.post(_PATH, json=_body(n=2))

    status_code, body = response.status_code, response.json()
    assert status_code == 400
    assert body["error"]["type"] == "invalid_request_error"
    assert body["error"]["code"] == "unsupported_parameter"
    assert body["error"]["param"] == "n"
    assert body["error"]["harness"] is None
    assert response.headers["x-should-retry"] == _NO_RETRY
    assert _count_audit_rows() == 0


# --- AC 4: routing 4xx are the same shape and keep their headers ---------------


def test_wrong_method_is_405_with_allow_header(temp_db):
    response = client.get(_PATH)

    _assert_response(
        response, _error(405, "invalid_request_error", "method_not_allowed", "Method Not Allowed")
    )
    # exc.headers survive the x-should-retry merge.
    assert response.headers["allow"] == "POST"


def test_unknown_v1_path_is_404_not_found(temp_db):
    _assert_response(
        client.post("/v1/nope", json=_body()),
        _error(404, "invalid_request_error", "not_found", "Not Found"),
    )


def test_outside_v1_404_is_fastapi_s():
    response = TestClient(app).get("/nope")

    assert (response.status_code, response.json()) == (404, {"detail": "Not Found"})
    assert "x-should-retry" not in response.headers


# --- T9: shape refusals are logged with who and which rule only ----------------


def test_request_refusal_logs_user_and_code_only(temp_db, upstream, caplog):
    with caplog.at_level(logging.INFO, logger="app.routers.v1"):
        client.post(_PATH, json=_body(_CANARY, n=2))

    records = [r for r in caplog.records if r.name == "app.routers.v1"]
    assert [r.levelno for r in records] == [logging.INFO]
    assert records[0].getMessage() == (
        f"v1 request refused: user_id={_AUTH_USER_ID} code=unsupported_parameter"
    )
    assert _CANARY not in caplog.text


def test_validation_refusal_logs_code_only(temp_db, upstream, caplog):
    with caplog.at_level(logging.INFO, logger="app.routers.v1"):
        client.post(_PATH, json={"model": _MODEL, "messages": _CANARY})

    records = [r for r in caplog.records if r.name == "app.routers.v1"]
    assert [r.getMessage() for r in records] == [
        "v1 request refused: user_id=None code=invalid_request"
    ]
    assert _CANARY not in caplog.text


def test_dependency_refusal_logs_code_only(caplog):
    with caplog.at_level(logging.INFO, logger="app.routers.v1"):
        TestClient(app).post(_PATH, json=_body(_CANARY))

    records = [r for r in caplog.records if r.name == "app.routers.v1"]
    assert [r.getMessage() for r in records] == ["v1 request refused: code=invalid_api_key"]
    assert _CANARY not in caplog.text


# --- STORY-011: pipeline faults (Section 7.5, D7) --------------------------------

_UPSTREAM_PREFIX = "OpenRouter request failed: "
_ANSWER = {
    "choices": [{"message": {"content": "Hello from the model."}, "finish_reason": "stop"}],
    "usage": {"total_tokens": 12},
}


def _upstream_over(handler):
    """The real call_openrouter, sending through a MockTransport over `handler`.

    `params` is accepted because run_conversation passes it only when set.
    """
    transport = httpx.MockTransport(handler)

    def _call(messages, model="gpt-4", api_key=None, params=None):
        with httpx.Client(transport=transport) as http_client:
            return _real_call_openrouter(
                messages, model=model, api_key=api_key, params=params, client=http_client
            )

    return _call


def _status(status_code):
    # The provider's body is the canary: it must never reach `error.message`.
    return lambda request: httpx.Response(status_code, text=_CANARY)


def _transport_failure(exc_type):
    def _handler(request):
        raise exc_type("probe", request=request)

    return _handler


def _json(payload):
    return lambda request: httpx.Response(200, json=payload)


def _no_request(request):
    raise AssertionError("the upstream must not be called")


def _raising(exc):
    def _raise(*args, **kwargs):
        raise exc

    return _raise


def _real_then_raising(real, exc):
    """Real on the first call (the user turn), raising on the second (the response)."""
    calls = []

    def _redact(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return real(*args, **kwargs)
        raise exc

    return _redact


def _rows():
    with get_connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM audit_logs ORDER BY id").fetchall()]
    return [get_audit_log(row_id) for row_id in ids]


def _assert_fault(response, status_code, code, retryable, message=None):
    """The whole body, and the retry signal (D7). `message=None` skips its pin."""
    error = response.json()["error"]
    expected_message = error["message"] if message is None else message
    assert (response.status_code, error) == (
        status_code,
        {
            "message": expected_message,
            "type": "api_error",
            "param": None,
            "code": code,
            "harness": None,
        },
    )
    if retryable:
        assert "x-should-retry" not in response.headers
    else:
        assert response.headers["x-should-retry"] == _NO_RETRY
    assert _CANARY not in response.text
    return error["message"]


def _assert_one_v1_failure_row(message):
    rows = _rows()
    assert len(rows) == 1, f"expected exactly one audit row, found {len(rows)}"
    row = rows[0]
    assert (row.success, row.error_message) == (False, message)
    assert (row.ingress, row.profile, row.streamed) == ("v1", "code", False)
    return row


# --- The router's exception -> code step (no storage) -----------------------------


@pytest.mark.parametrize(
    "exc, code",
    [
        (OpenRouterError("probe", retryable=True), "upstream_unavailable"),
        (OpenRouterError("probe"), "upstream_error"),
        (DuplicateCheckError("probe"), "internal_error"),
        (UsageLimitError("probe"), "internal_error"),
        (PiiRedactorError("probe"), "redaction_failed"),
    ],
    ids=["upstream-retryable", "upstream", "duplicate-lookup", "usage-gate", "redaction"],
)
def test_fault_code_per_pipeline_fault(exc, code):
    assert isinstance(exc, _PIPELINE_FAULTS)
    assert _fault_code(exc) == code


def test_fault_code_refuses_an_unmapped_exception():
    with pytest.raises(TypeError):
        _fault_code(ValueError("probe"))


# --- AC 1, AC 4: upstream faults through the real client -------------------------


@pytest.mark.parametrize(
    "handler",
    [
        _status(503),
        _status(429),
        _transport_failure(httpx.ConnectError),
        _transport_failure(httpx.ReadTimeout),
    ],
    ids=["5xx", "429", "connect", "timeout"],
)
def test_retryable_upstream_fault_is_502_upstream_unavailable(temp_db, monkeypatch, handler):
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(handler))

    response = client.post(_PATH, json=_body())

    # httpx's own text (status line and URL) follows the prefix; not pinned.
    message = _assert_fault(response, 502, "upstream_unavailable", retryable=True)
    assert message.startswith(_UPSTREAM_PREFIX)
    assert _assert_one_v1_failure_row(message).model_used == _MODEL


@pytest.mark.parametrize(
    "handler, message",
    [
        (_status(400), None),
        (
            _json({"unexpected": _CANARY}),
            "OpenRouter returned an unexpected response shape: 'choices'",
        ),
        (
            _json(
                {
                    "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 1},
                }
            ),
            "OpenRouter returned no text content (finish_reason=stop)",
        ),
    ],
    ids=["4xx", "malformed", "null-content"],
)
def test_deterministic_upstream_fault_is_502_upstream_error(temp_db, monkeypatch, handler, message):
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(handler))

    response = client.post(_PATH, json=_body())

    sent = _assert_fault(response, 502, "upstream_error", retryable=False, message=message)
    if message is None:
        assert sent.startswith(_UPSTREAM_PREFIX)
    _assert_one_v1_failure_row(sent)


def test_missing_upstream_key_is_502_upstream_error(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(_no_request))

    response = client.post(_PATH, json=_body())

    message = _assert_fault(
        response, 502, "upstream_error", retryable=False,
        message="OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY",
    )
    _assert_one_v1_failure_row(message)


# --- AC 2: storage and redaction faults ------------------------------------------


@pytest.mark.parametrize(
    "binding, exc",
    [
        ("check_duplicate", DuplicateCheckError("Duplicate lookup failed: probe")),
        ("admit", UsageLimitError("Usage admission failed: probe")),
    ],
    ids=["duplicate-lookup", "usage-gate"],
)
def test_storage_fault_is_500_internal_error_retryable(temp_db, upstream, monkeypatch, binding, exc):
    monkeypatch.setattr(query_pipeline, binding, _raising(exc))

    response = client.post(_PATH, json=_body())

    _assert_fault(response, 500, "internal_error", retryable=True, message=str(exc))
    # Fails closed before any row and before the upstream, as on /query.
    assert _count_audit_rows() == 0
    assert upstream.calls == []


def test_input_redaction_fault_is_500_redaction_failed(temp_db, upstream, monkeypatch):
    # `code` redacts through redact_for_policy, not `redact` (query_pipeline._redact).
    monkeypatch.setattr(
        query_pipeline, "redact_for_policy", _raising(PiiRedactorError("PII analysis failed: probe"))
    )

    response = client.post(_PATH, json=_body())

    _assert_fault(
        response, 500, "redaction_failed", retryable=False, message="PII analysis failed: probe"
    )
    _assert_one_v1_failure_row("PII analysis failed: probe")
    assert upstream.calls == []


def test_output_redaction_fault_is_500_redaction_failed(temp_db, upstream, monkeypatch):
    # `code` does not redact output by default (PRD-012 D1); conftest's
    # _default_pii_policy restores the policies afterwards.
    monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", True)
    pii_policy.load()
    monkeypatch.setattr(
        query_pipeline,
        "redact_for_policy",
        _real_then_raising(
            query_pipeline.redact_for_policy, PiiRedactorError("PII analysis failed: probe on output")
        ),
    )

    response = client.post(_PATH, json=_body())

    _assert_fault(
        response, 500, "redaction_failed", retryable=False,
        message="PII analysis failed: probe on output",
    )
    assert upstream.calls == [_MODEL]
    _assert_one_v1_failure_row("PII analysis failed: probe on output")


# --- AC 3: the rows are /query's for the same fault ------------------------------


def _both_upstreams(monkeypatch, call):
    monkeypatch.setattr("app.routers.query.call_openrouter", call)
    monkeypatch.setattr("app.routers.v1.call_openrouter", call)


def _fault_upstream_5xx(monkeypatch):
    _both_upstreams(monkeypatch, _upstream_over(_status(503)))


def _fault_upstream_4xx(monkeypatch):
    _both_upstreams(monkeypatch, _upstream_over(_status(400)))


def _fault_duplicate_lookup(monkeypatch):
    _both_upstreams(monkeypatch, _upstream_over(_no_request))
    monkeypatch.setattr(
        query_pipeline, "check_duplicate", _raising(DuplicateCheckError("Duplicate lookup failed: probe"))
    )


def _fault_usage_gate(monkeypatch):
    _both_upstreams(monkeypatch, _upstream_over(_no_request))
    monkeypatch.setattr(
        query_pipeline, "admit", _raising(UsageLimitError("Usage admission failed: probe"))
    )


def _fault_input_redaction(monkeypatch):
    # `chat` (/query) redacts through `redact`, `code` (/v1) through redact_for_policy.
    _both_upstreams(monkeypatch, _upstream_over(_no_request))
    exc = PiiRedactorError("PII analysis failed: probe")
    monkeypatch.setattr(query_pipeline, "redact", _raising(exc))
    monkeypatch.setattr(query_pipeline, "redact_for_policy", _raising(exc))


def _fault_output_redaction(monkeypatch):
    # `chat` always redacts output; `code` only with the switch (PRD-012 D1).
    _both_upstreams(monkeypatch, _upstream_over(lambda request: httpx.Response(200, json=_ANSWER)))
    monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", True)
    pii_policy.load()
    exc = PiiRedactorError("PII analysis failed: probe on output")
    monkeypatch.setattr(query_pipeline, "redact", _real_then_raising(query_pipeline.redact, exc))
    monkeypatch.setattr(
        query_pipeline, "redact_for_policy", _real_then_raising(query_pipeline.redact_for_policy, exc)
    )


@pytest.mark.parametrize(
    "install, expected_rows",
    [
        (_fault_upstream_5xx, 1),
        (_fault_upstream_4xx, 1),
        (_fault_duplicate_lookup, 0),
        (_fault_usage_gate, 0),
        (_fault_input_redaction, 1),
        (_fault_output_redaction, 1),
    ],
    ids=["upstream-5xx", "upstream-4xx", "duplicate-lookup", "usage-gate",
         "input-redaction", "output-redaction"],
)
def test_fault_rows_match_query_s(temp_db, monkeypatch, install, expected_rows):
    install(monkeypatch)

    query_response = client.post("/query", json={"prompt": _PROMPT})
    query_rows = _rows()
    v1_response = client.post(_PATH, json=_body())
    v1_rows = _rows()[len(query_rows):]

    # The same status on both doors: 502 upstream, 500 storage and redaction.
    assert v1_response.status_code == query_response.status_code
    assert (len(query_rows), len(v1_rows)) == (expected_rows, expected_rows)
    # The fault's own fields only: the pii_* fields differ by profile (PRD-012).
    def _fault_fields(row):
        return row.success, row.error_message, row.model_used is not None

    assert [_fault_fields(row) for row in v1_rows] == [_fault_fields(row) for row in query_rows]
    assert all(row.success is False for row in v1_rows)
    assert [row.ingress for row in query_rows] == ["query"] * expected_rows
    assert [(row.ingress, row.profile, row.streamed) for row in v1_rows] == [
        ("v1", "code", False)
    ] * expected_rows


# --- AC 5: a retried transient failure is answered, not held as a duplicate ------


def test_retryable_upstream_failure_then_retry_is_answered_not_duplicate(temp_db, monkeypatch):
    answers = iter([httpx.Response(503, text=_CANARY), httpx.Response(200, json=_ANSWER)])
    monkeypatch.setattr(
        "app.routers.v1.call_openrouter", _upstream_over(lambda request: next(answers))
    )

    failed = client.post(_PATH, json=_body())
    retried = client.post(_PATH, json=_body())

    _assert_fault(failed, 502, "upstream_unavailable", retryable=True)
    # PRD-009 Section 6.3: a success=False row never matches the duplicate lookup.
    assert retried.status_code == 200
    assert retried.json()["choices"][0]["message"]["content"] == "Hello from the model."
    rows = _rows()
    assert [(row.success, row.ingress) for row in rows] == [(False, "v1"), (True, "v1")]
    assert rows[0].dedup_key == rows[1].dedup_key
    assert rows[1].was_duplicate_blocked is False


# --- ChatSessionError is unreachable: /v1 passes no session ----------------------


def test_run_conversation_gets_no_session(temp_db, upstream, monkeypatch):
    real = query_pipeline.run_conversation
    bound = []

    def _spy(*args, **kwargs):
        bound.append(inspect.signature(real).bind(*args, **kwargs).arguments)
        return real(*args, **kwargs)

    monkeypatch.setattr("app.routers.v1.run_conversation", _spy)

    assert client.post(_PATH, json=_body()).status_code == 200
    assert len(bound) == 1
    assert bound[0].get("session_id") is None


# --- Faults are logged with who and which fault only ----------------------------


def test_fault_logs_user_and_code_only(temp_db, upstream, monkeypatch, caplog):
    # The body carries the exception's text, as /query's `detail` does
    # (parity, design decision 3); the log line never does.
    exc = DuplicateCheckError(f"Duplicate lookup failed: {_CANARY}")
    monkeypatch.setattr(query_pipeline, "check_duplicate", _raising(exc))

    with caplog.at_level(logging.INFO, logger="app.routers.v1"):
        response = client.post(_PATH, json=_body())

    assert response.status_code == 500
    assert response.json()["error"]["message"] == str(exc)
    records = [r for r in caplog.records if r.name == "app.routers.v1"]
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (logging.WARNING, f"v1 request failed: user_id={_AUTH_USER_ID} code=internal_error")
    ]
    assert _CANARY not in caplog.text
