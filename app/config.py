from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str

    DATABASE_URL: str = "sqlite:///harness_ai.db"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"

    # RBAC (PRD-005). RBAC_DEFAULT_ROLE is needed here for scripts/manage_users.py
    # (STORY-004); RBAC_ENABLED, RBAC_ROLES_FILE, and MODEL_ALLOWLIST are added by
    # STORY-005 on top of this field.
    RBAC_DEFAULT_ROLE: str = "user"

    PII_REDACTION_ENABLED: bool = True
    PII_SCORE_THRESHOLD: float = 0.35
    PII_ENTITIES: str = "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"
    PII_NLP_MODEL: str = "en_core_web_lg"

    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]


settings = Settings()
