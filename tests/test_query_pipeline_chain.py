"""PRD-022 STORY-012: steps 6 and 7 through `chain.run` for buffered calls.

    AC1  no chain: the PRD-020 path (one call, rows attempt 1, chain columns NULL)
    AC2  a 503 on the primary falls back: two rows, one request id, failure row first
    AC3  the fallback is redacted from the raw text for ITS route; limits skip; redactor fails closed
    AC4  nothing attempted: one `success=0` row with the skips; `/query` 502; BYOK one attempt
    AC5  admit once, charge once; `model_used` response vs audit; the success row lists skips

The legacy byte-for-byte replay is `tests/test_prd020_legacy_fixtures.py`; the runner's own
rules are `tests/test_chain_runner.py`. Here the pipeline is driven with injected
`call_openrouter` stubs, so no network is involved.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import re

import pytest
from fastapi.testclient import TestClient

import app.routers.query as query_router
import app.routers.v1 as v1_router
import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message
from app.models.schemas import QueryBlockedContextLimitResponse, QuerySuccessResponse
from app.services import authz, pii_policy
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.upstream import chain as chain_mod
from app.services.upstream import health
from tests._providers import chains_file, provider_file  # noqa: F401  (fixtures)
from tests.test_audit_characterization import (  # noqa: F401
    _audit_rows_since,
    _last_audit_id,
    _shipped_settings,  # autouse: shipped settings, redact stubbed, no model loaded
)

_EMAIL = "ana.lopez@example.com"
_MASK = "[EMAIL]"
_USER_ID = "juan@empresa.com"
_TOKEN = "test-user-token"
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}
_ADMIN = Identity("root", "admin")
_USER = Identity("juan", "user")

# local: internal, input unmasked (relaxed). remote, other: external. local2: internal, standard.
_REGISTRY = """
version: 1
default_model: remote/m
providers:
  - name: remote
    label: Remote
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    byok: true
    models:
      - id: remote/m
        upstream: up-remote
  - name: other
    label: Other
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    models:
      - id: other/m
        upstream: up-other
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    trust: internal
    pii: relaxed
    models:
      - id: local/m
        upstream: up-local
  - name: local2
    label: Local2
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    trust: internal
    models:
      - id: local2/m
        upstream: up-local2
"""

_CHAINS = """
version: 1
chains:
  - match: {model: remote/m}
    candidates:
      - {model: remote/m}
      - {model: other/m}
  - match: {model: local/m}
    candidates:
      - {model: local/m}
      - {model: remote/m, allow_lower_trust: true}
  - match: {model: local2/m}
    candidates:
      - {model: local2/m}
      - {model: local/m}
