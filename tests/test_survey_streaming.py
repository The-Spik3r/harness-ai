"""PRD-021 STORY-001: the offline parts of scripts/survey_streaming.py.

The script is a spike that records facts from live servers and asserts none, so
nothing here touches the network (httpx is made to fail if it is used).
"""

import json
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

import scripts.survey_streaming as survey


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network touched")

    monkeypatch.setattr(httpx, "Client", boom)
    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(survey, "_requests_sent", 0)


def test_no_key_exits_cleanly(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = tmp_path / "fx"
    rc = survey.main(["--env-file", str(tmp_path / "missing.env"), "--out-dir", str(out)])
    assert rc == 0
    assert "no OPENROUTER_API_KEY" in capsys.readouterr().out
    assert not out.exists()


def test_sanitize_truncates_and_scrubs_key():
    long = "x" * 100
    line = "data: " + json.dumps(
        {"id": "gen-1", "model": "m", "choices": [{"delta": {"reasoning": long, "content": "SECRETKEY" + long,
         "reasoning_details": [{"text": long}]}, "finish_reason": None}]}
    )
    out = survey.sanitize_line(line, "SECRETKEY")
    # The key sits at the start of a field that is then cut to 40 chars; the
    # whole-line scrub also replaces it wherever it survived.
    assert "SECRETKEY" not in out
    chunk = json.loads(out[6:])
    delta = chunk["choices"][0]["delta"]
    assert len(delta["reasoning"]) == 40 and delta["content"].startswith("[KEY]")
    assert len(delta["reasoning_details"][0]["text"]) == 40
    assert chunk["id"] == "gen-1"


def test_sanitize_drops_comments_and_keeps_done():
    assert survey.sanitize_line(": OPENROUTER PROCESSING", None) is None
    assert survey.sanitize_line("", None) is None
    assert survey.sanitize_line("data: [DONE]", None) == "data: [DONE]"
    assert survey.scrub("a KEY b", "KEY") == "a [KEY] b"


def test_summarize_reports_reasoning_usage_and_parser_drops():
    lines = [
        'data: {"choices":[{"delta":{"role":"assistant","reasoning":"hm"}}]}',
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3,'
        '"completion_tokens_details":{"reasoning_tokens":1}}}',
        "data: [DONE]",
    ]
    s = survey.summarize(lines)
    assert s["reasoning_fields"] == ["reasoning"]
    assert s["reasoning_before_content"] is True
    assert s["usage_chunk_choices_empty"] is True and s["reasoning_tokens"] == 1
    assert s["parse_events"] == {"TextDelta": 1, "Finish": 1, "UsageReport": 1}
    assert "reasoning" in s["delta_keys_dropped_by_parser"]


def test_request_budget_refuses_a_seventh_call(monkeypatch):
    monkeypatch.setattr(survey, "_requests_sent", survey.MAX_REQUESTS)
    with pytest.raises(survey.RequestBudgetExceeded):
        survey.probe("http://x", None, "m")


def test_unreachable_local_is_not_an_error(monkeypatch):
    # httpx.get is patched to raise AssertionError by the autouse fixture; a
    # connect error is what a closed port gives.
    def refuse(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", refuse)
    assert survey.reachable("http://localhost:1") is False
