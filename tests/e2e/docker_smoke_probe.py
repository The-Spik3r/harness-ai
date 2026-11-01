"""The Docker smoke's in-container probe (PRD-015 STORY-018). Not a test module.

tests/e2e/test_docker_smoke.py runs this inside the harness container:

    docker compose exec -T harness-ai python -m tests.e2e.docker_smoke_probe \\
        --direct http://127.0.0.1:8001 --caddy http://127.0.0.1:8095 --nonce N --workers 4 [--sections ...]

The bearer token comes from `SMOKE_TOKEN` in the environment (`exec -e`), so it
is never on a command line or in the output.

It runs from inside the container so Docker Desktop's port forwarding, which is
known to stall (PRD-014 STORY-006), is not in the timing path. `--direct` is the
backend process Caddy proxies to (`reflex run --backend-only`), so a difference
between the two bases is Caddy's doing.

It asserts nothing. It prints one ASCII JSON object on its last stdout line, and
the test module asserts on it. Each section records its own `error` instead of
stopping the run, so one broken section does not hide the others. Prompts carry
the run nonce plus a per-request suffix, because the duplicate checker spans
`/v1` and `/query` and would refuse a repeated prompt.
"""

import argparse
import json
import os
import re
import threading
import time
import traceback

import httpx

MODEL = "openai/gpt-4o"
# The whole comment frame, as app/services/v1_sse.py:KEEPALIVE writes it. A bare
# b": keep-alive" also matches answer text such as "...: keep-alives came through".
KEEPALIVE = b": keep-alive\n\n"
_ID = re.compile(r"^chatcmpl-harness-\d+$")


def _headers(token: str, **extra) -> dict:
    return {"Authorization": f"Bearer {token}", **extra}


def _body(prompt: str, stream: bool) -> dict:
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": stream}
    if stream:
        body["stream_options"] = {"include_usage": True}
    return body


def _events(text: str) -> list:
    """The `data:` payloads of an SSE body, with per-request fields normalised."""
    events = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            events.append("[DONE]")
            continue
        event = json.loads(payload)
        event["id_ok"] = bool(_ID.match(event.pop("id", "")))
        event.pop("created", None)
        events.append(event)
    return events


def _completion(client: httpx.Client, base: str, token: str, prompt: str) -> dict:
    response = client.post(f"{base}/v1/chat/completions", headers=_headers(token), json=_body(prompt, False))
    out = {"status": response.status_code}
    if response.status_code == 200:
        data = response.json()
        choice = data["choices"][0]
        out.update(
            object=data.get("object"),
            id_ok=bool(_ID.match(data.get("id", ""))),
            model=data.get("model"),
            content=choice["message"]["content"],
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
        )
    else:
        out["body"] = response.text[:500]
    return out


def _streamed(client: httpx.Client, base: str, token: str, prompt: str) -> dict:
    response = client.post(f"{base}/v1/chat/completions", headers=_headers(token), json=_body(prompt, True))
    return {
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "events": _events(response.text) if response.status_code == 200 else response.text[:500],
    }


def compare(args) -> dict:
    out = {}
    with httpx.Client(timeout=60) as client:
        for label, base in (("direct", args.direct), ("caddy", args.caddy)):
            out[label] = {
                "completion": _completion(client, base, args.token, f"compare {label} plain {args.nonce}"),
                "stream": _streamed(client, base, args.token, f"compare {label} streamed {args.nonce}"),
            }
    return out


def _timed_stream(base: str, token: str, prompt: str, accept_encoding: str) -> dict:
    """Arrival time of each keep-alive and of the first data event, from response headers."""
    keepalives, first_data, buffer = [], None, b""
    started = time.monotonic()
    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{base}/v1/chat/completions",
            headers=_headers(token, **{"Accept-Encoding": accept_encoding}),
            json=_body(prompt, True),
        ) as response:
            t0 = time.monotonic()
            # iter_bytes decodes gzip incrementally, so a keep-alive is seen as
            # soon as the encoder flushes it, and no earlier.
            for chunk in response.iter_bytes():
                now = round(time.monotonic() - t0, 3)
                buffer += chunk
                while KEEPALIVE in buffer:
                    keepalives.append(now)
                    buffer = buffer.split(KEEPALIVE, 1)[1]
                if first_data is None and b"data: " in buffer:
                    first_data = now
            return {
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "content_encoding": response.headers.get("content-encoding"),
                "headers_after": round(t0 - started, 3),
                "keepalives": keepalives,
                "first_data": first_data,
                "total": round(time.monotonic() - t0, 3),
                "done": b"[DONE]" in buffer,
            }


