from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
    EXTRACTOR_MODEL_CHAIN: str = Field(default="google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free")
    OPENROUTER_APP_URL: str = Field(default="")
    OPENROUTER_APP_TITLE: str = Field(default="AI Expense Audit System")
    OPENROUTER_RESPONSE_FORMAT: str = Field(default="json_object")

    REQUEST_TIMEOUT_SECONDS: float = Field(default=20.0)
    MAX_RETRIES: int = Field(default=3)
    BACKOFF_BASE_SECONDS: float = Field(default=1.5)

    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./app.db")
    STORAGE_PATH: str = Field(default="./storage")
    MAX_UPLOAD_MB: int = Field(default=20)

    LOG_LEVEL: str = Field(default="INFO")
    CORS_ORIGINS: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    @property
    def model_chain(self) -> list:
        return [m.strip() for m in self.EXTRACTOR_MODEL_CHAIN.split(",") if m.strip()]

    @property
    def cors_origins(self) -> list:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
