from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Accepted DATABASE_URL schemes (PRD-007 Section 4). Remote endpoints carry TLS
# or the libSQL protocol and require a token; plaintext http:// is permitted
# only for the local development server, which takes no token (PRD Section 9,
# and the endpoint recorded in STORY-001's driver decision).
_REMOTE_SCHEMES = ("libsql://", "https://")
_LOCAL_SCHEME = "http://"

# Matches every spelling of the file URL this PRD removes: sqlite:///relative,
# sqlite:////absolute, and sqlite:///:memory:.
_SQLITE_SCHEME = "sqlite:"


def _scheme_of(url: str) -> str:
    """The scheme part of a URL, and the only part of one any message quotes.

    A libSQL endpoint may carry `?authToken=...`, and PRD-007 Section 9 requires
    the credential to be "never logged, never echoed in error messages". Quoting
    the scheme alone makes that structural rather than something every `raise`
    below has to remember. This is the one place the module deliberately does
    not mirror `app/db/database.py:25`, which echoes the whole URL.
    """
    head, separator, _ = url.partition("://")
    if separator:
        return head + separator
    return f"{url.split(':', 1)[0]}:" if ":" in url else ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str

    # Turso / libSQL (PRD-007). DATABASE_URL names a network endpoint, not a
    # file, and carries no default: a default that silently creates a local
    # database nobody reads and nobody backs up is the failure mode this PRD
    # removes. TURSO_AUTH_TOKEN is required for a remote endpoint and unused
    # against the local dev server.
    DATABASE_URL: str
    TURSO_AUTH_TOKEN: str = ""

    # Whether startup touches the database at all -- STORY-008's reachability
    # guard and the schema migration behind it. The only sanctioned `False` is
    # the Dockerfile's builder stage: `reflex export` imports `chat_ui.chat_ui`,
    # which calls `init_db()` at import, and PRD-007 Section 11 requires the
    # build to succeed with no reachable database. STORY-014 sets it there,
    # beside the `DATABASE_URL` build placeholder it already owns.
    #
    # It gates the schema work as well as the probe, because gating only the
    # probe would leave the build doing exactly what it cannot do -- reach the
    # database -- one line later. The consequence is stated rather than defended
    # against: `False` in a running deployment boots an application whose schema
    # was never created, and it fails on first use. Defending against that would
    # mean probing the database, which is the thing being skipped.
    DB_BOOTSTRAP_ENABLED: bool = True

    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"

    # RBAC (PRD-005). RBAC_DEFAULT_ROLE was added by STORY-004 for
    # scripts/manage_users.py; the rest of this group is added by STORY-005.
    RBAC_ENABLED: bool = True
    RBAC_DEFAULT_ROLE: str = "user"
    RBAC_ROLES_FILE: str = ""
    MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"

    PII_REDACTION_ENABLED: bool = True
    PII_SCORE_THRESHOLD: float = 0.35
    PII_ENTITIES: str = "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"
    PII_NLP_MODEL: str = "en_core_web_lg"

    # Chat sessions (PRD-008). CHAT_HISTORY_ENABLED is the master switch for
    # transcript persistence: false means no chat_sessions or chat_messages row
    # is written, none is read, no rail is shown, and the chat behaves exactly
    # as it did before this PRD (PRD-008 Section 9, Risk 1) -- the supported
    # configuration for a deployment that must not hold prompt text at rest.
    # CHAT_SESSION_LIMIT caps how many sessions the rail lists per user.
    # Nothing reads either setting yet: app/services/chat_sessions.py, added by
    # STORY-006, is the only consumer.
    CHAT_HISTORY_ENABLED: bool = True
    CHAT_SESSION_LIMIT: int = 50

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """A libSQL endpoint, or a startup error -- never a file (PRD-007)."""
        url = value.strip()
        scheme = _scheme_of(url).lower()

        if scheme.startswith(_SQLITE_SCHEME):
            raise ValueError(
                "DATABASE_URL must name a libSQL endpoint, not a file. Replace the "
                "'sqlite:' URL with 'libsql://<database>-<org>.turso.io' (or "
                "'http://127.0.0.1:8080' for the local dev server). PRD-007 removed "
                "the file fallback deliberately: a local database file is written to "
                "an ephemeral container layer, read by nobody, and backed up by nobody."
            )

        if scheme not in _REMOTE_SCHEMES + (_LOCAL_SCHEME,):
            raise ValueError(
                f"Unsupported DATABASE_URL scheme: {scheme!r}. Expected one of: "
                "libsql://, https://, http:// (local dev server only)."
            )

        return url

    @model_validator(mode="after")
    def _require_token_for_remote_endpoint(self) -> "Settings":
        """A remote endpoint without its credential is a startup error, not a retry.

        Both fields are needed, so this cannot be a field validator.
        """
        is_remote = self.DATABASE_URL.lower().startswith(_REMOTE_SCHEMES)
        if is_remote and not self.TURSO_AUTH_TOKEN.strip():
            raise ValueError(
                "TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote "
                "endpoint (libsql:// or https://). The local libSQL dev server on "
                "http:// takes no token."
            )
        return self

    @field_validator("CHAT_SESSION_LIMIT")
    @classmethod
    def _validate_chat_session_limit(cls, value: int) -> int:
        """At least one session listed, or a startup error (PRD-008).

        A limit of 0 renders an empty rail on a user who has sessions, which is
        a silent lie rather than a small list -- so it fails at startup the way
        a bad DATABASE_URL does, rather than being defaulted away.
        """
        if value < 1:
            raise ValueError(
                f"CHAT_SESSION_LIMIT must be at least 1, got {value}. It is the "
                "number of sessions the rail lists per user; 0 would render an "
                "empty rail for a user who has sessions. To turn transcript "
                "persistence off, set CHAT_HISTORY_ENABLED=false instead."
            )
        return value

    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]

    @property
    def model_allowlist_list(self) -> list[str]:
        return [item.strip() for item in self.MODEL_ALLOWLIST.split(",") if item.strip()]


settings = Settings()