"""


@pytest.fixture(autouse=True)
def _health():
    health.reset()
    yield
    health.reset()


@pytest.fixture(autouse=True)
def _email_masker(monkeypatch, _shipped_settings):
    def mask(text, *args):
        masked = re.sub(r"[\w.]+@[\w.]+\.\w+", _MASK, text)
        return masked, ([] if masked == text else ["EMAIL_ADDRESS"])

    monkeypatch.setattr(query_pipeline, "redact", mask)
    monkeypatch.setattr(query_pipeline, "redact_for_policy", lambda t, policy: mask(t))


@pytest.fixture
def temp_db(temp_db):
    insert_user(User(user_id=_USER_ID, role="user", token_hash=hash_token(_TOKEN)))
    return temp_db


@pytest.fixture
def chained(provider_file, chains_file):  # noqa: F811
    provider_file(_REGISTRY)
    chains_file(_CHAINS)


class Upstream:
    """An injected `call_openrouter`: `script[model]` is an error to raise or a reply text."""

    def __init__(self, script=None, *, on_call=None):
        self.script = script or {}
        self.on_call = on_call
        self.calls = []  # (model, api_key, kwargs, texts)

    def __call__(self, messages, model, api_key=None, **kw):
        self.calls.append((model, api_key, kw, [m.content for m in messages]))
        if self.on_call is not None:
            self.on_call(len(self.calls))
        outcome = self.script.get(model, f"answer from {model}")
        if isinstance(outcome, BaseException):
            raise outcome
        return OpenRouterResult(response=outcome, model_used=model, tokens_used=7)

    @property
    def models(self):
        return [c[0] for c in self.calls]


def _503():
    return OpenRouterError("upstream unavailable", upstream_status=503, retryable=True)


def _run(messages, upstream, *, model="remote/m", identity=_USER, api_key=None, profile=None, **kw):
    return query_pipeline.run_conversation(
        identity, list(messages), "pytest/chain", model, api_key,
        call_openrouter=upstream, ingress="query", profile=profile, **kw,
    )


def _rows(before):
    return _audit_rows_since(before)


def _small_code_limit(monkeypatch, value=5):
    monkeypatch.setattr(settings, "PII_MAX_CHARACTERS_CODE", value)
    pii_policy.load()  # the code policy captures the limit at load time


# --- AC1: no chain is the PRD-020 path ----------------------------------------------


def test_no_chain_is_prd020_path(temp_db, provider_file, monkeypatch):  # noqa: F811
    provider_file(_REGISTRY)  # a registry, but no PROVIDER_CHAINS_FILE: single-candidate chains

    def boom(*a, **k):
        raise AssertionError("chain.run must not be called without a chain")

    monkeypatch.setattr(chain_mod, "run", boom)
    monkeypatch.setattr(health, "sync", boom)
    before = _last_audit_id()
    upstream = Upstream()

    result = _run([Message("user", "hello")], upstream)

    assert isinstance(result, QuerySuccessResponse)
    assert upstream.models == ["remote/m"] and upstream.calls[0][2] == {}  # no `timeout=`
    (row,) = _rows(before)
    assert (row.attempt, row.route_model) == (1, "remote/m")
    assert row.fallback_reason is None and row.skipped_providers is None


def test_no_chain_failure_row_is_attempt_one(temp_db, provider_file):  # noqa: F811
    provider_file(_REGISTRY)
    before = _last_audit_id()
    with pytest.raises(OpenRouterError):
        _run([Message("user", "hello")], Upstream({"remote/m": _503()}))
    (row,) = _rows(before)
    assert (row.attempt, row.route_model, row.success) == (1, "remote/m", False)
    assert row.fallback_reason is None and row.skipped_providers is None


# --- AC2: a 503 falls back ---------------------------------------------------------


def test_503_then_fallback_two_rows(temp_db, chained):
    before = _last_audit_id()
    upstream = Upstream({"remote/m": _503()})

    result = _run([Message("user", "hello")], upstream)

    assert upstream.models == ["remote/m", "other/m"]
    assert isinstance(result, QuerySuccessResponse) and result.model_used == "other/m"
    failed, answered = _rows(before)
    assert failed.request_id == answered.request_id and failed.request_id
    assert (failed.attempt, failed.route_model, failed.success) == (1, "remote/m", False)
    assert failed.provider == "remote" and failed.error_message == "upstream unavailable"
    assert (answered.attempt, answered.route_model, answered.success) == (2, "other/m", True)
    assert answered.provider == "other" and answered.upstream_model == "up-other"
    assert answered.fallback_reason == "status_503"


def test_failure_row_written_before_next_attempt(temp_db, chained):
    before = _last_audit_id()
    seen = {}

    def second_call_sees_the_failure_row(n):
        if n == 2:
            seen["rows"] = [(r.attempt, r.success) for r in _rows(before)]

    _run(
        [Message("user", "hello")],
        Upstream({"remote/m": _503()}, on_call=second_call_sees_the_failure_row),
    )
    assert seen["rows"] == [(1, False)]


def test_model_used_response_vs_audit(temp_db, chained):
    before = _last_audit_id()
    result = _run([Message("user", "hello")], Upstream({"remote/m": _503()}))
    _, answered = _rows(before)
    assert result.model_used == "other/m"  # what answered (D17)
    assert answered.model_used == "remote/m"  # what was asked; `route_model` says who answered


def test_a_deterministic_error_does_not_fall_back(temp_db, chained):
    upstream = Upstream({"remote/m": OpenRouterError("bad request", upstream_status=400)})
    before = _last_audit_id()
    with pytest.raises(OpenRouterError):
        _run([Message("user", "hello")], upstream)
    assert upstream.models == ["remote/m"]
    (row,) = _rows(before)
    assert (row.attempt, row.success) == (1, False)


def test_every_attempt_failing_leaves_one_row_each_and_no_exhaustion_row(temp_db, chained):
    before = _last_audit_id()
    with pytest.raises(OpenRouterError) as err:
        _run([Message("user", "hello")], Upstream({"remote/m": _503(), "other/m": _503()}))
    assert str(err.value) == "all providers unavailable"
    rows = _rows(before)
    assert [(r.attempt, r.route_model, r.success) for r in rows] == [
        (1, "remote/m", False),
        (2, "other/m", False),
    ]


def test_a_chained_attempt_gets_a_timeout_and_the_deadline_caps_it(temp_db, chained, monkeypatch):
    upstream = Upstream()
    _run([Message("user", "hello")], upstream)
    # A loaded chain bounds every attempt, at least by the provider's own timeout.
    assert 0 < upstream.calls[0][2]["timeout"] <= 120.0
    monkeypatch.setattr(settings, "PROVIDER_CHAIN_DEADLINE_SECONDS", 60.0)
    from app.services.upstream import chain_config

    chain_config.load()
    upstream = Upstream()
    _run([Message("user", "other prompt")], upstream)
    assert 0 < upstream.calls[0][2]["timeout"] <= 60.0  # the chain deadline caps it


# --- AC3: redaction per route -------------------------------------------------------


def test_fallback_redacts_from_raw_for_the_receiving_route(temp_db, chained):
    before = _last_audit_id()
    upstream = Upstream({"local/m": _503()})

    _run([Message("user", f"mail {_EMAIL}")], upstream, model="local/m", identity=_ADMIN)

    (first_model, _, _, first_texts), (second_model, _, _, second_texts) = upstream.calls
    assert first_model == "local/m" and first_texts == [f"mail {_EMAIL}"]  # relaxed: as received
    assert second_model == "remote/m" and second_texts == [f"mail {_MASK}"]  # external: standard
    failed, answered = _rows(before)
    assert failed.pii_input_relaxed is True and failed.pii_detected_input is False
    assert answered.pii_input_relaxed is False and answered.pii_detected_input is True
    assert answered.fallback_reason == "status_503;trust_lowered"


def test_candidate_over_code_limit_is_skipped(temp_db, chained, monkeypatch):
    _small_code_limit(monkeypatch)
    # local2 is standard (limited); local is relaxed (unlimited). Over the limit, the
    # primary is skipped as `redaction_limit` and the relaxed fallback answers.
    before = _last_audit_id()
    upstream = Upstream()
    result = _run(
        [Message("user", "y" * 50)], upstream, model="local2/m", profile="code", identity=_ADMIN
    )
    assert isinstance(result, QuerySuccessResponse) and result.model_used == "local/m"
    assert upstream.models == ["local/m"]
    (row,) = _rows(before)
    assert (row.attempt, row.route_model) == (1, "local/m")  # a skip consumes no number (D10)
    assert row.skipped_providers == "local2:redaction_limit"


def test_chained_primary_over_limit_with_no_attempt_keeps_limit_verdict(
    temp_db, chained, monkeypatch
):
    # Orchestrator note 3.2: a size limit is deterministic, so no "all providers unavailable".
    _small_code_limit(monkeypatch)
    before = _last_audit_id()
    upstream = Upstream()

    # local2 -> local would answer, so chain local2 -> remote instead: remote is limited too.
    result = _run(
        [Message("user", "y" * 50)], upstream, model="remote/m", profile="code", identity=_ADMIN
    )

    assert isinstance(result, QueryBlockedContextLimitResponse)
    assert (result.limit, result.maximum, result.actual) == ("redaction_characters", 5, 50)
    assert upstream.calls == []
    (row,) = _rows(before)
    assert row.success is False
    assert row.error_message == "redaction limit: characters 50 > 5"
    assert (row.attempt, row.route_model) == (None, None) and row.provider == "remote"


def test_chained_primary_over_limit_but_relaxed_fallback_answers(temp_db, chained, monkeypatch):
    _small_code_limit(monkeypatch)
    before = _last_audit_id()
    upstream = Upstream()

    result = _run(
        [Message("user", "z" * 50)], upstream, model="local2/m", profile="code", identity=_ADMIN
    )

    assert isinstance(result, QuerySuccessResponse)
    assert upstream.models == ["local/m"] and upstream.calls[0][3] == ["z" * 50]
    (row,) = _rows(before)
    assert row.success is True and row.pii_input_relaxed is True
    assert row.skipped_providers == "local2:redaction_limit"


def test_redaction_error_on_candidate_fails_closed(temp_db, chained, monkeypatch):
    def redactor(text, *args):
        raise PiiRedactorError("PII analysis failed: boom")

    # local (relaxed) never redacts, so its attempt runs; the fallback remote does, and raises.
    monkeypatch.setattr(query_pipeline, "redact", redactor)
    before = _last_audit_id()
    upstream = Upstream({"local/m": _503()})

    with pytest.raises(PiiRedactorError):
        _run([Message("user", "hello")], upstream, model="local/m", identity=_ADMIN)

    assert upstream.models == ["local/m"]  # the fallback was never called
    failed, refused = _rows(before)
    assert (failed.attempt, failed.success) == (1, False)
    assert refused.success is False and refused.error_message == "PII analysis failed: boom"
    assert (refused.attempt, refused.route_model) == (None, None)


# --- AC4: nothing attempted ---------------------------------------------------------


def _open_all():
    for name in ("remote", "other"):
        health.breaker(name).force_open(60.0)


def test_exhausted_without_attempt_writes_one_row(temp_db, chained):
    _open_all()
    before = _last_audit_id()
    upstream = Upstream()

    with pytest.raises(OpenRouterError) as err:
        _run([Message("user", "hello")], upstream)

    assert str(err.value) == "all providers unavailable" and upstream.calls == []
    (row,) = _rows(before)
    assert row.success is False and row.error_message == "all providers unavailable"
    assert (row.attempt, row.route_model, row.provider) == (None, "remote/m", "remote")
    assert row.skipped_providers == "remote:open,other:open"


def test_query_route_maps_exhausted_to_502(temp_db, chained, monkeypatch):
    _open_all()
    monkeypatch.setattr(query_router, "call_openrouter", Upstream())
    response = TestClient(app, headers=_HEADERS).post(
        "/query", json={"prompt": "hello", "model": "remote/m"}
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "all providers unavailable"


def test_v1_route_maps_exhausted_to_upstream_unavailable(temp_db, chained, monkeypatch):
    _open_all()
    monkeypatch.setattr(v1_router, "call_openrouter", Upstream())
    response = TestClient(app, headers=_HEADERS).post(
        "/v1/chat/completions",
        json={"model": "remote/m", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "upstream_unavailable"


def test_query_route_falls_back_end_to_end(temp_db, chained, monkeypatch):
    upstream = Upstream({"remote/m": _503()})
    monkeypatch.setattr(query_router, "call_openrouter", upstream)
    response = TestClient(app, headers=_HEADERS).post(
        "/query", json={"prompt": "hello", "model": "remote/m"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["model_used"] == "other/m"
    request_ids = {
        get_audit_log(r["id"]).request_id
        for r in get_connection().execute("SELECT id FROM audit_logs").fetchall()
    }
    assert len(request_ids) == 1  # two rows, one request id


def test_byok_single_attempt_key_reaches_only_the_primary(temp_db, chained):
    before = _last_audit_id()
    upstream = Upstream({"remote/m": _503()})

    with pytest.raises(OpenRouterError):
        _run([Message("user", "hello")], upstream, identity=_ADMIN, api_key="sk-caller")

    assert upstream.calls[0][:2] == ("remote/m", "sk-caller") and len(upstream.calls) == 1
    rows = _rows(before)
    assert [(r.attempt, r.success) for r in rows] == [(1, False)]


def test_a_forbidden_fallback_is_skipped(temp_db, chained, monkeypatch):
    real = authz.authorize_route

    def deny_other(identity, model):
        if model == "other/m":
            raise authz.PermissionDenied(f"query:model:{model}")
        return real(identity, model)

    monkeypatch.setattr(query_pipeline, "authorize_route", deny_other)
    before = _last_audit_id()
    with pytest.raises(OpenRouterError):
        _run([Message("user", "hello")], Upstream({"remote/m": _503()}))
    rows = _rows(before)
    assert [(r.attempt, r.success) for r in rows] == [(1, False)]  # no second call, no new row


# --- AC5: usage, model_used, skips ---------------------------------------------------


def test_admit_and_charge_once(temp_db, chained, monkeypatch):
    admits, charges = [], []
    real_admit, real_charge = query_pipeline.admit, query_pipeline.charge

    def spy_admit(identity, charges_budget):
        admits.append(identity.user_id)
        return real_admit(identity, charges_budget=charges_budget)

    def spy_charge(user_id, day, i, o, total):
        charges.append(total)
        return real_charge(user_id, day, i, o, total)

    monkeypatch.setattr(query_pipeline, "admit", spy_admit)
    monkeypatch.setattr(query_pipeline, "charge", spy_charge)

    _run([Message("user", "hello")], Upstream({"remote/m": _503()}))

    assert len(admits) == 1 and charges == [7]  # the answering attempt's usage, once


def test_resend_after_all_failed_is_answered(temp_db, chained):
    # A failed row is never a prior query (PRD-009 6.3): the same request is answered next time.
    with pytest.raises(OpenRouterError):
        _run([Message("user", "same")], Upstream({"remote/m": _503(), "other/m": _503()}))
    result = _run([Message("user", "same")], Upstream())
    assert isinstance(result, QuerySuccessResponse) and result.model_used == "remote/m"


def test_success_row_lists_skips(temp_db, chained):
    health.breaker("remote").force_open(60.0)
    before = _last_audit_id()

    result = _run([Message("user", "hello")], Upstream())

    assert result.model_used == "other/m"
    (row,) = _rows(before)
    assert (row.attempt, row.route_model) == (1, "other/m")
    assert row.skipped_providers == "remote:open" and row.fallback_reason is None


def test_pipeline_counts_nothing_itself(temp_db, chained, monkeypatch):
    # `chain.run` records health and counters; the pipeline adds none (no double counting).
    syncs = []
    real_sync = health.sync
    monkeypatch.setattr(health, "sync", lambda names: (syncs.append(set(names)), real_sync(names)))

    source = open(query_pipeline.__file__, encoding="utf-8").read()
    assert "health.record" not in source and "count_skipped" not in source
    assert "count_fallback_answer" not in source

    _run([Message("user", "hello")], Upstream({"remote/m": _503()}))

    assert len(syncs) == 1
    counters = health.providers_status([]).counters
    assert counters.fallback_answers == 1 and sum(counters.attempts_failed.values()) == 1


# --- Realtime stays single-candidate --------------------------------------------------


def test_streamed_request_on_chained_model_walks_the_chain(temp_db, chained, monkeypatch):
    # PRD-022 STORY-014 (6.6) supersedes STORY-012's interim rule (`..._stays_single_candidate`):
    # a streamed request on a chained model goes through `chain.run`, and a candidate that does
    # not declare `streaming` (this registry's) is skipped `capability`. The streaming chain
    # cases live in `tests/test_query_pipeline_chain_stream.py`.
    from app.services.delivery import Visibility

    class _Sink:
        def stage(self, *a): ...
        def phase(self, *a): ...
        def content(self, *a): ...
        def reasoning(self, *a): ...
        def committed(self, *a): ...

    monkeypatch.setattr(
        Visibility,
        "compute",
        classmethod(
            lambda cls, **kw: Visibility(realtime=False, reasoning=False, upstream_streamed=True)
        ),
    )
    ran = []
    real_run = chain_mod.run
    monkeypatch.setattr(chain_mod, "run", lambda *a, **k: (ran.append(1), real_run(*a, **k))[1])
    streamed = []

    def stream(messages, model, api_key=None, **kw):
        streamed.append(model)
        yield from ()

    before = _last_audit_id()
    with pytest.raises(ChainExhausted) as excinfo:
        _run([Message("user", "hello")], Upstream(), sink=_Sink(), stream_upstream=stream)

    # PRD-022 STORY-014: the chain ran and skipped both candidates; nothing was streamed.
    assert ran == [1] and streamed == []
    assert ("remote", "capability") in excinfo.value.skipped
    (row,) = _rows(before)
    assert row.attempt is None and row.success is False


# --- STORY-013: /v1 response surfaces -----------------------------------------------

from app.services.upstream.types import ChainExhausted  # noqa: E402

_V1_BODY = {"model": "remote/m", "messages": [{"role": "user", "content": "hello"}]}


def _v1(monkeypatch, upstream, body=None):
    monkeypatch.setattr(v1_router, "call_openrouter", upstream)
    return TestClient(app, headers=_HEADERS).post("/v1/chat/completions", json=body or _V1_BODY)


def test_v1_answer_without_fallback_names_provider_and_one_attempt(temp_db, chained, monkeypatch):
    response = _v1(monkeypatch, Upstream())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "remote/m"
    assert (body["harness"]["provider"], body["harness"]["attempts"]) == ("remote", 1)
    assert response.headers["X-Harness-Provider"] == "remote"


def test_v1_fallback_answer_names_the_answering_model_provider_and_attempts(
    temp_db, chained, monkeypatch
):
    response = _v1(monkeypatch, Upstream({"remote/m": _503()}))
    body = response.json()
    assert response.status_code == 200, response.text
    assert body["model"] == "other/m"  # PRD-022 D17: the answering id, not the requested one
    assert (body["harness"]["provider"], body["harness"]["attempts"]) == ("other", 2)
    assert response.headers["X-Harness-Provider"] == "other"


def test_v1_buffered_sse_carries_the_answering_model(temp_db, chained, monkeypatch):
    # PRD-022 F10 (accepted deviation): headers go out at commit, before the answer
    # exists, so a buffered stream has the answering `model` only.
    response = _v1(monkeypatch, Upstream({"remote/m": _503()}), {**_V1_BODY, "stream": True})
    assert response.status_code == 200, response.text
    assert "X-Harness-Provider" not in response.headers
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert chunks and {c["model"] for c in chunks} == {"other/m"}


def test_v1_total_outage_is_retryable_with_retry_after(temp_db, chained, monkeypatch):
    _open_all()
    response = _v1(monkeypatch, Upstream())
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unavailable"
    assert response.headers["retry-after"].isdigit()
    assert "x-should-retry" not in response.headers


def _raising(exc):
    def run(*a, **k):
        raise exc

    return run


def test_v1_exhaustion_without_retry_after_has_no_header(temp_db, chained, monkeypatch):
    monkeypatch.setattr(query_pipeline.chain, "run", _raising(ChainExhausted([("remote", "open")])))
    response = _v1(monkeypatch, Upstream())
    assert response.json()["error"]["code"] == "upstream_unavailable"
    assert "retry-after" not in response.headers


def test_v1_capability_only_exhaustion_is_not_retryable_and_names_the_reason(
    temp_db, chained, monkeypatch
):
    monkeypatch.setattr(
        query_pipeline.chain, "run", _raising(ChainExhausted([("other", "capability")]))
    )
    response = _v1(monkeypatch, Upstream())
    error = response.json()["error"]
    assert response.status_code == 502 and error["code"] == "upstream_error"
    assert response.headers["x-should-retry"] == "false"
    assert "capability" in error["message"] and "other" not in error["message"]


def test_v1_mixed_skips_stay_unavailable(temp_db, chained, monkeypatch):
    monkeypatch.setattr(
        query_pipeline.chain,
        "run",
        _raising(ChainExhausted([("other", "capability"), ("remote", "open")], retry_after_seconds=9)),
    )
    response = _v1(monkeypatch, Upstream())
    assert response.json()["error"]["code"] == "upstream_unavailable"
    assert response.headers["retry-after"] == "9"


def test_v1_last_attempt_4xx_keeps_upstream_error(temp_db, chained, monkeypatch):
    upstream = Upstream({"remote/m": _503(), "other/m": OpenRouterError("bad", upstream_status=400)})
    response = _v1(monkeypatch, upstream)
    assert response.json()["error"]["code"] == "upstream_error"
    assert response.headers["x-should-retry"] == "false"


def test_v1_exhaustion_never_leaks_the_upstream_text(temp_db, chained, monkeypatch):
    canary = "sk-or-v1-CANARY"
    failure = OpenRouterError(f"boom {canary}", upstream_status=503, retryable=True, provider="other")
    upstream = Upstream({"remote/m": failure, "other/m": failure})
    response = _v1(monkeypatch, upstream)
    assert response.status_code == 502
    assert canary not in response.text
    assert all(canary not in v for v in response.headers.values())
    monkeypatch.setattr(
        query_pipeline.chain, "run", _raising(ChainExhausted([("other", "open")], last_error=failure))
    )
    response = _v1(monkeypatch, upstream)
    assert canary not in response.text and "other" not in response.json()["error"]["message"]


def test_query_success_body_has_no_provenance_keys(temp_db, chained, monkeypatch):
    monkeypatch.setattr(query_router, "call_openrouter", Upstream({"remote/m": _503()}))
    body = TestClient(app, headers=_HEADERS).post(
        "/query", json={"prompt": "hello", "model": "remote/m"}
    ).json()
    assert "provider" not in body and "attempts" not in body and "answered_by" not in body
    assert "answered_by" not in QuerySuccessResponse.model_json_schema()["properties"]


def test_v1_without_a_chain_is_one_attempt(temp_db, provider_file, monkeypatch):  # noqa: F811
    provider_file(_REGISTRY)  # no PROVIDER_CHAINS_FILE
    response = _v1(monkeypatch, Upstream())
    body = response.json()
    assert response.status_code == 200, response.text
    assert body["harness"]["attempts"] == 1
    assert response.headers["X-Harness-Provider"] == body["harness"]["provider"] == "remote"
