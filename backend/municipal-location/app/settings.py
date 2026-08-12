"""Environment configuration for the Municipal & Location service.

Deliberately narrower than the Case Officer's settings — this service has no
LangSmith or MCP-auth secrets (handoff doc section 3).
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


settings = Settings()  # type: ignore[call-arg]
