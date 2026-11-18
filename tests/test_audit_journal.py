"""The on-disk audit journal (PRD-018 STORY-008, Section 6.8, D9, D10, D13).

Pure: no database, no settings, `tmp_path` only. Runs on Windows and Linux;
the POSIX-only mode assertions skip explicitly on Windows. Every journal a test
opens is closed by the `journals` fixture, and the module slot is checked
before and reset after every test so nothing leaks between them.
"""

import dataclasses
import errno
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.db import audit_journal
from app.db.audit_journal import AuditJournal, _JOURNAL_ENTRY_RESERVE_BYTES
from app.db.errors import AuditUnavailableError, StorageError
from app.db.models import ActionDecisionRow, AuditLog

_LOG = "app.db.audit_journal"
_REPO = Path(__file__).resolve().parents[1]
_SENTINEL = "SENTINEL-SECRET-PROMPT-TEXT"


@pytest.fixture(autouse=True)
def _slot_clean():
    assert audit_journal.current() is None
    yield
    audit_journal.close_journal()


@pytest.fixture
def journals(tmp_path):
    opened: list[AuditJournal] = []

    def _open(directory=None, max_bytes=1 << 20, workers=2) -> AuditJournal:
        journal = AuditJournal(str(directory or tmp_path / "buf"), max_bytes, workers)
        opened.append(journal)
        return journal

    yield _open
    for journal in opened:
        journal.close()


def _audit(write_id="w" * 32, **overrides) -> AuditLog:
    base = dict(timestamp="2026-11-17T10:00:00Z", user_id="u1", prompt_hash="h", write_id=write_id)
    return AuditLog(**{**base, **overrides})


def _decision(index=0, batch="b" * 32, **overrides) -> ActionDecisionRow:
    base = dict(
        timestamp="2026-11-17T10:00:00Z", audit_id=None, session_id=None, user_id="u1", role="user",
        tool_call_id="call_1", tool_name="run", operation_kind=None, target_preview=None,
        arguments_hash="ah", arguments_preview=None, decision="allow", rule="r", reason="why",
        granted_by=None, classifications="[]", policy_digest="pd", write_id=f"{batch}:{index}",
    )
    return ActionDecisionRow(**{**base, **overrides})


def _lines(path: Path) -> list[bytes]:
    return [line for line in path.read_bytes().split(b"\n") if line]


def _verifies(line: bytes) -> bool:
    obj = json.loads(line)
    claimed = obj.pop("sha256")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest() == claimed


def _errors(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _LOG and r.levelno == logging.ERROR]


def _orphan(tmp_path, journals, count=3) -> tuple[Path, Path]:
    """Write `count` entries to a journal, close it (file stays), return (dir, file)."""
    directory = tmp_path / "buf"
    first = journals(directory)
    for i in range(count):
        first.append(_audit(write_id=f"{i:032d}", prompt_preview=f"p{i}"))
    path = first.path
    first.close()
    return directory, path


def test_append_writes_one_checksummed_line_with_the_documented_keys(journals):
    journal = journals()
    entry = journal.append(_audit(prompt_preview="hi"))

    lines = _lines(journal.path)
    assert len(lines) == 1 and _verifies(lines[0])
    obj = json.loads(lines[0])
    assert set(obj) == {"v", "write_id", "appended_at", "audit", "audit_id", "decisions", "sha256"}
    assert obj["v"] == 1 and obj["audit_id"] is None and obj["write_id"] == entry.write_id
    assert "id" not in obj["audit"]


def test_append_flushes_then_fsyncs_before_returning(journals, monkeypatch):
    journal = journals()
    real_fsync = os.fsync
    seen = []

    def recorder(fd):
        # A separate handle sees only flushed bytes: size == full line proves flush() came first.
        seen.append((fd, journal.path.stat().st_size))
        real_fsync(fd)

    monkeypatch.setattr(audit_journal.os, "fsync", recorder)
    journal.append(_audit())

    assert len(seen) == 1  # fsync had already run when append returned
    assert seen[0][1] == journal.path.stat().st_size > 0


