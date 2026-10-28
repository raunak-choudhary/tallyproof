import pytest

from config.env import AppSettings, ConfigurationError, _load, checkpointer_settings

VALID = {
    "DJANGO_SECRET_KEY": "x",
    "DJANGO_ALLOWED_HOSTS": "a.example, b.example",
    "CORS_ALLOWED_ORIGINS": "https://web.example",
    "DATA_CLASSIFICATION": "public-no-pii",
    "DB_URL": "postgres://u@h/db",
    "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
    "MERKLE_LOG_ORIGIN": "test/log",
    "CHECKPOINT_PUBLIC_KEY": "k",
}


def set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    for name, value in {**VALID, **overrides}.items():
        monkeypatch.setenv(name, value)


def test_settings_parse_lists_and_hide_secrets(monkeypatch):
    set_env(monkeypatch)
    settings = AppSettings(_env_file=None)
    assert settings.allowed_host_list == ["a.example", "b.example"]
    assert settings.cors_origin_list == ["https://web.example"]
    assert "postgres" not in repr(settings.db_url)


def test_refuses_anything_but_public_pii_free_data(monkeypatch):
    set_env(monkeypatch, DATA_CLASSIFICATION="internal")
    with pytest.raises(ConfigurationError, match="public-no-pii"):
        _load(AppSettings)


def test_missing_required_values_are_named(monkeypatch):
    set_env(monkeypatch)
    monkeypatch.delenv("DB_URL")
    monkeypatch.setattr(AppSettings, "model_config", {**AppSettings.model_config, "env_file": None})
    with pytest.raises(ConfigurationError, match="DB_URL"):
        _load(AppSettings)


def test_checkpointer_needs_its_signing_key_file(monkeypatch, tmp_path):
    set_env(monkeypatch, CHECKPOINT_SIGNING_KEY_FILE=str(tmp_path / "rel.key"))
    assert checkpointer_settings().checkpoint_signing_key_file == tmp_path / "rel.key"
