"""PRD-020 STORY-009 (D8): the adapter's usage table, both `usage_missing` values.

    AC2  `"usage": null` against the stub, estimate mode: flagged, no split
    AC3  the D8 table (absent / null / non-object / no total / junk total) x error|estimate;
         a reported total is unchanged; the legacy message texts are today's
"""

import io
import os
import threading

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.models.messages import Message
from app.services.upstream import UpstreamError, call_upstream
from app.services.upstream.params import ToolParams
from scripts.stub_openrouter import make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_upstream_adapter import _FakeClient, _response

_MSG = [Message("user", "a" * 8)]  # 8 chars sent
_REPLY = "b" * 12  # 12 chars received: ceil(8/4) + ceil(12/4) = 5


def _yaml(usage_missing=None, port=1, cpt=None):
    extra = f"    usage_missing: {usage_missing}\n" if usage_missing else ""
    extra += f"    estimate_chars_per_token: {cpt}\n" if cpt else ""
    return f"""
version: 1
default_model: local/m
providers:
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:{port}/v1
    insecure_http: true
{extra}    models:
      - id: local/m
        upstream: up-local
"""


def _body(**usage):
    body = {"choices": [{"message": {"content": _REPLY}}]}
    if usage.get("_raw", "absent") != "absent":
        body["usage"] = usage["_raw"]
    elif usage:
        body["usage"] = usage
    return body


def _call(provider_file, mode, body, **kw):
    provider_file(_yaml(mode))
    return call_upstream(_MSG, model="local/m", client=_FakeClient(response=_response(body=body)), **kw)


def test_null_usage_estimates_against_stub(provider_file):
    server = make_server(
        parse_script({"default": {"content": _REPLY, "usage": None}}), log=io.StringIO()
    )
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        provider_file(_yaml("estimate", server.server_address[1]))
        result = call_upstream(_MSG, model="local/m")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.usage_estimated is True
    assert result.tokens_used == 5
    assert result.input_tokens is None and result.output_tokens is None


# no usable total, fewer than two usable splits: an estimate (D8)
_ESTIMATED = [
    pytest.param(_body(), id="usage-absent"),
    pytest.param(_body(_raw=None), id="usage-null"),
    pytest.param(_body(_raw=[1, 2]), id="usage-list"),
    pytest.param(_body(_raw="12"), id="usage-string"),
    pytest.param(_body(prompt_tokens=3), id="no-total-one-split"),
    pytest.param(_body(completion_tokens=3), id="no-total-other-split"),
    pytest.param(_body(prompt_tokens=3, completion_tokens=-1), id="no-total-bad-split"),
    pytest.param(_body(total_tokens=None, prompt_tokens=3), id="junk-total-none"),
    pytest.param(_body(total_tokens="9"), id="junk-total-str"),
    pytest.param(_body(total_tokens=True), id="junk-total-bool"),
    pytest.param(_body(total_tokens=-4), id="junk-total-negative"),
]


@pytest.mark.parametrize("body", _ESTIMATED)
def test_d8_table_estimate_mode(provider_file, body):
    result = _call(provider_file, "estimate", body)
    assert (result.tokens_used, result.usage_estimated) == (5, True)
    assert result.input_tokens is None and result.output_tokens is None


def test_default_for_a_file_provider_is_estimate(provider_file):
    assert _call(provider_file, None, _body()).usage_estimated is True


def test_no_total_both_splits_sums_them(provider_file):
    result = _call(provider_file, "estimate", _body(prompt_tokens=3, completion_tokens=4))
    assert (result.tokens_used, result.input_tokens, result.output_tokens) == (7, 3, 4)
    assert result.usage_estimated is False


def test_total_present_unchanged(provider_file):
    for mode in ("estimate", "error"):
        result = _call(provider_file, mode, _body(total_tokens=9, prompt_tokens=3, completion_tokens=6))
        assert (result.tokens_used, result.input_tokens, result.output_tokens) == (9, 3, 6)
        assert result.usage_estimated is False
        result = _call(provider_file, mode, _body(total_tokens=9))
        assert (result.tokens_used, result.input_tokens, result.output_tokens) == (9, None, None)


def test_legacy_mode_keeps_the_raw_total(provider_file):
    # D1: `error` mode never validates the total; a junk value passes through as today.
    assert _call(provider_file, "error", _body(total_tokens="9")).tokens_used == "9"


@pytest.mark.parametrize(
    "body, quoted",
    [
        (_body(), "'usage'"),
        (_body(_raw=None), "'usage'"),
        (_body(_raw=[1]), "'usage'"),
        (_body(prompt_tokens=3, completion_tokens=4), "'total_tokens'"),
    ],
    ids=["absent", "null", "non-object", "no-total"],
)
def test_d8_table_error_mode_raises_todays_message(provider_file, body, quoted):
    with pytest.raises(UpstreamError) as excinfo:
        _call(provider_file, "error", body)
    assert str(excinfo.value) == f"Local returned an unexpected response shape: {quoted}"
    assert excinfo.value.upstream_status is None and excinfo.value.retryable is False


def test_estimate_counts_tools_calls_and_cpt(provider_file):
    provider_file(_yaml("estimate", cpt=2))
    tools = ToolParams(tools=[{"type": "function"}], tool_choice=None, parallel_tool_calls=None)
    client = _FakeClient(response=_response(body=_body()))
    result = call_upstream(_MSG, model="local/m", client=client, tools=tools)
    tools_chars = len('[{"type": "function"}]')
    assert result.tokens_used == -(-(8 + tools_chars) // 2) + 6
