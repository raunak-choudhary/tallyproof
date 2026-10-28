import pytest

from tallyproof_pipeline.settings import PipelineSettings, SettingsError, get_settings

URLS = {
    "DATA_SOURCE_USASPENDING_FILES_URL": "https://files.example.gov/archive/",
    "DATA_SOURCE_USASPENDING_API_URL": "https://api.example.gov/v2/",
    "DATA_SOURCE_FISCALDATA_API_URL": "https://fiscal.example.gov/",
}


def test_settings_load_from_environment(monkeypatch, tmp_path):
    for name, value in URLS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_FISCAL_YEARS", "[2024, 2025]")
    settings = PipelineSettings(_env_file=None)
    assert settings.fiscal_years == [2024, 2025]
    assert settings.bronze_dir == tmp_path / "bronze"
    assert settings.silver_dir == tmp_path / "silver"
    assert settings.gold_dir == tmp_path / "gold"
    assert settings.work_dir == tmp_path / "work"
    assert str(settings.usaspending_files_url) == URLS["DATA_SOURCE_USASPENDING_FILES_URL"]


def test_missing_required_values_name_the_variable(monkeypatch):
    for name in URLS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        PipelineSettings, "model_config", {**PipelineSettings.model_config, "env_file": None}
    )
    get_settings.cache_clear()
    with pytest.raises(SettingsError, match="DATA_SOURCE_USASPENDING_FILES_URL"):
        get_settings()
    get_settings.cache_clear()
