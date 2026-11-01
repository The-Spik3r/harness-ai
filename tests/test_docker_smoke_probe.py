"""PRD-015 STORY-018: the Docker smoke probe's parsing and verdict helpers.

tests/e2e/test_docker_smoke.py only runs with Docker and `--run-e2e`, so what
decides its verdicts is pinned here, in the everyday suite:
- the SSE event parser;
- the keep-alive timer, run against a local server that gzip-flushes each frame
  the way Caddy's encoder does;
- the keep-alive window check;
- the wave split.
No Docker, no storage.
"""

import gzip
import json
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.e2e import docker_smoke_probe as probe

_ANSWER = "slow answer: keep-alives came through"  # contains ": keep-alive" on purpose


def _chunk(content=None, finish=None, usage=None, choices=True) -> str:
    event = {"id": "chatcmpl-harness-7", "object": "chat.completion.chunk", "created": 123, "model": "m"}
    event["choices"] = (
        [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish}] if choices else []
    )
    if usage:
        event["usage"] = usage
    return f"data: {json.dumps(event)}\n\n"


def _sse_frames(keepalives: int) -> list:
    return [probe.KEEPALIVE.decode()] * keepalives + [
        _chunk(content=_ANSWER),
        _chunk(finish="stop"),
        _chunk(choices=False, usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}),
        "data: [DONE]\n\n",
    ]


def test_events_normalises_id_and_created_and_keeps_done():
    events = probe._events("".join(_sse_frames(keepalives=2)))
    assert events[-1] == "[DONE]"
    assert len(events) == 4
    assert all(event["id_ok"] and "id" not in event and "created" not in event for event in events[:-1])
    assert events[0]["choices"][0]["delta"]["content"] == _ANSWER


def test_events_flags_an_id_that_is_not_the_harness_shape():
    events = probe._events(_chunk(content="x").replace("chatcmpl-harness-7", "chatcmpl-abc"))
    assert events[0]["id_ok"] is False


class _SlowSSE(BaseHTTPRequestHandler):
    interval = 0.3
    keepalives = 2

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        gzipped = "gzip" in self.headers.get("Accept-Encoding", "")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        if gzipped:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        encoder = zlib.compressobj(wbits=31) if gzipped else None  # 31: gzip container
        frames = _sse_frames(self.keepalives)
        for index, frame in enumerate(frames):
            if index <= self.keepalives:
                time.sleep(self.interval)
            data = frame.encode()
            if encoder:
                # Z_SYNC_FLUSH per frame, as an encoder that flushes on SSE does.
                data = encoder.compress(data) + encoder.flush(zlib.Z_SYNC_FLUSH)
            self.wfile.write(data)
            self.wfile.flush()
        if encoder:
            self.wfile.write(encoder.flush())
        self.close_connection = True

    def log_message(self, *args):
        pass


@pytest.fixture
def sse_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowSSE)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("encoding", ["gzip", "identity"])
def test_timed_stream_times_each_keepalive_and_ignores_answer_text(sse_server, encoding):
    timing = probe._timed_stream(sse_server, "token", "prompt", encoding)
    assert timing["status"] == 200
    assert timing["content_encoding"] == ("gzip" if encoding == "gzip" else None)
    # Two frames, not three: the answer's ": keep-alives" is not a keep-alive.
    assert len(timing["keepalives"]) == 2, timing
    first, second = timing["keepalives"]
    assert 0.2 <= first < second
    assert timing["first_data"] >= second
    assert timing["done"] is True
    assert not probe.keepalive_problems(timing, interval=0.3, tolerance=0.25, minimum=2)


def test_gzip_frames_survive_a_whole_body_decode():
    # The fixture's encoder output is a valid gzip stream overall, so the
    # incremental decode above is the only difference being tested.
    encoder = zlib.compressobj(wbits=31)
    body = b"".join(encoder.compress(f.encode()) + encoder.flush(zlib.Z_SYNC_FLUSH) for f in _sse_frames(1))
    body += encoder.flush()
    assert gzip.decompress(body).decode() == "".join(_sse_frames(1))


def _timing(**overrides) -> dict:
    timing = {"status": 200, "keepalives": [10.0, 20.1, 30.0], "first_data": 30.05, "done": True}
    timing.update(overrides)
    return timing


def test_keepalive_problems_accepts_arrivals_on_their_interval():
    assert probe.keepalive_problems(_timing(), 10, 2, minimum=2) == []


def test_keepalive_problems_flags_a_late_keepalive():
    problems = probe.keepalive_problems(_timing(keepalives=[10.0, 22.5]), 10, 2, minimum=2)
    assert problems == ["keep-alive 2 at 22.5s, due at 20s +- 2s"]


def test_keepalive_problems_flags_keepalives_bunched_at_the_end():
    # What a buffering proxy produces: everything arrives with the answer.
    problems = probe.keepalive_problems(_timing(keepalives=[30.0, 30.0, 30.0]), 10, 2, minimum=2)
    assert "keep-alive 1 at 30.0s, due at 10s +- 2s" in problems
    assert "keep-alive 2 at 30.0s, due at 20s +- 2s" in problems


def test_keepalive_problems_flags_too_few_missing_data_and_no_done():
    problems = probe.keepalive_problems(_timing(keepalives=[10.0], first_data=None, done=False), 10, 2, minimum=2)
    assert problems == ["1 keep-alives, expected at least 2", "no data event", "no [DONE]"]


def test_keepalive_problems_reports_a_failed_request():
    assert probe.keepalive_problems({"error": "boom"}, 10, 2, minimum=2) == ["request failed: boom"]
    assert probe.keepalive_problems(_timing(status=502), 10, 2, minimum=2) == ["status 502"]


def test_split_waves_separates_queued_requests():
    requests = [{"headers_after": h} for h in (0.2, 5.4, 0.3, 0.1, 5.2, 0.25, 5.3, 5.1)]
    at_once, queued = probe.split_waves(requests, 5.0)
    assert at_once == [0.1, 0.2, 0.25, 0.3]
    assert queued == [5.1, 5.2, 5.3, 5.4]