def test_a_failed_fsync_raises_audit_unavailable_and_leaves_no_partial_line(journals, monkeypatch):
    journal = journals()
    journal.append(_audit(write_id="a" * 32))
    size = journal.path.stat().st_size
    real_fsync = os.fsync
    calls = []

    def flaky(fd):
        calls.append(fd)
        if len(calls) == 1:
            raise OSError(errno.EIO, "disk")
        real_fsync(fd)

    monkeypatch.setattr(audit_journal.os, "fsync", flaky)
    with pytest.raises(AuditUnavailableError) as exc_info:
        journal.append(_audit(write_id="b" * 32))
    assert isinstance(exc_info.value, StorageError)
    assert journal.path.stat().st_size == size
    assert journal.entries() == 1

    monkeypatch.setattr(audit_journal.os, "fsync", real_fsync)
    journal.append(_audit(write_id="c" * 32))
    assert all(_verifies(line) for line in _lines(journal.path)) and len(_lines(journal.path)) == 2


def test_append_that_would_exceed_max_bytes_writes_nothing(journals, tmp_path):
    probe = journals(tmp_path / "probe")
    probe.append(_audit())
    size = probe.bytes()

    journal = journals(tmp_path / "small", max_bytes=size + size // 2)
    journal.append(_audit(write_id="a" * 32))
    before = journal.path.read_bytes()
    with pytest.raises(AuditUnavailableError, match="AUDIT_BUFFER_MAX_BYTES"):
        journal.append(_audit(write_id="b" * 32))
    assert journal.path.read_bytes() == before
    assert journal.entries() == 1


def test_depth_queries_and_headroom(journals, tmp_path, monkeypatch):
    monkeypatch.setattr(audit_journal, "_utc_now", lambda: "2026-11-17T10:00:01Z")
    probe = journals(tmp_path / "probe")
    probe.append(_audit())
    size = probe.bytes()
    reserve = 2 * _JOURNAL_ENTRY_RESERVE_BYTES

    ok = journals(tmp_path / "ok", max_bytes=size + reserve, workers=2)
    tight = journals(tmp_path / "tight", max_bytes=size - 1 + reserve, workers=2)
    assert ok.headroom_ok() and tight.headroom_ok()  # empty
    ok.append(_audit())
    tight.append(_audit())
    assert ok.bytes() == ok.path.stat().st_size == size
    assert ok.headroom_ok() is True  # bytes == max - workers * reserve exactly
    assert tight.headroom_ok() is False  # one byte over

    status = ok.status()
    assert (status.entries, status.bytes, status.max_bytes) == (1, size, size + reserve)
    assert status.reserve_bytes == 65536 and status.oldest_timestamp == "2026-11-17T10:00:01Z"
    assert ok.entries() == 1 and ok.oldest_timestamp() == "2026-11-17T10:00:01Z"
    assert journals(tmp_path / "empty").oldest_timestamp() is None


def _generated(cls, excluded):
    values = {}
    for n, f in enumerate(dataclasses.fields(cls), start=1):
        if f.name in excluded:
            continue
        kind = str(f.type)
        if "bool" in kind:
            values[f.name] = not f.default
        elif "int" in kind:
            values[f.name] = 1000 + n
        else:
            values[f.name] = f"{f.name}-{n}-é中"
    return values


def test_entry_round_trips_every_dataclass_field(journals, tmp_path):
    audit_values = _generated(AuditLog, {"id"})
    decision_values = _generated(ActionDecisionRow, {"audit_id", "id"})
    first = journals(tmp_path / "buf")
    first.append(AuditLog(**audit_values), (ActionDecisionRow(audit_id=None, **decision_values),))
    path = first.path
    first.close()

    obj = json.loads(_lines(path)[0])
    # A field added to either dataclass later is carried automatically, or this fails.
    assert set(obj["audit"]) == {f.name for f in dataclasses.fields(AuditLog)} - {"id"}
    assert set(obj["decisions"][0]) == {f.name for f in dataclasses.fields(ActionDecisionRow)} - {"audit_id", "id"}

    second = journals(tmp_path / "buf")
    assert second.adopt() == 1
    (entry,) = second.pending()
    assert entry.audit == AuditLog(**audit_values)
    assert entry.decisions[0] == ActionDecisionRow(audit_id=None, **decision_values)


def test_decisions_only_entry_carries_audit_id_and_null_audit(journals, tmp_path):
    first = journals(tmp_path / "buf")
    entry = first.append(None, (_decision(0), _decision(1)), audit_id=42, write_id="b" * 32)
    assert entry.write_id == "b" * 32
    obj = json.loads(_lines(first.path)[0])
    assert obj["audit"] is None and obj["audit_id"] == 42 and len(obj["decisions"]) == 2
    first.close()
    second = journals(tmp_path / "buf")
    second.adopt()
    (loaded,) = second.pending()
    assert loaded.audit is None and [d.audit_id for d in loaded.decisions] == [42, 42]


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(audit=_audit(write_id="")),
        dict(audit=_audit(id=5)),
        dict(audit=_audit(), audit_id=3),
        dict(audit=_audit(), write_id="other"),
        dict(audit=None, decisions=(_decision(),), audit_id=None, write_id="b" * 32),
        dict(audit=None, decisions=(), audit_id=1, write_id="b" * 32),
        dict(audit=None, decisions=(_decision(),), audit_id=1, write_id=None),
        dict(audit=_audit(), decisions=(_decision(write_id=None),)),
        dict(audit=_audit(), decisions=(_decision(id=9),)),
    ],
)
def test_append_rejects_a_malformed_entry(journals, kwargs):
    journal = journals()
    with pytest.raises(ValueError):
        journal.append(**kwargs)
    assert journal.entries() == 0 and journal.path.stat().st_size == 0


