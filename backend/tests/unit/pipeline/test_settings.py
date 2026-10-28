import pytest

from tallyproof_pipeline.settings import REPO_ROOT, PipelineSettings, SettingsError, get_settings

URLS = {
    "DATA_SOURCE_USASPENDING_FILES_URL": "https://files.example.gov/archive/",
    "DATA_SOURCE_USASPENDING_API_URL": "https://api.example.gov/v2/",
    "DATA_SOURCE_FISCALDATA_API_URL": "https://fiscal.example.gov/",
    "DATA_SOURCE_ECFR_API_URL": "https://ecfr.example.gov/api/versioner/v1/",
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


def test_relative_data_dir_is_anchored_to_the_repository_root(monkeypatch, tmp_path):
    for name, value in URLS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATA_DIR", "data")
    monkeypatch.chdir(tmp_path)  # simulate running from another folder
    settings = PipelineSettings(_env_file=None)
    assert settings.data_dir == REPO_ROOT / "data"


@pytest.mark.parametrize(
    ("scenario", "events", "per_anomaly"),
    [
        ("smoke", 2_000, 2),
        ("demo", 20_000, 5),
        ("full", 1_000_000, 25),
        ("volume", 15_000_000, 100),
    ],
)
def test_a_scenario_sets_the_replay_size_and_anomaly_count(
    monkeypatch, scenario, events, per_anomaly
):
    for name, value in URLS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATA_SCENARIO", scenario)
    settings = PipelineSettings(_env_file=None)
    assert (settings.replay_slice_events, settings.overlay_per_anomaly) == (events, per_anomaly)


def test_an_explicit_size_overrides_the_scenario(monkeypatch):
    for name, value in URLS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATA_SCENARIO", "smoke")
    monkeypatch.setenv("OVERLAY_PER_ANOMALY", "7")
    settings = PipelineSettings(_env_file=None)
    assert (settings.replay_slice_events, settings.overlay_per_anomaly) == (2_000, 7)


def test_an_unknown_scenario_is_refused(monkeypatch):
    for name, value in URLS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATA_SCENARIO", "huge")
    with pytest.raises(ValueError, match="smoke"):
        PipelineSettings(_env_file=None)
