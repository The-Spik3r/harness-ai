from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str

    DATABASE_URL: str = "sqlite:///harness_ai.db"
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

    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]

    @property
    def model_allowlist_list(self) -> list[str]:
        return [item.strip() for item in self.MODEL_ALLOWLIST.split(",") if item.strip()]


settings = Settings()