def test_file_name_and_second_opener_cannot_lock(journals):
    journal = journals()
    assert re.fullmatch(r"audit-journal-[A-Za-z0-9._-]+-\d+-[0-9a-f]{32}\.jsonl", journal.path.name)
    assert f"-{os.getpid()}-" in journal.path.name
    journal.append(_audit())

    fd = os.open(journal.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        assert audit_journal._try_lock(fd) is False
    finally:
        os.close(fd)
    assert len(_lines(journal.path)) == 1  # data stays readable under the lock

    path = journal.path
    journal.close()
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        assert audit_journal._try_lock(fd) is True  # released on close
    finally:
        os.close(fd)


_CHILD = """
import sys
from app.db import audit_journal as j
from app.db.models import AuditLog
journal = j.open_journal(sys.argv[1], 1 << 20, 2)
journal.append(AuditLog(timestamp="t", user_id="child", prompt_hash="h", write_id="c" * 32))
print(journal.path, flush=True)
sys.stdin.readline()
"""


def test_adopt_skips_a_file_locked_by_a_live_process(journals, tmp_path, caplog):
    directory = tmp_path / "buf"
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(directory)],
        cwd=_REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    try:
        child.stdout.readline()
        parent = journals(directory)
        with caplog.at_level(logging.INFO, logger=_LOG):
            assert parent.adopt() == 0
        assert "reason=locked" in caplog.text and parent.entries() == 0

        child.stdin.write(b"\n")
        child.stdin.flush()
        child.wait(timeout=30)
        assert parent.adopt() == 1
        assert [e.audit.user_id for e in parent.pending()] == ["child"]
    finally:
        child.kill()
        child.wait()


def test_torn_tail_partial_line_is_discarded_with_one_error(journals, tmp_path, caplog):
    directory, path = _orphan(tmp_path, journals)
    with open(path, "ab") as f:
        f.write(b'{"v":1,"write_id":"zz')  # no newline: never acknowledged
    second = journals(directory)
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        assert second.adopt() == 1
    assert [e.write_id for e in second.pending()] == [f"{i:032d}" for i in range(3)]
    errors = _errors(caplog)
    assert len(errors) == 1 and "reason=torn_tail" in errors[0].getMessage() and "write_id=-" in errors[0].getMessage()
    assert second.status().torn_tail_discarded == 1
    assert "p0" not in caplog.text


def test_torn_tail_bad_checksum_last_line_is_discarded_with_one_error(journals, tmp_path, caplog):
    directory, path = _orphan(tmp_path, journals)
    data = path.read_bytes()
    head, last, _ = data.rsplit(b"\n", 2)[0], data.rsplit(b"\n", 2)[1], b""
    path.write_bytes(head + b"\n" + last.replace(b'"user_id":"u1"', b'"user_id":"u2"') + b"\n")
    second = journals(directory)
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        assert second.adopt() == 1
    assert [e.write_id for e in second.pending()] == [f"{i:032d}" for i in range(2)]
    errors = _errors(caplog)
    assert len(errors) == 1 and f"write_id={2:032d}" in errors[0].getMessage()
    assert "reason=torn_tail" in errors[0].getMessage() and "p2" not in caplog.text


