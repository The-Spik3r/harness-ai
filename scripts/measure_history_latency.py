"""What sending history actually costs, measured rather than argued about.

PRD-010 STORY-015, serving PRD Section 11's quality indicator ("added latency
per chat send at most one `messages_for` read plus per-turn redaction") and
Risk 3 ("per-turn redaction latency grows with history"). This is a spike: it
*records* numbers and asserts none of them, exactly as
`tests/test_two_instance_smoke.py` does -- a wall-clock threshold asserted as
pass/fail would be a flaky test on a loaded machine, and the figure that carries
meaning here is the ratio between the history path and the single-turn path,
not any absolute millisecond count.

Four arms are timed, each over `--sends` iterations, against the local libSQL
dev server with real Presidio and a stub upstream:

    (a) assemble   -- chat_history.assemble + fit: one live `messages_for` read
    (b) redaction  -- redact() over every message, the loop at
                      app/services/query_pipeline.py:265-284
    (c) pipeline   -- the whole run_conversation, minus the stub's own span
    (d) single     -- (b) and (c) again for a one-message conversation

**Why the final user turn is unique on every iteration.** The duplicate check is
step 4 of the pipeline and redaction is step 6
(app/services/query_pipeline.py:226-284), so thirty sends of an identical
conversation would return BLOCKED_DUPLICATE from the second iteration onward and
skip everything this script exists to measure. Every iteration therefore carries
a run nonce and an index in its last turn, and every result is checked to be a
SUCCESS before its sample is kept.

**Why Presidio is loaded before the timing window.** The first redact() in a
process pays for the spaCy `en_core_web_lg` load, which is not latency and must
not be counted as it: STORY-014 measured 67.73s to 61.70s from that mistake
alone. `pii_redactor.load()` runs first, and one iteration of every arm is run
and discarded before the measured ones.

This script writes rows (a user, a session, its transcript, and one audit row
per pipeline send). It refuses a non-local `DATABASE_URL` unless told otherwise,
and deletes the session it created on the way out.

Usage:

    python scripts/measure_history_latency.py
    python scripts/measure_history_latency.py --exchanges 20 --sends 30
    python scripts/measure_history_latency.py --database-url http://127.0.0.1:8080
    python scripts/measure_history_latency.py --show-corpus

The dev server is the one the suite uses (tests/conftest.py):

    docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
      ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
"""

import argparse
import math
import os
import platform
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Optional, Sequence
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# `app.config.settings` is a module-level singleton built at import time, and
# DATABASE_URL has no default -- so the endpoint has to be in the environment
# *before* the first `app.` import, not after argparse has run.
# tests/conftest.py:42-57 solves it the same way. Hence this small peek at argv
# ahead of the real parser: do not "tidy" the imports back above it.
_DEFAULT_ENDPOINT = "http://127.0.0.1:8080"


def _database_url(argv: Optional[Sequence[str]]) -> str:
    """--database-url, else HARNESS_TEST_LIBSQL_URL, else the dev server."""
    args = list(sys.argv[1:] if argv is None else argv)
    for index, item in enumerate(args):
        if item == "--database-url" and index + 1 < len(args):
            return args[index + 1]
        if item.startswith("--database-url="):
            return item.split("=", 1)[1]
    return os.environ.get("HARNESS_TEST_LIBSQL_URL") or _DEFAULT_ENDPOINT


