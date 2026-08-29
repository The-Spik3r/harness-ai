import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import hashlib
import inspect
import pathlib
import re
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_audit_log, get_connection, init_db, insert_user
from app.db.models import User
from app.main import app
import app.services.audit_logger as audit_logger
import app.services.duplicate_checker as duplicate_checker
import app.services.query_pipeline as query_pipeline
from app.services.duplicate_checker import (
    DuplicateCheckResult,
    check_duplicate,
    hash_prompt,
)
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult
from app.services.pattern_detector import SUSPICIOUS_PATTERNS
from app.services.pii_redactor import redact
from app.services.query_pipeline import run_query

_JUAN_TOKEN = "juan-token"
_MARIA_TOKEN = "maria-token"
_JUAN_HEADERS = {"Authorization": f"Bearer {_JUAN_TOKEN}"}
_MARIA_HEADERS = {"Authorization": f"Bearer {_MARIA_TOKEN}"}

client = TestClient(app)

# Two prompts from two different users, differing ONLY in the email address.
# Both mask to the same text -- PRD User Story 6 / RF-6 is the promise that this
# collision can never reach the dedup hash.
_PROMPT_A = "contact me at a@x.com"
_PROMPT_B = "contact me at b@y.com"
_REDACTED_BOTH = "contact me at <EMAIL_ADDRESS>"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    insert_user(
        User(user_id="juan@empresa.com", role="user", token_hash=hash_token(_JUAN_TOKEN))
    )
    insert_user(
        User(user_id="maria@empresa.com", role="user", token_hash=hash_token(_MARIA_TOKEN))
    )
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")


def _capturing_openrouter(seen: list, response: str = "ok"):
    def _call(prompt, model="gpt-4", api_key=None):
        seen.append(prompt)
        return OpenRouterResult(response=response, model_used=model, tokens_used=5)

    return _call


def test_two_pii_prompts_collide_after_redaction():
    """The hazard RF-6 exists to prevent: distinct prompts, identical once masked."""
    redacted_a, entities_a = redact(_PROMPT_A)
    redacted_b, entities_b = redact(_PROMPT_B)

    assert redacted_a == _REDACTED_BOTH
    assert redacted_b == _REDACTED_BOTH
    assert entities_a == entities_b == ["EMAIL_ADDRESS"]
    # Hashing the REDACTED text would conflate two different customers.
    assert hash_prompt(redacted_a) == hash_prompt(redacted_b)


def test_two_pii_prompts_hash_differently_on_raw_text():
    """The defence: the hash is taken over raw text, so the collision never lands."""
    assert _PROMPT_A != _PROMPT_B
    assert hash_prompt(_PROMPT_A) != hash_prompt(_PROMPT_B)
    assert hash_prompt(_PROMPT_A) != hash_prompt(_REDACTED_BOTH)
    assert hash_prompt(_PROMPT_B) != hash_prompt(_REDACTED_BOTH)


def test_distinct_pii_prompts_are_never_duplicates_of_each_other(temp_db, monkeypatch):
    seen = []
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

    first = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A},
        headers=_JUAN_HEADERS,
    )
    second = client.post(
        "/query",
        json={"user_id": "maria@empresa.com", "prompt": _PROMPT_B},
        headers=_MARIA_HEADERS,
    )

    assert first.json()["status"] == "SUCCESS"
    assert second.json()["status"] == "SUCCESS"
    # OpenRouter literally received the same bytes twice -- and dedup still let both through.
    assert seen == [_REDACTED_BOTH, _REDACTED_BOTH]
    assert _count_audit_rows() == 2


def test_identical_pii_prompt_is_still_blocked_as_duplicate(temp_db, monkeypatch):
    """Control for the test above: dedup is not simply broken in the presence of PII."""
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))
    first = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A},
        headers=_JUAN_HEADERS,
    )
    assert first.json()["status"] == "SUCCESS"

    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    second = client.post(
        "/query",
        json={"user_id": "maria@empresa.com", "prompt": _PROMPT_A},
        headers=_MARIA_HEADERS,
    )

    body = second.json()
    assert body["status"] == "BLOCKED"
    assert body["reason"] == "Duplicate query within 24 hours"


def test_audit_prompt_hashes_are_over_raw_text_not_redacted(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

    first = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A},
        headers=_JUAN_HEADERS,
    )
    second = client.post(
        "/query",
        json={"user_id": "maria@empresa.com", "prompt": _PROMPT_B},
        headers=_MARIA_HEADERS,
    )

    entry_a = get_audit_log(first.json()["audit_id"])
    entry_b = get_audit_log(second.json()["audit_id"])

    assert entry_a.prompt_hash == hash_prompt(_PROMPT_A)
    assert entry_b.prompt_hash == hash_prompt(_PROMPT_B)
    assert entry_a.prompt_hash != entry_b.prompt_hash
    assert entry_a.prompt_hash != hash_prompt(_REDACTED_BOTH)
    assert entry_a.prompt_preview == _PROMPT_A
    assert entry_b.prompt_preview == _PROMPT_B


