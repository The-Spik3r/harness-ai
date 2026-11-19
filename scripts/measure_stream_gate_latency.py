"""What the output gate costs per segment and per response (PRD-021 STORY-008, AC 5).

PRD-021 Risk 2 and *Quality indicators*: the gate must add at most 150 ms (p95)
per released segment, or segments batch to two sentences. Like
`scripts/measure_pii_latency.py` this *records* numbers and asserts none of them
(a wall-clock assertion on a loaded CI machine would be flaky).

A scripted 2 000-character reply (sentences plus a few emails and phones) is
fed to `OutputGate` in 12-character deltas, for `chat` and for `code` with
`PII_CODE_REDACT_OUTPUT` on (otherwise `code` builds no gate). Per arm:

    segment   -- each `feed()` call that released text (p95 per segment: AC 5)
    response  -- the whole feed + finish loop, final pass included in `finish`
    final     -- one `redact()` over the whole text (the step 8 cost it replaces)

Analyzers are loaded and one reply is run before the timing window.

Usage:  python scripts/measure_stream_gate_latency.py [--runs 50]
"""

import argparse
import math
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DATABASE_URL", "http://127.0.0.1:8080")
os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")

from app.config import settings  # noqa: E402
from app.services import pii_policy, pii_redactor  # noqa: E402
from app.services.stream_redaction import OutputGate  # noqa: E402

_SENTENCES = [
    "The deployment finished without errors and the service is healthy.",
    "You can reach the maintainer at ana.garcia@example.com for questions.",
    "Next, restart the worker and check the queue depth on the dashboard.",
    "Call the on-call engineer at +1 415 555 0132 if the alert persists.",
    "Latency dropped by a third after the cache warmed up this morning.",
    "Send the report to luis.perez@example.org before the end of the day.",
]


def _reply(target: int = 2000) -> str:
    out, i = [], 0
    while sum(len(s) + 1 for s in out) < target:
        out.append(_SENTENCES[i % len(_SENTENCES)])
        i += 1
    return " ".join(out)[:target]


def _p(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def _line(label, values):
    ms = [v * 1000 for v in values]
    print(f"  {label:<9} n={len(ms):<5} p50={_p(ms, .5):8.1f} ms  p95={_p(ms, .95):8.1f} ms  max={max(ms):8.1f} ms")


def _run_once(policy, text, size=12):
    gate = OutputGate(policy, settings.STREAM_HOLDBACK_MAX_CHARACTERS)
    segments = []
    loop_start = time.perf_counter()
    for i in range(0, len(text), size):
        t0 = time.perf_counter()
        out = gate.feed(text[i:i + size])
        elapsed = time.perf_counter() - t0
        if out:
            segments.append(elapsed)
    gate.finish()
    return segments, time.perf_counter() - loop_start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()
    settings.PII_CODE_REDACT_OUTPUT = True
    text = _reply()
    print(f"reply: {len(text)} characters, holdback cap {settings.STREAM_HOLDBACK_MAX_CHARACTERS}")
    for name in ("chat", "code"):
        policy = pii_policy.get_pii_policy(name)
        _run_once(policy, text)  # warm-up: analyzers load here, not in the window
        pii_redactor.redact(text)
        segments, responses, finals = [], [], []
        for _ in range(args.runs):
            seg, total = _run_once(policy, text)
            segments += seg
            responses.append(total)
            t0 = time.perf_counter()
            pii_redactor.redact_for_policy(text, policy)
            finals.append(time.perf_counter() - t0)
        print(f"{name}:")
        _line("segment", segments)
        _line("response", responses)
        _line("final", finals)


if __name__ == "__main__":
    main()