def _bootstrap_environment(argv: Optional[Sequence[str]] = None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    # Required by Settings() with no default; irrelevant to what is measured,
    # because the upstream call is a stub and no admin route is exercised.
    os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
    os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")
    return endpoint


_ENDPOINT = _bootstrap_environment()

from app.config import settings  # noqa: E402
from app.db import database  # noqa: E402
from app.db.errors import IntegrityError  # noqa: E402
from app.db.models import StoredMessage, User  # noqa: E402
from app.models.messages import Message  # noqa: E402
from app.models.schemas import QuerySuccessResponse  # noqa: E402
from app.services import chat_history, chat_sessions, pii_redactor  # noqa: E402
from app.services.identity import Identity, hash_token  # noqa: E402
from app.services.openrouter_client import OpenRouterResult  # noqa: E402
from app.services.query_pipeline import run_conversation  # noqa: E402

_MODEL = "gpt-4"  # in settings.MODEL_ALLOWLIST's default, so authorize_model passes
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------

# Realistic support-desk traffic in the 300-800 character band AC 1 asks for.
# Roughly one question in three carries PII that settings.PII_ENTITIES actually
# covers (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION), so arm (b) exercises
# the anonymizer rather than only pii_redactor.py:64-65's empty-result return.
# Answers are ordinary prose with no PII: PRD Risk 3 claims assistant turns are
# "already placeholder text and cheap to analyse", and arm (b) is where that
# claim can be confirmed or corrected.
_QUESTIONS = [
    (
        "We are rolling out the new ingest service to the regional clusters next "
        "week and I want to understand the failure modes before we commit. If the "
        "upstream queue backs up beyond the configured high-water mark, does the "
        "service shed load at the edge or does it apply backpressure all the way "
        "to the producers? I have read the design note twice and it describes both "
        "behaviours in different sections, which makes me think one of them is "
        "stale. Please explain which one ships today and what the operator sees."
    ),
    (
        "Maria Gonzalez on the platform team asked me to follow up on the incident "
        "from Tuesday. She can be reached at maria.gonzalez@example.com or on "
        "+1 415 555 0147 if you need the raw traces. The question we could not "
        "settle between us is whether the retry budget is shared across the whole "
        "deployment or scoped per pod. Our dashboards suggest it is shared, since "
        "a single noisy pod exhausted the budget for everyone, but the "
        "documentation says otherwise. Which is authoritative?"
    ),
    (
        "I need to write a runbook entry for the on-call rotation covering what to "
        "do when the write path reports elevated latency but the error rate stays "
        "flat. Walk me through the diagnostic order you would follow: which metric "
        "to check first, what threshold makes it worth paging the database owner, "
        "and at what point rolling back the most recent deploy becomes the right "
        "move rather than a distraction. Assume the reader has shell access but "
        "has never debugged this particular service before."
    ),
    (
        "Our finance team wants a cost projection for the next two quarters and "
        "they keep asking me questions I cannot answer from the billing export "
        "alone. Specifically, is the per-request charge applied to requests that "
        "fail authorization, or only to those that reach the upstream provider? "
        "And when a request is served from a cache, does it still count against "
        "the monthly quota? I would rather give them one correct answer now than "
        "three approximate ones over the next fortnight."
    ),
    (
        "Tom Whitfield in the Manchester office reported that his session drops "
        "roughly every twenty minutes, always mid-request, and always with the "
        "same generic message. Nobody else in that office sees it. He is on the "
        "same build as the rest of the team and his token was reissued last "
        "Thursday. Before I escalate this to the networking group I would like to "
        "rule out anything on our side: what state does the server hold per "
        "session, and what would cause it to be discarded early?"
    ),
    (
        "The migration plan assumes we can run the old and new schema side by side "
        "for a fortnight while we verify the backfill. That only works if writes "
        "land in both places without the application knowing which one is "
        "authoritative. Is dual-write something the storage layer supports "
        "directly, or is it something each caller has to implement? If it is the "
        "latter, I would like to know how many call sites we are talking about "
        "before I promise a timeline to anyone above me."
    ),
]

_ANSWERS = [
    (
        "It applies backpressure to the producers, and the section describing edge "
        "shedding is stale documentation left over from the first prototype. When "
        "the queue passes the high-water mark, the accept loop stops acknowledging "
        "new work and producers see their send calls block rather than fail. An "
        "operator watching the dashboard sees queue depth plateau at the mark and "
        "producer-side latency climb, with no increase in the error rate. If you "
        "need shedding instead, that is a configuration change, not a code change."
    ),
    (
        "The retry budget is shared across the deployment, which matches what your "
        "dashboards showed rather than what the documentation claims. It is "
        "tracked in the shared limiter, so one pod issuing a burst of retries can "
        "exhaust the allowance for every other pod behind the same limiter. The "
        "documented per-pod behaviour was the original intent and never shipped. "
        "Treat the observed behaviour as authoritative and file the doc bug."
    ),
    (
        "Start with the queue depth on the write path, because it separates a slow "
        "downstream from a slow local process within about thirty seconds. If "
        "depth is flat, the delay is local and the next check is garbage "
        "collection pauses. If depth is climbing, move to the database. Page the "
        "owner once sustained latency passes the agreed threshold for five "
        "consecutive minutes. A rollback is right only when the latency began "
        "within an hour of a deploy and the metric has not recovered on its own."
    ),
    (
        "Requests that fail authorization are not charged, because the charge is "
        "recorded only after a response is received from the provider. Cached "
        "responses are also not charged and do not count against the monthly "
        "quota, since no upstream call is made. What does count is a request that "
        "reaches the provider and then fails: the provider bills it and so do we. "
        "That last case is the one that usually surprises finance teams."
    ),
    (
        "The server holds very little per session, which is what makes a "
        "twenty-minute cadence suspicious. Session state is a token, a role and a "
        "last-seen timestamp, and none of those expire on that interval. A "
        "regular twenty-minute drop that affects exactly one location almost "
        "always turns out to be an idle-connection timeout on intermediate "
        "network equipment. Escalating to the networking group is the right call."
    ),
    (
        "Dual-write is not something the storage layer provides; each caller would "
        "have to implement it, and there are more call sites than the plan "
        "assumes. Before promising a timeline, count the write paths rather than "
        "the services, because several services write through more than one. The "
        "alternative worth considering is replaying from the change log into the "
        "new schema, which needs no caller changes at all and removes the "
        "side-by-side window from the critical path entirely."
    ),
]


def _corpus(exchanges: int) -> list[tuple[str, str]]:
    """`exchanges` question/answer pairs, cycling the pools deterministically."""
    pairs = []
    for index in range(exchanges):
        question = _QUESTIONS[index % len(_QUESTIONS)]
        answer = _ANSWERS[index % len(_ANSWERS)]
        pairs.append((question, answer))
    return pairs


def _unique_question(index: int, nonce: str, arm: str) -> str:
    """A question no earlier send has asked, so the dedup check cannot fire.

    dedup_key hashes the whole conversation (app/services/duplicate_checker.py),
    so varying the last turn is enough. The suffix is short enough to keep the
    text inside AC 1's 300-800 character band.
    """
    base = _QUESTIONS[index % len(_QUESTIONS)]
    return f"{base} [{arm} {nonce} #{index}]"


# --------------------------------------------------------------------------
# Statement recording -- tests/test_two_instance_smoke.py:190-214, copied
# rather than imported: scripts/ must not depend on the test tree.
# --------------------------------------------------------------------------


class Recording:
    """A connection proxy that records the SQL issued through it.

    `__enter__`/`__exit__` are not decoration: `database._session()` does
    `with conn:`, so a proxy without them turns every write into an
    AttributeError instead of a measurement.
    """

    def __init__(self, conn, statements):
        self._conn = conn
        self._statements = statements

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, sql, *parameters):
        self._statements.append(sql)
        return self._conn.execute(sql, *parameters)

    def cursor(self):
        return self._conn.cursor()