def test_corrupt_non_last_line_leaves_the_whole_file_untouched(journals, tmp_path, caplog):
    directory, path = _orphan(tmp_path, journals)
    lines = path.read_bytes().split(b"\n")
    lines[1] = lines[1].replace(b'"user_id":"u1"', b'"user_id":"u2"')
    damaged = b"\n".join(lines)
    path.write_bytes(damaged)

    second = journals(directory)
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        assert second.adopt() == 0
    errors = _errors(caplog)
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "reason=corrupt" in message and "line=2" in message and path.name in message
    assert f"write_id={1:032d}" in message and "p1" not in caplog.text
    assert second.entries() == 0 and second.status().held_back_files == 1
    assert path.read_bytes() == damaged  # not compacted, not deleted
    os.remove(path)  # and its lock was released (a held file could not be removed on Windows)


def test_checksum_valid_but_undecodable_line_leaves_the_file_untouched(journals, tmp_path, caplog):
    directory, path = _orphan(tmp_path, journals, count=1)
    obj = json.loads(_lines(path)[0])
    obj.pop("sha256")
    obj["v"] = 2
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    obj["sha256"] = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    future = (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    path.write_bytes(future)

    second = journals(directory)
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        assert second.adopt() == 0
    errors = _errors(caplog)
    assert len(errors) == 1 and "reason=undecodable" in errors[0].getMessage() and "line=1" in errors[0].getMessage()
    assert path.read_bytes() == future


def test_mark_drained_advances_the_checkpoint_and_compacts_to_zero(journals, tmp_path):
    journal = journals(tmp_path / "buf")
    for i in range(3):
        journal.append(_audit(write_id=f"{i:032d}"))
    ends = []
    offset = 0
    for line in _lines(journal.path):
        offset += len(line) + 1
        ends.append(offset)

    journal.mark_drained(f"{0:032d}")
    sidecar = journal.path.with_name(journal.path.name + ".checkpoint")
    assert int(sidecar.read_text()) == ends[0]
    assert [e.write_id for e in journal.pending()] == [f"{1:032d}", f"{2:032d}"]
    with pytest.raises(KeyError):
        journal.mark_drained("unknown")

    path = journal.path
    journal.close()  # a restart after a partial drain: the checkpoint is honoured
    second = journals(tmp_path / "buf")
    assert second.adopt() == 1
    assert [e.write_id for e in second.pending()] == [f"{1:032d}", f"{2:032d}"]

    # Drain through the adopted file: deleted once empty, with its sidecar.
    second.mark_drained(f"{1:032d}")
    second.mark_drained(f"{2:032d}")
    assert not path.exists() and not sidecar.exists() and second.adopted_files() == 0

    # Own file: out-of-order drain still compacts to zero bytes.
    for i in range(3):
        second.append(_audit(write_id=f"{i:032d}"))
    own = second.path
    second.mark_drained(f"{2:032d}")
    assert not own.with_name(own.name + ".checkpoint").exists()  # prefix not drained yet
    second.mark_drained(f"{0:032d}")
    second.mark_drained(f"{1:032d}")
    assert own.stat().st_size == 0 and second.bytes() == 0 and second.entries() == 0
    assert not own.with_name(own.name + ".checkpoint").exists()
    second.append(_audit(write_id="d" * 32))
    assert [_verifies(line) for line in _lines(own)] == [True]


def test_adopted_file_with_nothing_pending_is_deleted_at_once(journals, tmp_path):
    directory = tmp_path / "buf"
    first = journals(directory)
    first.append(_audit())
    first.mark_drained("w" * 32)  # compacted to zero, file left behind empty
    path = first.path
    first.close()
    assert path.exists() and path.stat().st_size == 0

    second = journals(directory)
    assert second.adopt() == 1
    assert not path.exists() and second.adopted_files() == 0


def test_adopted_files_count_toward_bytes(journals, tmp_path):
    directory, path = _orphan(tmp_path, journals)
    second = journals(directory)
    second.adopt()
    assert second.adopted_files() == 1 and second.bytes() == path.stat().st_size


def test_pending_audit_rows_indexes_by_user_and_key_and_forgets_on_drain(journals):
    journal = journals()
    journal.append(_audit(write_id="a" * 32, user_id="u1", dedup_key="k1"))
    journal.append(_audit(write_id="b" * 32, user_id="u1", dedup_key="k2"))
    journal.append(_audit(write_id="c" * 32, user_id="u2", dedup_key="k1"))
    journal.append(_audit(write_id="d" * 32, user_id="u1", dedup_key=None))

    rows = journal.pending_audit_rows("u1", "k1")
    assert [r.write_id for r in rows] == ["a" * 32]
    rows[0].success = False  # a copy: the index is unchanged
    assert journal.pending_audit_rows("u1", "k1")[0].success is True
    assert journal.pending_audit_rows("u1", "none") == []
    assert [r.write_id for r in journal.pending_audit_rows("u2", "k1")] == ["c" * 32]

    journal.mark_drained("a" * 32)
    assert journal.pending_audit_rows("u1", "k1") == []


def test_unwritable_directory_is_an_error_naming_the_setting(tmp_path):
    blocker = tmp_path / "f"
    blocker.write_text("a regular file, not a directory")
    with pytest.raises(AuditUnavailableError, match="AUDIT_BUFFER_DIR"):
        AuditJournal(str(blocker / "sub"), 1 << 20, 2)


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes; Windows has no 0700/0600")
def test_directory_is_0700_and_file_0600_on_posix(journals, tmp_path):
    journal = journals(tmp_path / "newdir")
    assert (tmp_path / "newdir").stat().st_mode & 0o777 == 0o700
    assert journal.path.stat().st_mode & 0o777 == 0o600


def test_module_slot_unset_by_default_and_append_fails_closed(tmp_path):
    assert audit_journal.current() is None
    with pytest.raises(AuditUnavailableError, match="not open"):
        audit_journal.append(_audit())

    journal = audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    assert audit_journal.current() is journal
    with pytest.raises(RuntimeError):
        audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    assert audit_journal.append(_audit()).write_id == "w" * 32

    audit_journal.close_journal()
    assert audit_journal.current() is None
    audit_journal.close_journal()  # a no-op when unset
    with pytest.raises(AuditUnavailableError, match="closed"):
        journal.append(_audit(write_id="x" * 32))


def test_import_has_no_side_effect_and_does_not_import_settings(tmp_path):
    code = "import sys, threading; import app.db.audit_journal; print(threading.active_count(), 'app.config' in sys.modules)"
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["1", "False"]  # no thread; no settings import (no cycle)
    assert list(tmp_path.iterdir()) == []


def test_logs_never_contain_contents(journals, tmp_path, caplog):
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        first = journals(tmp_path / "buf")
        first.append(
            _audit(prompt_preview=_SENTINEL, response_preview=_SENTINEL, dedup_key=_SENTINEL),
            (_decision(arguments_preview=_SENTINEL),),
        )
        first.append(_audit(write_id="b" * 32, prompt_preview=_SENTINEL))
        path = first.path
        first.close()
        with open(path, "ab") as f:
            f.write(b'{"torn":"' + _SENTINEL.encode() + b'')
        second = journals(tmp_path / "buf")
        second.adopt()
        second.mark_drained("w" * 32)
        second.mark_drained("b" * 32)
    assert _SENTINEL not in caplog.text and caplog.records


def test_concurrent_appends_all_verify(journals):
    journal = journals(max_bytes=1 << 24, workers=8)
    barrier = threading.Barrier(8)

    def work(worker):
        barrier.wait(timeout=30)
        for i in range(20):
            journal.append(_audit(write_id=f"{worker:016d}{i:016d}"))

    threads = [threading.Thread(target=work, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads)
    lines = _lines(journal.path)
    assert len(lines) == 160 and all(_verifies(line) for line in lines)
    assert journal.entries() == 160


def test_status_reports_the_admission_reserve_as_headroom_bytes(journals):
    """PRD-018 STORY-012 (Section 10): `headroom_bytes` is workers x 64 KiB, the
    reserve admission applies, not the free bytes."""
    journal = journals(workers=3)
    assert journal.status().headroom_bytes == 3 * _JOURNAL_ENTRY_RESERVE_BYTES
    journal.append(_audit())
    assert journal.status().headroom_bytes == 3 * _JOURNAL_ENTRY_RESERVE_BYTES
