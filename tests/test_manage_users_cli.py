import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
from app.db.database import find_user_by_token_hash, get_user, init_db
from app.services.identity import hash_token
from scripts.manage_users import main


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


# --- create-user (AC1, AC2, AC3) ---


def test_create_user_prints_token_exactly_once_with_recovery_warning(temp_db, capsys):
    exit_code = main(["create-user", "--user-id", "ana", "--role", "user"])

    out = capsys.readouterr().out
    assert exit_code == 0
    user = get_user("ana")
    assert user is not None
    assert user.role == "user"
    # exactly one line carries the warning + token
    warning_lines = [line for line in out.splitlines() if "cannot be recovered" in line]
    assert len(warning_lines) == 1
    token = warning_lines[0].rsplit(": ", 1)[1]
    assert find_user_by_token_hash(hash_token(token)) is not None


def test_create_user_role_omitted_uses_rbac_default_role(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_DEFAULT_ROLE", "auditor")

    exit_code = main(["create-user", "--user-id", "bob"])

    assert exit_code == 0
    assert get_user("bob").role == "auditor"


def test_create_user_invalid_role_exits_nonzero_and_lists_valid_roles(temp_db, capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["create-user", "--user-id", "eve", "--role", "superuser"])

    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "admin" in err and "auditor" in err and "user" in err
    assert get_user("eve") is None


def test_create_user_duplicate_user_id_exits_nonzero(temp_db, capsys):
    main(["create-user", "--user-id", "ana", "--role", "user"])

    exit_code = main(["create-user", "--user-id", "ana", "--role", "admin"])

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err
    assert get_user("ana").role == "user"  # first row untouched


# --- list-users (AC4) ---


def test_list_users_prints_expected_fields_never_token_or_hash(temp_db, capsys):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    capsys.readouterr()  # discard create-user's own output, including its token

    exit_code = main(["list-users"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "ana" in out
    assert "user" in out
    assert "True" in out  # active
    assert "cannot be recovered" not in out
    assert "Token" not in out


def test_list_users_empty_table_prints_nothing(temp_db, capsys):
    exit_code = main(["list-users"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


# --- deactivate-user (AC5) ---


def test_deactivate_user_blocks_next_resolve(temp_db):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    user_before = get_user("ana")

    exit_code = main(["deactivate-user", "--user-id", "ana"])

    assert exit_code == 0
    assert get_user("ana").active is False
    # the credential this user was just issued no longer resolves --
    # exercised via find_user_by_token_hash, since the plaintext token
    # itself is only ever visible in create-user's captured stdout.
    assert find_user_by_token_hash(user_before.token_hash) is None


def test_deactivate_user_unknown_user_exits_nonzero(temp_db, capsys):
    exit_code = main(["deactivate-user", "--user-id", "ghost"])

    assert exit_code == 1
    assert "no user" in capsys.readouterr().err


# --- issue-token (Design Note 4: PRD Section 4 "issue tokens";
#     app/db/database.py:320-323 names this exact subcommand) ---


def test_issue_token_rotates_credential(temp_db, capsys):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    old_token_hash = get_user("ana").token_hash
    capsys.readouterr()

    exit_code = main(["issue-token", "--user-id", "ana"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert get_user("ana").token_hash != old_token_hash
    assert find_user_by_token_hash(old_token_hash) is None
    warning_lines = [line for line in out.splitlines() if "cannot be recovered" in line]
    assert len(warning_lines) == 1


def test_issue_token_unknown_user_exits_nonzero(temp_db, capsys):
    exit_code = main(["issue-token", "--user-id", "ghost"])

    assert exit_code == 1
    assert "no user" in capsys.readouterr().err