def _statements_of(work: Callable[[], object]) -> tuple[object, list[str]]:
    """Runs work(), returning its result and the SQL statements it issued."""
    statements: list[str] = []
    real = database.get_connection
    database.get_connection = lambda: Recording(real(), statements)
    try:
        result = work()
    finally:
        database.get_connection = real
    return result, statements


# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------


class Samples:
    """Wall-clock samples for one arm, summarised the way the report needs."""

    def __init__(self, label: str):
        self.label = label
        self.values: list[float] = []

    def add(self, milliseconds: float) -> None:
        self.values.append(milliseconds)

    @property
    def n(self) -> int:
        return len(self.values)

    def summary(self) -> tuple[float, float, float]:
        """(min, p50, p95) in milliseconds.

        p50 is the median. p95 is the *nearest-rank* percentile --
        sorted[ceil(0.95 * n) - 1] -- which at n=30 is the 29th of 30 sorted
        samples. Named here because the repo has no percentile precedent and
        the report quotes these numbers: a different method would move p95 by
        a whole sample at this n.
        """
        ordered = sorted(self.values)
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
        return min(ordered), statistics.median(ordered), p95


def _timed(work: Callable[[], object]) -> tuple[object, float]:
    """(result, elapsed_ms) -- tests/test_two_instance_smoke.py:217-228's idiom."""
    started = time.perf_counter()
    result = work()
    return result, (time.perf_counter() - started) * 1000


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------


