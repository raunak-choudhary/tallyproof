import pytest

from tallyproof_pipeline.quality import deequ_session, stop_session
from tallyproof_pipeline.settings import PipelineSettings


@pytest.fixture(scope="session")
def spark_settings(tmp_path_factory):
    return PipelineSettings(
        _env_file=None,
        DATA_DIR=tmp_path_factory.mktemp("data"),
        DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
        DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/",
        DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
        SPARK_MASTER="local[1]",
        SPARK_DRIVER_MEMORY="1g",
        SPARK_SHUFFLE_PARTITIONS=1,
        DATA_REPLAY_SLICE_EVENTS=20,
        OVERLAY_PER_ANOMALY=2,
    )


@pytest.fixture(scope="session")
def spark(spark_settings):
    # One JVM serves every Spark test, and Spark only loads extra libraries when the
    # JVM starts, so the shared session is started with Deequ on the classpath.
    session = deequ_session(spark_settings)
    yield session
    stop_session(session)
