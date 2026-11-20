"""PRD-022 STORY-011: the chain runner (`upstream/chain.py`), with fakes and an injected clock."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.pii_redactor import PiiRedactorError
from app.services.upstream import chain as chain_mod
from app.services.upstream import health
from app.services.upstream.chain import REDACTION_LIMIT, RequestNeeds, run
from app.services.upstream.chain_config import Candidate, Chain, ChainLimits
from app.services.upstream.types import ChainExhausted, UpstreamError


@pytest.fixture
def now():
    t = [0.0]
    health.reset(clock=lambda: t[0])
    yield t
    health.reset()


def _route(model_id, provider=None, *, trust="internal", timeout=30.0, relaxed=False, **caps):
    capabilities = SimpleNamespace(
        tools=caps.get("tools", True),
        forced_tool_choice=caps.get("forced_tool_choice", True),
        streaming=caps.get("streaming", True),
        max_context_tokens=caps.get("max_context_tokens"),
    )
    return SimpleNamespace(
        model_id=model_id,
        provider=SimpleNamespace(name=provider or f"p-{model_id}", trust=trust, timeout_seconds=timeout),
        capabilities=capabilities,
        relaxes_input=lambda: relaxed,
    )


def _err(kind="timeout", retryable=True, status=None):
    return UpstreamError("x", kind=kind, retryable=retryable, upstream_status=status)


class Harness:
    """Routes a, b, c; every callback records into one event log."""

    def __init__(self, routes, *, clock=None, **overrides):
        self.routes = {r.model_id: r for r in routes}
        self.chain = Chain(
            routes[0].model_id, None, tuple(Candidate(r.model_id) for r in routes)
        )
        self.events = []
        self.forbidden = set()
        self.behaviour = {}  # model_id -> result or exception
        self.prepared = []
        self.released = False
        self.kw = dict(
            primary=routes[0],
            limits=None,
            needs=RequestNeeds(),
            byok=False,
            policy="policy",
            resolve=self.routes.get,
            permitted=self._permitted,
            prepare=self._prepare,
            attempt=self._attempt,
            on_attempt_failed=self._failed,
            released=lambda: self.released,
        )
        if clock is not None:
            self.kw["clock"] = clock
        self.kw.update(overrides)
        self.timeouts = []

    def _permitted(self, model_id):
        self.events.append(("permitted", model_id))
        return model_id not in self.forbidden

    def _prepare(self, route):
        self.prepared.append(route.model_id)
        return f"sent-for-{route.model_id}"

    def _attempt(self, route, sent, timeout):
        self.events.append(("attempt", route.model_id))
        self.timeouts.append(timeout)
        outcome = self.behaviour.get(route.model_id, f"ok-{route.model_id}")
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def _failed(self, candidate, error, *, attempt):
        self.events.append(("failed", candidate.model_id, attempt))

    def run(self):
        return run(self.chain, **self.kw)

    def attempted(self):
        return [e[1] for e in self.events if e[0] == "attempt"]


def _abc(**kw):
    return [_route("a", **kw), _route("b"), _route("c")]


def _counters():
    return health.providers_status([]).counters


# --- 1. skip reasons -------------------------------------------------------------


def test_the_primary_answers_with_no_skip_and_no_reason(now):
    h = Harness(_abc())
    out = h.run()
    assert (out.result, out.candidate.model_id, out.attempt) == ("ok-a", "a", 1)
    assert out.fallback_reason is None and out.skipped is None
    assert ("permitted", "a") not in h.events  # the primary is never asked (step 2 ruled)


def test_forbidden_skips_a_fallback_and_counts_it(now):
    h = Harness(_abc())
    h.forbidden = {"b"}
    h.behaviour["a"] = _err()
    out = h.run()
    assert out.candidate.model_id == "c" and out.skipped == "p-b:forbidden"
    assert _counters().skipped == {"p-b:forbidden": 1}


def test_an_unresolvable_candidate_is_forbidden_with_an_unknown_provider(now):
    h = Harness(_abc(), resolve=lambda m: None if m == "b" else h.routes[m])
    h.behaviour["a"] = _err()
    out = h.run()
    assert out.skipped == "unknown:forbidden" and out.candidate.model_id == "c"


@pytest.mark.parametrize(
    "needs,caps",
    [
        (RequestNeeds(tools=True), {"tools": False}),
        (RequestNeeds(tools=True, forced_tool_choice=True), {"forced_tool_choice": False}),
        (RequestNeeds(streaming=True), {"streaming": False}),
        (RequestNeeds(estimate=lambda r: 500), {"max_context_tokens": 100}),
    ],
)
def test_capability_skips_a_candidate_that_cannot_serve_the_request(now, needs, caps):
    routes = [_route("a"), _route("b", **caps), _route("c")]
    h = Harness(routes, needs=needs)
    h.behaviour["a"] = _err()
    out = h.run()
    assert out.candidate.model_id == "c" and out.skipped == "p-b:capability"


def test_the_context_estimate_is_evaluated_only_when_the_route_sets_a_maximum(now):
    calls = []

    def estimate(route):
        calls.append(route.model_id)
        return 10

    h = Harness([_route("a"), _route("b", max_context_tokens=100)], needs=RequestNeeds(estimate=estimate))
    h.behaviour["a"] = _err()
    h.run()
    assert calls == ["b"]


def test_byok_skips_every_fallback_but_never_the_primary(now):
    h = Harness(_abc(), byok=True)
    h.behaviour["a"] = _err()
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-b", "byok"), ("p-c", "byok"))
    assert h.attempted() == ["a"]


def test_deadline_skips_when_too_little_time_remains(now):
    h = Harness(_abc(), clock=lambda: now[0], limits=ChainLimits(3, 10.0, 2.0))

    def slow(route, sent, timeout):
        h.events.append(("attempt", route.model_id))
        now[0] += 9.0  # leaves 1 s < min_attempt 2 s
        raise _err()

    h.kw["attempt"] = slow
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-b", "deadline"), ("p-c", "deadline"))
    assert h.attempted() == ["a"]


def test_redaction_limit_skips_and_a_cached_limit_is_reused(now):
    h = Harness([_route("a", relaxed=True), _route("b"), _route("c")])
    h.kw["prepare"] = lambda route: h.prepared.append(route.model_id) or REDACTION_LIMIT
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-a", "redaction_limit"), ("p-b", "redaction_limit"), ("p-c", "redaction_limit"))
    assert h.prepared == ["a", "b"]  # b and c share the (policy, standard) key


def _open(name, now):
    for _ in range(5):
        health.record(name, _err())


def test_an_open_breaker_skips_the_candidate(now):
    h = Harness(_abc())
    _open("p-a", now)
    now[0] = 3.0
    out = h.run()
    assert out.skipped == "p-a:open" and out.candidate.model_id == "b"
    assert _counters().skipped == {"p-a:open": 1}


def test_half_open_busy_is_skipped_while_a_trial_is_in_flight(now):
    h = Harness(_abc())
    _open("p-a", now)
    now[0] = 10.5
    assert health.admit("p-a").admitted  # someone else holds the trial
    out = h.run()
    assert out.skipped == "p-a:half_open_busy" and out.candidate.model_id == "b"
    assert _counters().skipped == {"p-a:half_open_busy": 1}


def test_each_skip_reason_is_counted(now):
    h = Harness(_abc(), byok=True)
    h.behaviour["a"] = _err()
    with pytest.raises(ChainExhausted):
        h.run()
    assert _counters().skipped == {"p-b:byok": 1, "p-c:byok": 1}


# --- 2. order ---------------------------------------------------------------------


def test_forbidden_outranks_capability_and_byok(now):
    h = Harness([_route("a"), _route("b", tools=False), _route("c")], needs=RequestNeeds(tools=True), byok=True)
    h.forbidden = {"b"}
    h.behaviour["a"] = _err()
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped[0] == ("p-b", "forbidden")


def test_admit_is_last_so_a_skipped_candidate_never_claims_a_trial(now, monkeypatch):
    admitted = []
    real = health.admit
    monkeypatch.setattr(health, "admit", lambda n: admitted.append(n) or real(n))
    h = Harness(
        [_route("a"), _route("b"), _route("c")],
        clock=lambda: now[0],
        limits=ChainLimits(3, 10.0, 2.0),
    )
    h.kw["prepare"] = lambda route: REDACTION_LIMIT if route.model_id == "b" else "sent"

    def slow(route, sent, timeout):
        now[0] += 9.0
        raise _err()

    h.kw["attempt"] = slow
    with pytest.raises(ChainExhausted):
        h.run()
    assert admitted == ["p-a"]  # b (deadline) and c (deadline) never reached admit


def test_redaction_limit_never_calls_admit(now, monkeypatch):
    admitted = []
    real = health.admit
    monkeypatch.setattr(health, "admit", lambda n: admitted.append(n) or real(n))
    h = Harness([_route("a", relaxed=True), _route("b"), _route("c")])
    h.kw["prepare"] = lambda route: REDACTION_LIMIT if route.relaxes_input() else "sent"
    out = h.run()
    assert out.candidate.model_id == "b" and admitted == ["p-b"]


# --- 3. failure -------------------------------------------------------------------


def test_an_eligible_failure_is_recorded_reported_before_the_next_attempt_then_falls_back(now):
    h = Harness(_abc())
    h.behaviour["a"] = _err(status=503)
    out = h.run()
    assert h.events == [("attempt", "a"), ("failed", "a", 1), ("permitted", "b"), ("attempt", "b")]
    assert out.attempt == 2 and _counters().attempts_failed == {"p-a:timeout": 1}


@pytest.mark.parametrize("kind", ["status", "shape", "incompatible", "refusal"])
def test_a_non_eligible_error_is_raised_with_no_further_attempt(now, kind):
    h = Harness(_abc())
    err = _err(kind=kind, retryable=False, status=400)
    h.behaviour["a"] = err
    with pytest.raises(UpstreamError) as info:
        h.run()
    assert info.value is err
    assert h.attempted() == ["a"] and ("failed", "a", 1) in h.events


def test_an_eligible_failure_after_release_is_raised(now):
    h = Harness(_abc())
    err = _err()
    h.behaviour["a"] = err
    h.released = True
    with pytest.raises(UpstreamError) as info:
        h.run()
    assert info.value is err and h.attempted() == ["a"]


def test_released_is_read_live_after_each_failure(now):
    h = Harness(_abc())
    err_b = _err(kind="transport")

    def attempt(route, sent, timeout):
        h.events.append(("attempt", route.model_id))
        if route.model_id == "a":
            raise _err()
        h.released = True  # b releases to the sink, then fails
        raise err_b

    h.kw["attempt"] = attempt
    with pytest.raises(UpstreamError) as info:
        h.run()
    assert info.value is err_b and h.attempted() == ["a", "b"]


def test_misconfigured_falls_back(now):
    h = Harness(_abc())
    h.behaviour["a"] = UpstreamError("x", kind="misconfigured", upstream_status=401)
    assert h.run().candidate.model_id == "b"


# --- 4. exhaustion ----------------------------------------------------------------


def test_all_skipped_has_no_last_error_and_no_retry_after_without_an_open_breaker(now):
    routes = [_route("a", tools=False), _route("b", tools=False), _route("c", tools=False)]
    h = Harness(routes, needs=RequestNeeds(tools=True))
    with pytest.raises(ChainExhausted) as info:
        h.run()
    exc = info.value
    assert exc.last_error is None and exc.retry_after_seconds is None
    assert exc.skipped == (("p-a", "capability"), ("p-b", "capability"), ("p-c", "capability"))
    assert exc.kind == "exhausted" and exc.retryable and h.attempted() == []


def test_retry_after_is_the_smallest_open_window_and_at_least_one(now):
    h = Harness([_route("a"), _route("b")])
    _open("p-a", now)
    _open("p-b", now)
    now[0] = 9.5  # 0.5 s left on both windows
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-a", "open"), ("p-b", "open"))
    assert info.value.retry_after_seconds == 1
    now[0] = 0.0
    health.reset(clock=lambda: now[0])
    _open("p-a", now)
    now[0] = 4.0
    _open("p-b", now)  # opens at t=4 -> 10 s window
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.retry_after_seconds == 6


def test_every_candidate_failing_eligibly_exhausts_with_the_last_error(now):
    h = Harness(_abc())
    last = _err(kind="transport")
    h.behaviour.update({"a": _err(), "b": _err(), "c": last})
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.last_error is last and info.value.skipped == ()
    assert h.attempted() == ["a", "b", "c"]


def test_a_mixed_skip_and_failure_exhausts_with_both(now):
    h = Harness(_abc())
    h.forbidden = {"b"}
    h.behaviour.update({"a": _err(), "c": _err(kind="transport")})
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-b", "forbidden"),)
    assert info.value.last_error.kind == "transport"


# --- 5/6. success outcome -----------------------------------------------------------


def test_success_records_a_closing_success_and_counts_a_fallback_answer_only_after_attempt_one(now):
    h = Harness(_abc())
    h.run()
    assert _counters().fallback_answers == 0
    h.behaviour["a"] = _err()
    out = h.run()
    assert out.attempt == 2 and _counters().fallback_answers == 1


def test_a_candidate_answering_as_attempt_one_after_a_skipped_primary_is_not_a_fallback_answer(now):
    h = Harness([_route("a", relaxed=True), _route("b"), _route("c")])
    h.kw["prepare"] = lambda route: REDACTION_LIMIT if route.relaxes_input() else "sent"
    out = h.run()
    assert out.attempt == 1 and out.skipped == "p-a:redaction_limit"
    assert _counters().fallback_answers == 0 and out.fallback_reason is None


def test_skipped_string_lists_provider_reason_pairs_in_order(now):
    h = Harness(_abc())
    h.forbidden = {"b"}
    h.behaviour["a"] = _err()
    h.kw["needs"] = RequestNeeds()
    h.routes["c"].capabilities.tools = True
    out = h.run()
    assert out.skipped == "p-b:forbidden"
    h2 = Harness([_route("a"), _route("b", tools=False), _route("c")], needs=RequestNeeds(tools=True))
    h2.forbidden = set()
    h2.behaviour["a"] = _err()
    assert h2.run().skipped == "p-b:capability"


@pytest.mark.parametrize(
    "error,expected",
    [
        (_err(status=503), "status_503"),
        (_err(kind="timeout"), "timeout"),
        (UpstreamError("x", retryable=True), "unclassified"),
    ],
)
def test_fallback_reason_names_the_previous_failure(now, error, expected):
    h = Harness(_abc())
    h.behaviour["a"] = error
    assert h.run().fallback_reason == expected


def test_fallback_reason_appends_trust_lowered_for_an_internal_primary_answered_externally(now):
    h = Harness([_route("a"), _route("b", trust="external")])
    h.behaviour["a"] = _err(status=503)
    assert h.run().fallback_reason == "status_503;trust_lowered"


def test_trust_lowered_alone_when_the_primary_was_skipped(now):
    h = Harness([_route("a", relaxed=True), _route("b", trust="external")])
    h.kw["prepare"] = lambda route: REDACTION_LIMIT if route.relaxes_input() else "sent"
    out = h.run()
    assert out.attempt == 1 and out.fallback_reason == "trust_lowered"


def test_an_internal_fallback_for_an_internal_primary_is_not_trust_lowered(now):
    h = Harness(_abc())
    h.behaviour["a"] = _err()
    assert "trust_lowered" not in h.run().fallback_reason


# --- 7. prepare -----------------------------------------------------------------------


def test_prepare_is_cached_per_policy_and_relaxation(now):
    routes = [_route("a", relaxed=True), _route("b"), _route("c"), _route("d", relaxed=True)]
    h = Harness(routes)
    h.behaviour.update({m: _err() for m in "abc"})
    assert h.run().candidate.model_id == "d"
    assert h.prepared == ["a", "b"]  # c reuses b's standard text, d reuses a's relaxed text


def test_a_fallback_never_receives_the_relaxed_text_of_an_internal_primary(now):
    routes = [_route("a", relaxed=True), _route("b", trust="external")]
    h = Harness(routes)
    h.kw["prepare"] = lambda route: "relaxed-text" if route.relaxes_input() else "standard-text"
    sent = []

    def attempt(route, text, timeout):
        sent.append((route.model_id, text))
        if route.model_id == "a":
            raise _err()
        return "ok"

    h.kw["attempt"] = attempt
    h.run()
    assert sent == [("a", "relaxed-text"), ("b", "standard-text")]


def test_a_pii_redactor_error_propagates_and_nothing_is_attempted(now):
    h = Harness(_abc())

    def boom(route):
        raise PiiRedactorError("down")

    h.kw["prepare"] = boom
    with pytest.raises(PiiRedactorError):
        h.run()
    assert h.attempted() == []


# --- 8. deadline and timeout --------------------------------------------------------------


def test_the_attempt_timeout_is_the_smaller_of_the_provider_and_the_remainder(now):
    h = Harness([_route("a", timeout=30.0), _route("b", timeout=30.0)], clock=lambda: now[0], limits=ChainLimits(3, 20.0, 1.0))
    h.run()
    assert h.timeouts == [20.0]
    h2 = Harness([_route("a", timeout=5.0)], clock=lambda: now[0], limits=ChainLimits(3, 20.0, 1.0))
    h2.run()
    assert h2.timeouts == [5.0]


def test_the_remainder_shrinks_after_a_slow_attempt(now):
    h = Harness(_abc(), clock=lambda: now[0], limits=ChainLimits(3, 20.0, 1.0))

    def attempt(route, sent, timeout):
        h.timeouts.append(timeout)
        if route.model_id == "a":
            now[0] += 12.0
            raise _err()
        return "ok"

    h.kw["attempt"] = attempt
    h.run()
    assert h.timeouts == [20.0, 8.0]


def test_the_default_deadline_is_the_primarys_provider_timeout(now):
    h = Harness([_route("a", timeout=10.0), _route("b", timeout=30.0)], clock=lambda: now[0], limits=ChainLimits(3, None, 1.0))

    def attempt(route, sent, timeout):
        h.timeouts.append(timeout)
        if route.model_id == "a":
            now[0] += 9.5
            raise _err()
        return "ok"

    h.kw["attempt"] = attempt
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-b", "deadline"),) and h.timeouts == [10.0]


def test_no_limits_means_no_deadline_and_no_timeout(now):
    h = Harness(_abc(), clock=lambda: now[0])

    def attempt(route, sent, timeout):
        h.timeouts.append(timeout)
        now[0] += 1000.0
        if route.model_id != "c":
            raise _err()
        return "ok"

    h.kw["attempt"] = attempt
    assert h.run().candidate.model_id == "c"
    assert h.timeouts == [None, None, None]


# --- 9. non-UpstreamError ---------------------------------------------------------------


def test_a_non_upstream_error_propagates_unchanged_and_is_not_recorded(now):
    h = Harness(_abc())
    bug = RuntimeError("bug")
    h.behaviour["a"] = bug
    with pytest.raises(RuntimeError) as info:
        h.run()
    assert info.value is bug
    assert _counters().attempts_failed == {} and not any(e[0] == "failed" for e in h.events)


def test_a_half_open_trial_lost_to_a_bug_is_busy_until_the_lease_lapses(now):
    h = Harness([_route("a")])
    _open("p-a", now)
    now[0] = 10.5
    h.behaviour["a"] = RuntimeError("bug")
    with pytest.raises(RuntimeError):
        h.run()
    h.behaviour["a"] = "ok"
    with pytest.raises(ChainExhausted) as info:
        h.run()
    assert info.value.skipped == (("p-a", "half_open_busy"),)
    now[0] += 10.5  # the 10 s lease lapses
    assert h.run().result == "ok"


# --- 10. purity ----------------------------------------------------------------------------


def test_the_module_is_pure():
    source = Path(chain_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {"time", "dataclasses", "typing"}
    internal = {
        "app.services.upstream",
        "app.services.upstream.chain_config",
        "app.services.upstream.types",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {a.name.split(".")[0] for a in node.names} <= allowed
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module in internal or node.module.split(".")[0] in allowed
            if node.module == "app.services.upstream":
                assert {a.name for a in node.names} == {"health"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not (
        {"open", "settings", "httpx", "database", "get_connection", "authz", "provider_registry"}
        & (names | attrs)
    )