def _guard_local(endpoint: str, allow_remote: bool) -> None:
    if allow_remote:
        return
    host = urlsplit(endpoint).hostname or ""
    if host in _LOCAL_HOSTS:
        return
    raise SystemExit(
        f"Refusing to seed a non-local database: {endpoint}\n"
        "This script writes a user, a chat session, its transcript and one audit "
        "row per send. Point --database-url at the local libSQL dev server, or "
        "pass --allow-remote-database if you are certain."
    )


def _seed(identity: Identity, exchanges: int) -> str:
    """A session with `exchanges` answered exchanges, through the real write path.

    One `assistant` row *is* one exchange: `row.prompt` is the raw question and
    `row.content` the redacted reply, which is what lets `assemble` rebuild a
    pair from each (app/services/chat_history.py:109-117). Mirrors
    tests/test_chat_history.py:67-97.
    """
    database.init_db()

    try:
        database.insert_user(
            User(
                user_id=identity.user_id,
                role=identity.role,
                token_hash=hash_token(f"{identity.user_id}-measurement-token"),
            )
        )
    except IntegrityError:
        pass  # left over from an earlier run; the row is what matters, not who wrote it

    session_id = chat_sessions.create(
        identity, "STORY-015 latency bench", lambda prompt: "STORY-015 latency bench"
    )
    if session_id is None:
        raise SystemExit(
            "CHAT_HISTORY_ENABLED is false, so no session can be created and "
            "there is no history path to measure. Set it true and re-run."
        )

    for question, answer in _corpus(exchanges):
        chat_sessions.append_message(
            identity,
            session_id,
            StoredMessage(
                session_id=session_id,
                kind="assistant",
                content=answer,
                prompt=question,
            ),
        )
    return session_id


# --------------------------------------------------------------------------
# The arms
# --------------------------------------------------------------------------


def _stub_upstream(span: list[float]) -> Callable[..., OpenRouterResult]:
    """A stub that records its own wall clock, so arm (c) can subtract it.

    Three parameters only: run_conversation forwards `params=` solely when it is
    set (app/services/query_pipeline.py:286-298), and this script passes none.
    Mirrors tests/test_pipeline_concurrency.py:179.
    """

    def call(messages, model=_MODEL, api_key=None) -> OpenRouterResult:
        started = time.perf_counter()
        result = OpenRouterResult(
            response=(
                "That behaviour is configuration-dependent, and the short answer "
                "is that the deployed build applies backpressure rather than "
                "shedding load at the edge."
            ),
            model_used=model,
            tokens_used=64,
        )
        span.append((time.perf_counter() - started) * 1000)
        return result

    return call


def _redact_all(messages: Sequence[Message]) -> None:
    """Step 6 of the pipeline, reproduced.

    app/services/query_pipeline.py:265-284 redacts every message on every send
    (D5). It is not separately callable, so it is reproduced here; this comment
    is the only thing stopping the two drifting silently apart.
    """
    for message in messages:
        pii_redactor.redact(message.content)


