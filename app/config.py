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

# What each setting that bounds a resource controls, quoted by its validator
# so the message says why 0 or a negative value is rejected, not just that
# it is. The first three arrived with PRD-010's pipeline sizes; PRD-011 added
# the fourth, which is why the name no longer says "pipeline", and PRD-012 the
# fifth.
_POSITIVE_LIMIT_DESCRIPTIONS = {
    "CONTEXT_MAX_MESSAGES": "the maximum number of messages a conversation may carry into the pipeline",
    "CONTEXT_MAX_CHARACTERS": "the maximum total characters across message contents in a conversation",
    "PIPELINE_MAX_WORKERS": "the number of threads in the dedicated pipeline executor",
    "PATTERN_MAX_SCAN_CHARACTERS": "the per-message ceiling on characters any one pattern scan runs over",
    "PII_MAX_CHARACTERS_CODE": (
        "the analyzable characters per request the code profile's PII redaction "
        "runs over; a longer conversation is refused"
    ),
}

# The entity names Presidio's default English registry supports, at the
# version requirements.txt pins (2.2.364). PII_ENTITIES_CODE is checked against
# this constant rather than a loaded analyzer, because Settings is built before
# any model loads (PRD-012 STORY-005). tests/test_config.py compares it to the
# live registry, so an upgrade that changes the registry turns a test red
# instead of drifting silently.
_PRESIDIO_ENTITY_NAMES = frozenset(
    {
        "CREDIT_CARD",
        "CRYPTO",
        "DATE_TIME",
        "EMAIL_ADDRESS",
        "IBAN_CODE",
        "IP_ADDRESS",
        "LOCATION",
        "MAC_ADDRESS",
        "MEDICAL_LICENSE",
        "NRP",
        "ORGANIZATION",
        "PERSON",
        "PHONE_NUMBER",
        "UK_NHS",
        "URL",
        "US_BANK_NUMBER",
        "US_DRIVER_LICENSE",
        "US_ITIN",
        "US_PASSPORT",
        "US_SSN",
    }
)


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


