from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
GRAPHLOOM_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRAPPHLOOM_",
        env_file=(GRAPHLOOM_DIR / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    db_path: Path = Field(default_factory=lambda: GRAPHLOOM_DIR / ".local" / "graphloom.db")
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    max_body_bytes: int = 10 * 1024 * 1024
    rate_limit_per_minute: int = 1200
    frontend_dist: Path = Field(default_factory=lambda: GRAPHLOOM_DIR / "frontend" / "dist")

    @field_validator("db_path", "frontend_dist", mode="after")
    @classmethod
    def _resolve_runtime_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else GRAPHLOOM_DIR / value

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


def get_settings() -> Settings:
    return Settings()