def _run_pipeline_excluding_upstream(
    identity: Identity, messages: Sequence[Message], session_id: Optional[str]
) -> float:
    """One send. Returns milliseconds spent in run_conversation minus the stub.

    The result is checked to be a SUCCESS: a send silently answered by the
    duplicate arm would skip redaction and upstream entirely, and would be the
    single easiest way for this script to report a fast, meaningless number.
    """
    span: list[float] = []
    result, elapsed_ms = _timed(
        lambda: run_conversation(
            identity,
            messages,
            None,
            _MODEL,
            None,
            call_openrouter=_stub_upstream(span),
            session_id=session_id,
        )
    )
    if not isinstance(result, QuerySuccessResponse):
        raise SystemExit(
            f"Expected SUCCESS, got {type(result).__name__}: {result!r}\n"
            "A blocked send skips redaction and upstream, so its timing measures "
            "nothing. Check the unique-turn suffix in _unique_question()."
        )
    return elapsed_ms - sum(span)


def _measure(
    identity: Identity, session_id: str, sends: int
) -> tuple[dict[str, Samples], list[Message]]:
    """Every arm, warmed once and then timed `sends` times."""
    nonce = uuid.uuid4().hex[:8]
    arms = {
        "assemble": Samples("(a) assemble + fit"),
        "redact_history": Samples("(b) redact all messages"),
        "pipeline_history": Samples("(c) run_conversation excl. upstream"),
        "redact_single": Samples("(b') redact one message"),
        "pipeline_single": Samples("(c') run_conversation excl. upstream"),
    }

    # The first redact() in a process loads the spaCy model, and the first
    # libSQL round trip opens the stream. Neither is latency.
    pii_redactor.load()
    warm_history = chat_history.assemble(identity, session_id)
    _redact_all(warm_history)
    _run_pipeline_excluding_upstream(
        identity,
        warm_history + [Message("user", _unique_question(0, nonce, "warm-multi"))],
        session_id,
    )
    _run_pipeline_excluding_upstream(
        identity, [Message("user", _unique_question(0, nonce, "warm-single"))], session_id
    )

    last_conversation: list[Message] = []
    for index in range(sends):
        question = _unique_question(index, nonce, "multi")
        new_turn = Message("user", question)

        # (a) one live messages_for read, plus the pure fit() the chat does
        # with its result (app/services/chat_history.py:178-196).
        def assemble_and_fit():
            history = chat_history.assemble(identity, session_id)
            return chat_history.fit(
                history,
                new_turn,
                settings.CONTEXT_MAX_MESSAGES,
                settings.CONTEXT_MAX_CHARACTERS,
            )

        (conversation, _dropped), elapsed = _timed(assemble_and_fit)
        arms["assemble"].add(elapsed)
        last_conversation = conversation

        # (b) the redaction loop over the whole conversation
        _, elapsed = _timed(lambda: _redact_all(conversation))
        arms["redact_history"].add(elapsed)

        # (c) the whole pipeline for that conversation, minus the stub
        arms["pipeline_history"].add(
            _run_pipeline_excluding_upstream(identity, conversation, session_id)
        )

        # (d) the same two measurements for a single-turn send
        single = [Message("user", _unique_question(index, nonce, "single"))]
        _, elapsed = _timed(lambda: _redact_all(single))
        arms["redact_single"].add(elapsed)
        arms["pipeline_single"].add(
            _run_pipeline_excluding_upstream(identity, single, session_id)
        )

    return arms, last_conversation


