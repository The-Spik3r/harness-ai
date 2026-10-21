"""PRD-015 STORY-001: `/query`'s error bodies and the upstream request body, pinned before `/v1` exists.

**Every assertion in this module is a frozen record of `/query` on `main`
before any PRD-015 code.** It was pinned green on untouched code (PRD-015
Section 6.3, "Characterize before moving"). STORY-010 registers app-wide
exception handlers that must return the OpenAI error shape only under `/v1/`
and delegate to FastAPI's defaults everywhere else (Section 7.5, Risk 4); this
module is what they are checked against, and STORY-010 adds the `/v1` half
here. A later story may add tests. It may not change or delete a pin written
here. A story that believes one must change stops and raises it.

**Bodies are compared as whole dicts,** never field by field, so a handler
cannot add, rename or reshape anything without a failure. The 422 bodies are
FastAPI's `{"detail": [...]}` exactly as returned today, `loc`, `type`,
`input` and `ctx` included.

**The 500 arms raise a fixed message** from the pipeline's own bindings
(`query_pipeline.check_duplicate`, `query_pipeline.redact`), not a real
storage failure: a driver's error text would make `detail` driver-dependent,
which a whole-body pin cannot hold. The real failure stays pinned in
`tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500`.

**The upstream half** drives the real `call_openrouter` over an
`httpx.MockTransport`, so the URL and the JSON body are the ones the client
builds. It is the PRD Section 9.2 T5 baseline: no key outside `model`,
`messages` and `GenerationParams`' four fields.

Only the no-bearer test reaches no storage, so it is the one test that runs
under `-m "not db"`. Per the libSQL dev-server note: mass fixture errors here
mean restart the dev container, not bisect code.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db.database import insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message
from app.models.schemas import QuerySuccessResponse
import app.services.query_pipeline as query_pipeline
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import GenerationParams, OpenRouterError
from app.services.openrouter_client import call_openrouter as _real_call_openrouter
from app.services.pii_redactor import PiiRedactorError
from tests.test_openrouter_client import _API_URL

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
_PROMPT = "hello world"

client = TestClient(app, headers=_AUTH_HEADERS)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _mask_nothing(text, *args):
    return text, []


def _raising(exc: Exception):
    def _raise(*args, **kwargs):
        raise exc

    return _raise


# --- /query error bodies -------------------------------------------------------


def test_query_401_without_bearer_body_is_pinned(monkeypatch):
    # No temp_db on purpose: resolve(None) returns before any lookup, so this
    # is the one test here that runs without storage (AC4).
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = TestClient(app).post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing credential"}


def test_query_401_with_unknown_bearer_body_is_pinned(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    unknown_client = TestClient(app, headers={"Authorization": "Bearer not-a-real-token"})

    response = unknown_client.post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing credential"}


def test_query_403_without_query_submit_body_is_pinned(temp_db, monkeypatch):
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-token"))
    )
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    auditor_client = TestClient(app, headers={"Authorization": "Bearer auditor-token"})

    response = auditor_client.post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 403
    # The literal, not PERMISSION_QUERY_SUBMIT: a renamed constant is a diff here.
    assert response.json() == {"detail": "Permission denied: query:submit"}


def test_query_422_missing_prompt_body_is_pinned(temp_db, monkeypatch):
    # A valid bearer: the auth dependency is resolved before the body errors are
    # reported, so without one a 401 would mask the 422.
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={})

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {"type": "missing", "loc": ["body", "prompt"], "msg": "Field required", "input": {}}
        ]
    }


def test_query_422_malformed_session_id_body_is_pinned(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={"prompt": _PROMPT, "session_id": "not-a-uuid"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", "session_id"],
                "msg": (
                    "Value error, session_id must be a canonical lowercase UUID4 string, "
                    "got 'not-a-uuid'. "
                    "Session ids are minted by the harness and echoed back unchanged; "
                    "omit the field entirely to send without a session."
                ),
                "input": "not-a-uuid",
                "ctx": {"error": {}},
            }
        ]
    }


def test_query_500_duplicate_check_error_body_is_pinned(temp_db, monkeypatch):
    monkeypatch.setattr(
        query_pipeline,
        "check_duplicate",
        _raising(DuplicateCheckError("Duplicate lookup failed: isolation probe")),
    )
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 500
    assert response.json() == {"detail": "Duplicate lookup failed: isolation probe"}


def test_query_500_pii_redactor_error_body_is_pinned(temp_db, monkeypatch):
    monkeypatch.setattr(
        query_pipeline,
        "redact",
        _raising(PiiRedactorError("PII analysis failed: isolation probe")),
    )
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 500
    assert response.json() == {"detail": "PII analysis failed: isolation probe"}


def test_query_502_openrouter_error_body_is_pinned(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)
    monkeypatch.setattr(
        "app.routers.query.call_openrouter",
        _raising(OpenRouterError("OpenRouter request failed: isolation probe")),
    )

    response = client.post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 502
    assert response.json() == {"detail": "OpenRouter request failed: isolation probe"}


# --- The upstream request (PRD Section 9.2 T5 baseline) ----------------------------


def _capturing_transport(seen: list) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hi there!"}, "finish_reason": "stop"}],
                "model": "gpt-4",
                "usage": {"total_tokens": 12},
            },
        )

    return httpx.MockTransport(_handler)


def _upstream_over(transport: httpx.MockTransport):
    """The real call_openrouter, sending through `transport` instead of the network.

    `params` is accepted because run_conversation passes it only when set.
    """

    def _call(messages, model="gpt-4", api_key=None, params=None):
        with httpx.Client(transport=transport) as http_client:
            return _real_call_openrouter(
                messages, model=model, api_key=api_key, params=params, client=http_client
            )

    return _call


def test_query_success_upstream_request_is_pinned(temp_db, monkeypatch):
    seen: list = []
    monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _upstream_over(_capturing_transport(seen))
    )

    response = client.post("/query", json={"prompt": _PROMPT})

    assert response.status_code == 200
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == _API_URL
    body = json.loads(request.content)
    assert list(body) == ["model", "messages"]
    assert body == {"model": "gpt-4", "messages": [{"role": "user", "content": _PROMPT}]}


def test_run_conversation_upstream_request_with_all_four_params_is_pinned(temp_db, monkeypatch):
    seen: list = []
    monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)

    result = query_pipeline.run_conversation(
        identity=Identity(user_id=_AUTH_USER_ID, role="user"),
        messages=[Message("user", _PROMPT)],
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        params=GenerationParams(temperature=0.2, max_tokens=100, top_p=0.9, stop=["END"]),
        call_openrouter=_upstream_over(_capturing_transport(seen)),
    )

    assert isinstance(result, QuerySuccessResponse)
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == _API_URL
    body = json.loads(request.content)
    # T5: no key outside `model`, `messages` and the four GenerationParams
    # fields, in call_openrouter's field order.
    assert list(body) == ["model", "messages", "temperature", "max_tokens", "top_p", "stop"]
    assert body == {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": _PROMPT}],
        "temperature": 0.2,
        "max_tokens": 100,
        "top_p": 0.9,
        "stop": ["END"],
    }
