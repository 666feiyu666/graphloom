from __future__ import annotations

from pathlib import Path

from app.config import DEVELOPMENT_DATA_DIR, PRODUCTION_DATA_DIR, Settings
from app.storage import DataStore


def clean_settings(monkeypatch, **kwargs) -> Settings:
    for name in (
        "GRAPPHLOOM_PROFILE",
        "GRAPPHLOOM_DATA_DIR",
        "GRAPPHLOOM_FRONTEND_DIST",
    ):
        monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None, **kwargs)


def test_default_profile_uses_production_dir(monkeypatch):
    settings = clean_settings(monkeypatch)
    assert settings.profile == "prod"
    assert settings.resolved_data_dir == PRODUCTION_DATA_DIR


def test_dev_profile_uses_separate_dir(monkeypatch):
    settings = clean_settings(monkeypatch, profile="dev")
    assert settings.resolved_data_dir == DEVELOPMENT_DATA_DIR
    assert settings.resolved_data_dir != PRODUCTION_DATA_DIR


def test_explicit_data_dir_wins(monkeypatch, tmp_path):
    target = tmp_path / "custom"
    settings = clean_settings(monkeypatch, profile="dev", data_dir=target)
    assert settings.resolved_data_dir == target


def test_relative_data_dir_resolves_against_graphloom(monkeypatch):
    settings = clean_settings(monkeypatch, data_dir=Path("relative/projects"))
    assert settings.resolved_data_dir.is_absolute()


def test_store_creates_data_dir_lazily(tmp_path):
    target = tmp_path / "projects"
    store = DataStore(target)
    assert not target.exists()
    assert store.list_projects() == []

    project = store.create_project("Synthetic", "")
    assert target.exists()
    assert (target / f"{project['id']}.json").exists()