def _statement_comparison(
    identity: Identity, session_id: str
) -> tuple[list[str], list[str]]:
    """The SQL a history send issues, against a single-turn send. Untimed.

    AC 2's indicator is phrased as "one `messages_for` read plus per-turn
    redaction". Latency is context; the statement list is what actually proves
    the *read* half, and counts are the assertable number in this repo
    (tests/test_two_instance_smoke.py:1225-1246).
    """
    nonce = uuid.uuid4().hex[:8]

    def history_send():
        history = chat_history.assemble(identity, session_id)
        conversation, _ = chat_history.fit(
            history,
            Message("user", _unique_question(1, nonce, "stmt-multi")),
            settings.CONTEXT_MAX_MESSAGES,
            settings.CONTEXT_MAX_CHARACTERS,
        )
        return _run_pipeline_excluding_upstream(identity, conversation, session_id)

    def single_send():
        return _run_pipeline_excluding_upstream(
            identity,
            [Message("user", _unique_question(1, nonce, "stmt-single"))],
            session_id,
        )

    _, history_statements = _statements_of(history_send)
    _, single_statements = _statements_of(single_send)
    return history_statements, single_statements


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _first_words(statements: Sequence[str]) -> str:
    """"SELECT chat_messages, SELECT audit_logs, INSERT audit_logs".

    The verb alone would not distinguish the read `assemble` adds from the
    duplicate check's, and that distinction is the whole point of the
    comparison, so the table is named too.
    """
    described = []
    for statement in statements:
        words = statement.split()
        verb = words[0].upper()
        table = ""
        for index, word in enumerate(words):
            if word.upper() in {"FROM", "INTO", "UPDATE"} and index + 1 < len(words):
                table = " " + words[index + 1].strip("(),")
                break
        described.append(f"{verb}{table}")
    return ", ".join(described)


def _table(rows: Sequence[tuple[str, Samples]]) -> list[str]:
    lines = [
        "| arm | n | min (ms) | p50 (ms) | p95 (ms) |",
        "|-----|---|----------|----------|----------|",
    ]
    for label, samples in rows:
        low, p50, p95 = samples.summary()
        lines.append(
            f"| {label} | {samples.n} | {low:.2f} | {p50:.2f} | {p95:.2f} |"
        )
    return lines