def _epic_base():
    """Merge-base with `main`, or None when git/history is unavailable."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "main", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _changed_since_epic_base(path: str) -> list:
    base = _epic_base()
    if base is None:
        pytest.skip("git history unavailable; behavioural pins below still apply")
    result = subprocess.run(
        ["git", "diff", "--name-only", base, "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line.strip()]


@pytest.mark.parametrize(
    "path",
    ["app/services/duplicate_checker.py", "app/services/pattern_detector.py"],
)
def test_dedup_and_pattern_sources_unmodified_on_this_branch(path):
    """RF-6: this epic must not touch either module -- working tree included."""
    assert _changed_since_epic_base(path) == []


def test_duplicate_checker_has_no_redaction_dependency():
    source = inspect.getsource(duplicate_checker).lower()

    assert "pii" not in source
    assert "redact" not in source
    assert "presidio" not in source
    assert set(vars(duplicate_checker)) & {"redact", "pii_redactor", "PiiRedactorError"} == set()


def test_hash_prompt_is_plain_sha256_of_utf8_text():
    for text in (_PROMPT_A, _PROMPT_B, _REDACTED_BOTH, "", "acentuación y emoji 🙂"):
        assert hash_prompt(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_check_duplicate_public_contract_is_stable():
    signature = inspect.signature(check_duplicate)

    assert list(signature.parameters) == ["prompt"]
    assert signature.parameters["prompt"].annotation is str
    assert signature.parameters["prompt"].default is inspect.Parameter.empty
    assert signature.return_annotation is DuplicateCheckResult
    assert [field.name for field in DuplicateCheckResult.__dataclass_fields__.values()] == [
        "is_duplicate",
        "first_query_at",
    ]


@pytest.mark.parametrize("pattern", SUSPICIOUS_PATTERNS)
def test_suspicious_pattern_with_pii_blocked_before_redaction(temp_db, monkeypatch, pattern):
    """Pattern blocking is unchanged from PRD-001: it wins, and nothing is analyzed."""
    monkeypatch.setattr(query_pipeline, "redact", _fail_if_called)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query",
        json={
            "user_id": "juan@empresa.com",
            "prompt": f"please {pattern} and contact me at a@x.com",
        },
        headers=_JUAN_HEADERS,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "BLOCKED"
    assert body["reason"] == "Suspicious pattern detected"
    assert body["pattern"] == pattern
    assert _count_audit_rows() == 1


def test_pipeline_runs_both_checks_before_any_redaction(temp_db, monkeypatch):
    calls = []
    real_duplicate = query_pipeline.check_duplicate
    real_pattern = query_pipeline.detect_suspicious_pattern
    real_redact = query_pipeline.redact

    def _spy_duplicate(prompt):
        calls.append(("check_duplicate", prompt))
        return real_duplicate(prompt)

    def _spy_pattern(prompt):
        calls.append(("detect_suspicious_pattern", prompt))
        return real_pattern(prompt)

    def _spy_redact(text):
        calls.append(("redact", text))
        return real_redact(text)

    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
    monkeypatch.setattr(query_pipeline, "detect_suspicious_pattern", _spy_pattern)
    monkeypatch.setattr(query_pipeline, "redact", _spy_redact)
    monkeypatch.setattr(
        "app.routers.query.call_openrouter", _capturing_openrouter([], response=_PROMPT_B)
    )

    response = client.post(
        "/query",
        json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A},
        headers=_JUAN_HEADERS,
    )

    assert response.status_code == 200
    assert [name for name, _ in calls] == [
        "check_duplicate",
        "detect_suspicious_pattern",
        "redact",
        "redact",
    ]
    # Both checks saw raw text; redaction only ever ran afterwards.
    assert calls[0][1] == _PROMPT_A
    assert calls[1][1] == _PROMPT_A
    assert calls[2][1] == _PROMPT_A
    assert calls[3][1] == _PROMPT_B


def test_hash_prompt_only_ever_receives_raw_text(temp_db, monkeypatch):
    seen = []
    real_hash = hash_prompt

    def _spy(label):
        def _hash(text):
            seen.append((label, text))
            return real_hash(text)

        return _hash

    # Two binding sites: audit_logger imported the name; check_duplicate uses the global.
    monkeypatch.setattr(duplicate_checker, "hash_prompt", _spy("duplicate_checker"))
    monkeypatch.setattr(audit_logger, "hash_prompt", _spy("audit_logger"))

    raw_response = "Sure, I will draft a reply to juan@empresa.com for Maria Gomez."

    def _fake_call(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response=raw_response, model_used=model, tokens_used=9)

    result = run_query(
        identity=Identity(user_id="juan@empresa.com", role="user"),
        prompt=_PROMPT_A,
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fake_call,
    )

    assert result.pii_redacted is True
    assert seen == [
        ("duplicate_checker", _PROMPT_A),
        ("audit_logger", _PROMPT_A),
        ("audit_logger", raw_response),
    ]
    # No masking placeholder was ever hashed, in either direction.
    assert all("<" not in text for _, text in seen)


def test_hash_prompt_call_sites_are_exactly_the_three_audited_ones():
    """A new call site must fail here so it gets re-checked for raw-text input."""
    pattern = re.compile(r"(?<!def )hash_prompt\(")
    census = {}
    for path in sorted((_REPO_ROOT / "app").rglob("*.py")):
        count = len(pattern.findall(path.read_text(encoding="utf-8")))
        if count:
            census[path.relative_to(_REPO_ROOT).as_posix()] = count

    assert census == {
        "app/services/audit_logger.py": 2,
        "app/services/duplicate_checker.py": 1,
    }