def keepalive(args) -> dict:
    out = {}
    targets = [("caddy_gzip", args.caddy, "gzip"), ("direct_gzip", args.direct, "gzip")]
    if args.identity:
        targets.append(("caddy_identity", args.caddy, "identity"))
    results = {}

    def run(label, base, encoding):
        try:
            results[label] = _timed_stream(base, args.token, f"SMOKE-SLOW {label} {args.nonce}", encoding)
        except Exception:  # recorded, not raised: see the module docstring
            results[label] = {"error": traceback.format_exc(limit=3)}

    # In parallel: each one waits 30 s on the stub, and the executor has room.
    threads = [threading.Thread(target=run, args=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    out.update(results)
    return out


def routes(args) -> dict:
    out = {}
    with httpx.Client(timeout=60) as client:
        # Static Reflex pages. file_server answers a directory path such as
        # /admin/audit with a 308 to its trailing-slash form, as a browser
        # follows, so both the first hop and where it ends up are recorded.
        for path in ("/", "/admin/audit"):
            first = client.get(f"{args.caddy}{path}")
            final = client.get(f"{args.caddy}{path}", follow_redirects=True)
            out[path] = {
                "status": first.status_code,
                "location": first.headers.get("location"),
                "final_status": final.status_code,
                "final_path": final.url.path,
                "content_type": final.headers.get("content-type", ""),
            }
        ping = client.get(f"{args.caddy}/ping")
        out["/ping"] = {"status": ping.status_code, "body": ping.text[:100]}
        health = client.get(f"{args.caddy}/health")
        out["/health"] = {"status": health.status_code, "body": health.text[:100]}
        query = client.post(
            f"{args.caddy}/query",
            headers=_headers(args.token),
            json={"prompt": f"SMOKE-QUERY {args.nonce}", "model": MODEL},
        )
        out["/query"] = {"status": query.status_code}
        if query.status_code == 200:
            out["/query"]["response"] = query.json().get("response")
        else:
            out["/query"]["body"] = query.text[:500]
        models = client.get(f"{args.caddy}/v1/models", headers=_headers(args.token))
        out["/v1/models"] = {"status": models.status_code}
        if models.status_code == 200:
            out["/v1/models"]["ids"] = [item["id"] for item in models.json().get("data", [])]
        else:
            out["/v1/models"]["body"] = models.text[:500]
    return out


def concurrency(args) -> dict:
    """PRD-015 Risk 6: N streamed requests at once against PIPELINE_MAX_WORKERS threads."""
    count = args.count or 2 * args.workers
    results = [None] * count
    barrier = threading.Barrier(count)

    def run(index):
        prompt = f"SMOKE-WAVE {index} {args.nonce}"
        try:
            with httpx.Client(timeout=120) as client:
                barrier.wait()
                sent = time.monotonic()
                with client.stream(
                    "POST", f"{args.caddy}/v1/chat/completions", headers=_headers(args.token), json=_body(prompt, True)
                ) as response:
                    headers_at = time.monotonic() - sent
                    text = b"".join(response.iter_bytes()).decode("utf-8", "replace")
                    results[index] = {
                        "status": response.status_code,
                        "headers_after": round(headers_at, 3),
                        "total": round(time.monotonic() - sent, 3),
                        "done": "data: [DONE]" in text,
                    }
        except Exception:
            results[index] = {"error": traceback.format_exc(limit=3)}

    started = time.monotonic()
    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return {"workers": args.workers, "count": count, "wall": round(time.monotonic() - started, 3), "requests": results}


def keepalive_problems(timing: dict, interval: float, tolerance: float, minimum: int) -> list:
    """Why `timing` (one `_timed_stream` result) breaks the keep-alive contract; empty if it holds.

    The k-th keep-alive is due k * interval after the response headers
    (app/services/v1_sse.py: the first comes one interval after commit, and the
    headers go out at commit). Used by the host-side test, not in the container.
    """
    if "error" in timing:
        return [f"request failed: {timing['error']}"]
    problems = []
    if timing.get("status") != 200:
        problems.append(f"status {timing.get('status')}")
    arrivals = timing.get("keepalives", [])
    if len(arrivals) < minimum:
        problems.append(f"{len(arrivals)} keep-alives, expected at least {minimum}")
    for k, arrived in enumerate(arrivals, start=1):
        if abs(arrived - k * interval) > tolerance:
            problems.append(f"keep-alive {k} at {arrived}s, due at {k * interval}s +- {tolerance}s")
    first_data = timing.get("first_data")
    if first_data is None:
        problems.append("no data event")
    elif arrivals and first_data < arrivals[-1]:
        problems.append(f"data at {first_data}s before the last keep-alive at {arrivals[-1]}s")
    if not timing.get("done"):
        problems.append("no [DONE]")
    return problems


def split_waves(requests: list, delay: float) -> tuple:
    """(committed at once, queued) time-to-headers lists for a concurrency run.

    A request that waited for a pipeline worker gets its headers only after a
    running one finished, which takes at least the stub's `delay`; one that
    found a free worker commits before the stub answers, well under it.
    """
    heads = sorted(entry["headers_after"] for entry in requests)
    return [h for h in heads if h < delay], [h for h in heads if h >= delay]


SECTIONS = {"compare": compare, "keepalive": keepalive, "routes": routes, "concurrency": concurrency}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--direct", required=True)
    parser.add_argument("--caddy", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--workers", type=int, required=True, help="PIPELINE_MAX_WORKERS the stack runs with")
    parser.add_argument("--count", type=int, default=0, help="concurrent requests (default 2 x workers)")
    parser.add_argument("--identity", action="store_true", help="also time keep-alives with Accept-Encoding: identity")
    parser.add_argument("--sections", nargs="+", default=list(SECTIONS), choices=list(SECTIONS))
    args = parser.parse_args(argv)
    args.token = os.environ["SMOKE_TOKEN"]
    out = {}
    for name in args.sections:
        try:
            out[name] = SECTIONS[name](args)
        except Exception:
            out[name] = {"error": traceback.format_exc(limit=3)}
    print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