def _report(
    arms: dict[str, Samples],
    conversation: Sequence[Message],
    exchanges: int,
    sends: int,
    endpoint: str,
    history_statements: Sequence[str],
    single_statements: Sequence[str],
) -> str:
    characters = sum(len(m.content) for m in conversation)
    lines = [
        "",
        "--- STORY-015 history latency (PRD-010 Section 11, Risk 3) ---",
        "",
        f"  endpoint             : {endpoint} (same host)",
        f"  python               : {platform.python_version()} on {platform.system()}",
        f"  exchanges seeded     : {exchanges}",
        f"  sends per arm        : {sends} (plus one discarded warm iteration)",
        f"  conversation sent    : {len(conversation)} messages, {characters} characters",
        f"  CONTEXT_MAX_MESSAGES : {settings.CONTEXT_MAX_MESSAGES}",
        f"  CONTEXT_MAX_CHARACTERS: {settings.CONTEXT_MAX_CHARACTERS}",
        f"  PII_REDACTION_ENABLED: {settings.PII_REDACTION_ENABLED}",
        f"  PII_NLP_MODEL        : {settings.PII_NLP_MODEL}",
        f"  PII_ENTITIES         : {settings.PII_ENTITIES}",
        f"  redact() calls/send  : {len(conversation)} history+new, +1 on the response",
        "",
        f"  history send SQL     : {_first_words(history_statements)}",
        f"  single-turn send SQL : {_first_words(single_statements)}",
        "",
        "  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1].",
        "  No latency here is asserted as a pass/fail bound.",
        "",
    ]

    lines.append(f"  History path ({exchanges} exchanges):")
    lines.extend("  " + row for row in _table([
        (arms["assemble"].label, arms["assemble"]),
        (arms["redact_history"].label, arms["redact_history"]),
        (arms["pipeline_history"].label, arms["pipeline_history"]),
    ]))
    lines.append("")
    lines.append("  Single-turn baseline:")
    lines.append(
        "  (a') assemble + fit: n/a -- a single-turn send reads no history, "
        "which is the whole of the difference arm (a) measures."
    )
    lines.extend("  " + row for row in _table([
        (arms["redact_single"].label, arms["redact_single"]),
        (arms["pipeline_single"].label, arms["pipeline_single"]),
    ]))
    lines.append("")

    _, history_p50, history_p95 = arms["pipeline_history"].summary()
    _, single_p50, single_p95 = arms["pipeline_single"].summary()
    _, assemble_p50, _ = arms["assemble"].summary()
    _, redact_history_p50, _ = arms["redact_history"].summary()
    _, redact_single_p50, _ = arms["redact_single"].summary()
    added_p50 = history_p50 - single_p50
    accounted = assemble_p50 + (redact_history_p50 - redact_single_p50)

    lines.extend(
        [
            f"  added per send (p50) : {added_p50:.2f} ms "
            f"({history_p50:.2f} - {single_p50:.2f})",
            f"  added per send (p95) : {history_p95 - single_p95:.2f} ms",
            f"  accounted for by     : {accounted:.2f} ms "
            f"= assemble {assemble_p50:.2f} + extra redaction "
            f"{redact_history_p50 - redact_single_p50:.2f}",
            "",
        ]
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _measure_command(args: argparse.Namespace) -> int:
    if args.show_corpus:
        for index, (question, answer) in enumerate(_corpus(args.exchanges)):
            unique = _unique_question(index, "0" * 8, "multi")
            print(
                f"{index:>3}  question {len(question):>4} chars "
                f"(with suffix {len(unique):>4})  answer {len(answer):>4} chars"
            )
        return 0

    _guard_local(_ENDPOINT, args.allow_remote_database)

    if not settings.PII_REDACTION_ENABLED:
        print(
            "PII_REDACTION_ENABLED is false, so redact() returns its input "
            "untouched and arm (b) would measure nothing. Set it true and re-run.",
            file=sys.stderr,
        )
        return 1

    identity = Identity(user_id=args.user_id, role="user")
    session_id = _seed(identity, args.exchanges)
    try:
        arms, conversation = _measure(identity, session_id, args.sends)
        history_statements, single_statements = _statement_comparison(
            identity, session_id
        )
        print(
            _report(
                arms,
                conversation,
                args.exchanges,
                args.sends,
                _ENDPOINT,
                history_statements,
                single_statements,
            )
        )
    finally:
        if args.keep:
            print(f"  kept session {session_id} (--keep)")
        else:
            removed = chat_sessions.delete(identity, session_id)
            print(f"  cleaned up session {session_id}: {removed}")
            # `audit_logs` is deliberately left alone: no public delete path
            # exists, and database.delete_chat_session explains why -- deleting a
            # conversation does not edit the record of what was asked. Each run
            # uses a fresh nonce, so the rows left behind cannot collide with a
            # later run's dedup keys.
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the added per-send latency of history assembly and per-turn "
            "redaction (PRD-010 STORY-015). Records numbers; asserts none."
        )
    )
    parser.add_argument(
        "--exchanges", type=int, default=20, help="answered exchanges to seed (default 20)"
    )
    parser.add_argument(
        "--sends", type=int, default=30, help="timed sends per arm (default 30)"
    )
    parser.add_argument(
        "--database-url",
        default=_ENDPOINT,
        help=(
            "libSQL endpoint to measure against; read before argparse runs "
            "(default: $HARNESS_TEST_LIBSQL_URL or " + _DEFAULT_ENDPOINT + ")"
        ),
    )
    parser.add_argument(
        "--user-id", default="story015-bench", help="bench user id (default story015-bench)"
    )
    parser.add_argument(
        "--keep", action="store_true", help="leave the seeded session behind"
    )
    parser.add_argument(
        "--allow-remote-database",
        action="store_true",
        help="seed a non-local DATABASE_URL (refused by default)",
    )
    parser.add_argument(
        "--show-corpus", action="store_true", help="print corpus lengths and exit"
    )
    parser.set_defaults(func=_measure_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
