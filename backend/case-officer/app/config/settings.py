"""Environment configuration for the Case Officer service.

Loaded via pydantic-settings rather than raw ``os.environ`` calls so that
missing required keys fail loudly at startup instead of deep inside an
agent call (handoff doc section 3).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str
    tavily_api_key: str

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "govflow-ksa"

    # Self-issued secret gating the mock Balady submission tool (Phase 5).
    mcp_auth_secret: str | None = None


settings = Settings()  # type: ignore[call-arg]
