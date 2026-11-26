from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
GRAPHLOOM_DIR = BACKEND_DIR.parent

PRODUCTION_DATA_DIR = GRAPHLOOM_DIR / ".local" / "projects"
DEVELOPMENT_DATA_DIR = GRAPHLOOM_DIR / ".local" / "dev"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRAPPHLOOM_",
        env_file=(GRAPHLOOM_DIR / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    # `prod` (default) uses .local/projects; `dev` uses .local/dev.
    # An explicit GRAPPHLOOM_DATA_DIR always wins.
    profile: Literal["prod", "dev"] = "prod"
    data_dir: Path | None = None
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    max_body_bytes: int = 10 * 1024 * 1024
    frontend_dist: Path = Field(default_factory=lambda: GRAPHLOOM_DIR / "frontend" / "dist")

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        if self.data_dir is None:
            self.data_dir = DEVELOPMENT_DATA_DIR if self.profile == "dev" else PRODUCTION_DATA_DIR
        elif not self.data_dir.is_absolute():
            self.data_dir = GRAPHLOOM_DIR / self.data_dir
        if not self.frontend_dist.is_absolute():
            self.frontend_dist = GRAPHLOOM_DIR / self.frontend_dist
        return self

    @property
    def resolved_data_dir(self) -> Path:
        assert self.data_dir is not None
        return self.data_dir

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


def get_settings() -> Settings:
    return Settings()