def _split_comma_list(value: str) -> list[str]:
    """A comma-separated setting as a list, parsed exactly as `pii_entities_list` does."""
    return [item.strip() for item in value.split(",") if item.strip()]


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

    # The Reports section (app/services/reports.py) reads the delivery record the
    # story workflow writes under `.agents/`. Empty means `.agents` at the
    # repository root. REPORTS_REPO_URL is where a report's commit SHA links to.
    REPORTS_AGENTS_DIR: str = ""
    REPORTS_REPO_URL: str = "https://github.com/The-Spik3r/harness-ai"

    # Multi-turn pipeline (PRD-010). Defaults and startup validation land now;
    # no production code reads these yet -- each field names the story that
    # becomes its consumer.

    # Upstream request timeout in seconds, replacing the hard-coded 30.0.
    # Consumed by STORY-005's call_openrouter.
    OPENROUTER_TIMEOUT_SECONDS: float = 120.0

    # Max messages a conversation may carry into the pipeline. Consumed by
    # STORY-008's context-limit refusal.
    CONTEXT_MAX_MESSAGES: int = 100

    # Max total characters across message contents in a conversation -- the
    # sum of len(message.content) over all messages. Characters, not tokens,
    # is a documented proxy (PRD-010 Section 4, Out of Scope). Consumed by
    # STORY-008's context-limit refusal.
    CONTEXT_MAX_CHARACTERS: int = 200_000

    # Size of the dedicated pipeline executor thread pool, off the shared
    # anyio/default-executor pools. Consumed by STORY-006.
    PIPELINE_MAX_WORKERS: int = 32

    # Pattern policy (PRD-011). pattern_config.load() reads PATTERNS_FILE,
    # PATTERN_PROFILE_DEFAULT and PATTERNS_ALLOW_REGEX at startup, in both
    # lifespans (STORY-007). PATTERN_MAX_SCAN_CHARACTERS, and the request-path
    # read of PATTERN_PROFILE_DEFAULT, wait for STORY-008 -- each field names
    # the story that becomes its consumer.

    # Path to the YAML file of pattern lists and profiles. Empty means the
    # built-in policy and no file is read at all -- the RBAC_ROLES_FILE shape
    # (app/services/authz.py). A file replaces the built-in policy wholesale;
    # it is not merged into it. Consumed by STORY-005's pattern_config.load().
    PATTERNS_FILE: str = ""

    # The profile any call site that passes none gets -- /query and the chat
    # UI (PRD-011 Section 6.6, D2).
    #
    # Whether it names a profile the policy actually defines is NOT checked
    # here, and deliberately so: that is a cross-check between this setting and
    # the patterns file, and the file is not read when Settings is constructed.
    # pattern_config.load() owns it (STORY-006), and raises PatternConfigError
    # naming the setting, the missing profile and the profiles that do exist.
    # The only check below is that the value is not empty. Read by STORY-008's
    # run_conversation.
    PATTERN_PROFILE_DEFAULT: str = "chat"

    # Whether `match: regex` lists are permitted at all. Off by default is the
    # first of PRD-011 Section 9.2 T4's four ReDoS layers -- enabling regex is
    # meant to be a deliberate act, not a default anyone inherits. Enforced by
    # STORY-005's loader, which refuses a regex list outright while this is
    # false.
    PATTERNS_ALLOW_REGEX: bool = False

    # Per-message ceiling on the characters any one pattern scan runs over. A
    # longer message is truncated for matching only -- never for the upstream
    # call -- and the pipeline warns with the two lengths, never the content.
    # Consumed by STORY-008's inspect().
    PATTERN_MAX_SCAN_CHARACTERS: int = 1_000_000

    # PII for code (PRD-012). The `code` profile's PII policy is built from
    # these six. The four PII_* settings above keep their meaning and apply to
    # `chat` only; PII_REDACTION_ENABLED stays the master switch for every
    # policy. Nothing reads these yet -- each field names the story that
    # becomes its consumer.

    # Presidio entity types detected under `code`. Pattern recognizers only
    # (D7): with no NER type in the list, the tokenizer-only analyzer is used.
    # PERSON stays out by STORY-003's rule R4 -- it needs en_core_web_lg, which
    # is 7x over the latency budget. Consumed by STORY-006 (analyzer choice) and
    # STORY-007 (the `code` policy).
    PII_ENTITIES_CODE: str = "EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE"

    # Minimum Presidio confidence to mask an entity under `code` (D6). 0.40 is
    # STORY-003's rule R1: the highest candidate that still finds every prose
    # file's entities and every required probe. Consumed by STORY-007.
    PII_SCORE_THRESHOLD_CODE: float = 0.40

    # Analyzable characters per request under `code` (D4); over it, the request
    # is refused, fail closed. 200,000 is STORY-003's rule R3, which holds only
    # with STORY-008's line-aligned 20,000-character chunks. Consumed by
    # STORY-007 (the policy) and STORY-010 (the refusal arm).
    PII_MAX_CHARACTERS_CODE: int = 200_000

    # Redact the model's response under `code` (D1). Off: the reader of a coding
    # agent's output is the file system, and a placeholder in a response becomes
    # a placeholder in a file. Consumed by STORY-007.
    PII_CODE_REDACT_OUTPUT: bool = False

    # Redact `system` turns under `code` (D3). Off: it is the client's own
    # prompt, and the largest fixed cost per request. Consumed by STORY-007.
    PII_CODE_REDACT_SYSTEM: bool = False

    # Skip fenced code blocks under `code` (D2); prose around them, and inline
    # backtick spans, are still analyzed. Consumed by STORY-007.
    PII_CODE_SKIP_CODE_BLOCKS: bool = True

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

    @field_validator("OPENROUTER_TIMEOUT_SECONDS")
    @classmethod
    def _validate_openrouter_timeout_seconds(cls, value: float) -> float:
        """A non-positive timeout would hang forever or fail every call instantly (PRD-010)."""
        if value <= 0:
            raise ValueError(
                f"OPENROUTER_TIMEOUT_SECONDS must be greater than 0, got {value}. "
                "It is the upstream request timeout in seconds."
            )
        return value

    @field_validator(
        "CONTEXT_MAX_MESSAGES",
        "CONTEXT_MAX_CHARACTERS",
        "PIPELINE_MAX_WORKERS",
        "PATTERN_MAX_SCAN_CHARACTERS",
        "PII_MAX_CHARACTERS_CODE",
    )
    @classmethod
    def _validate_positive_limit(cls, value: int, info) -> int:
        """Each of these bounds a resource that cannot be 0 or negative (PRD-010, PRD-011, PRD-012)."""
        if value < 1:
            description = _POSITIVE_LIMIT_DESCRIPTIONS[info.field_name]
            raise ValueError(
                f"{info.field_name} must be at least 1, got {value}. It is {description}."
            )
        return value

    @field_validator("PATTERN_PROFILE_DEFAULT")
    @classmethod
    def _validate_pattern_profile_default(cls, value: str) -> str:
        """Non-empty, and nothing more -- the membership check is not ours (PRD-011).

        This is the whole of what can be decided at construction time. Whether
        the name matches a profile the policy defines depends on a file that
        pattern_config.load() has not read yet, so that check lives there
        (PRD-011 Section 9.3) and a validator here that went looking for the
        file would either fail every boot or silently skip the check.

        Stripped rather than rejected for whitespace, the way
        _validate_database_url treats a trailing newline in a `.env` value.
        """
        name = value.strip()
        if not name:
            raise ValueError(
                "PATTERN_PROFILE_DEFAULT must name a profile, got an empty value. "
                "It is the profile used by any call site that does not pass one "
                "-- /query and the chat UI. Set it to 'chat' (the built-in "
                "default) or to a profile your PATTERNS_FILE defines."
            )
        return name

    @field_validator("PII_ENTITIES_CODE")
    @classmethod
    def _validate_pii_entities_code(cls, value: str) -> str:
        """At least one entity type, each one Presidio knows (PRD-012).

        Checked against _PRESIDIO_ENTITY_NAMES, not a loaded analyzer: Settings
        is constructed before any model loads, and building an analyzer here
        would put a model load on every import of this module. PERSON and
        LOCATION are accepted -- an operator may opt into NER at NER's cost
        (D7); STORY-006 routes such a list to the full analyzer.

        The value is returned as given. pii_entities_code_list does the
        parsing, as pii_entities_list does for PII_ENTITIES.
        """
        accepted = ", ".join(sorted(_PRESIDIO_ENTITY_NAMES))
        names = _split_comma_list(value)
        if not names:
            raise ValueError(
                f"PII_ENTITIES_CODE must name at least one Presidio entity type, "
                f"got {value!r}. It is the entity list the code profile detects; "
                "to turn PII redaction off, set PII_REDACTION_ENABLED=false "
                f"instead. Accepted names: {accepted}."
            )

        unknown = [name for name in names if name not in _PRESIDIO_ENTITY_NAMES]
        if unknown:
            raise ValueError(
                f"PII_ENTITIES_CODE names unknown Presidio entity type(s) "
                f"{', '.join(unknown)} (in {value!r}). Names are case-sensitive. "
                f"Accepted names: {accepted}."
            )
        return value

    @field_validator("PII_SCORE_THRESHOLD_CODE")
    @classmethod
    def _validate_pii_score_threshold_code(cls, value: float) -> float:
        """A confidence, so within [0, 1], or a startup error (PRD-012).

        Written as `not 0 <= value <= 1` so that NaN, which fails every
        comparison, is rejected too rather than slipping through.
        """
        if not 0 <= value <= 1:
            raise ValueError(
                f"PII_SCORE_THRESHOLD_CODE must be between 0 and 1, got {value}. "
                "It is the minimum Presidio confidence for an entity to be "
                "masked under the code profile."
            )
        return value

    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]

    @property
    def pii_entities_code_list(self) -> list[str]:
        return _split_comma_list(self.PII_ENTITIES_CODE)

    @property
    def model_allowlist_list(self) -> list[str]:
        return [item.strip() for item in self.MODEL_ALLOWLIST.split(",") if item.strip()]


settings = Settings()
