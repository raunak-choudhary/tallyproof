from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from tallyproof_pipeline.acquire import AcquireError, read_manifest
from tallyproof_pipeline.outlays import (
    SOURCE,
    acquire_outlays,
    file_prefix,
    request_download,
    wait_until_ready,
)
from tallyproof_pipeline.settings import PipelineSettings

NAME = "FY2024P01-P03_All_TAS_AccountBreakdownByAward_2026-10-28_H14M36S44330129.zip"
FILE_URL = f"https://files.example.gov/generated_downloads/{NAME}"
ZIP = b"PK fake outlay archive"


@dataclass
class FakeResponse:
    payload: object = None
    body: bytes = b""
    status_code: int = 200
    headers: CaseInsensitiveDict[str] = field(default_factory=CaseInsensitiveDict)

    def json(self) -> object:
        return self.payload

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield self.body

    def raise_for_status(self) -> None: ...


@dataclass
class FakeSession:
    statuses: list[str] = field(default_factory=lambda: ["ready", "running", "finished"])
    posted: list[dict[str, Any]] = field(default_factory=list)
    polls: int = 0
    downloads: int = 0
    file_name: str = NAME

    def post(self, url, *, json, timeout):
        self.posted.append(json)
        return FakeResponse(payload={"file_name": self.file_name, "file_url": FILE_URL})

    def get(self, url, *, params=None, headers=None, stream=False, timeout=None):
        if stream:
            self.downloads += 1
            return FakeResponse(
                body=ZIP, headers=CaseInsensitiveDict({"Content-Length": str(len(ZIP))})
            )
        status = self.statuses[min(self.polls, len(self.statuses) - 1)]
        self.polls += 1
        return FakeResponse(
            payload={"status": status, "message": "An error occurred.", "total_rows": 5}
        )


def session(fake: FakeSession) -> requests.Session:
    return cast("requests.Session", fake)


@pytest.fixture
def settings(tmp_path):
    return PipelineSettings(
        _env_file=None,
        DATA_DIR=tmp_path,
        DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
        DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/api/v2/",
        DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
        DATA_SOURCE_ECFR_API_URL="https://ecfr.example.gov/api/versioner/v1/",
        DATA_DOWNLOAD_MAX_MBPS=1000,
        DATA_OUTLAY_FISCAL_YEAR=2024,
        DATA_OUTLAY_QUARTERS=[1],
    )


def test_a_quarter_file_covers_the_year_up_to_the_quarter():
    assert file_prefix(2024, 1) == "FY2024P01-P03_All_TAS_AccountBreakdownByAward"
    assert file_prefix(2025, 4) == "FY2025P01-P12_All_TAS_AccountBreakdownByAward"


def test_the_request_asks_for_award_financial_data_for_every_agency(settings):
    fake = FakeSession()
    generated = request_download(session(fake), settings, 2024, 1)
    assert generated.file_name == NAME
    filters = fake.posted[0]["filters"]
    assert filters["submission_types"] == ["award_financial"]
    assert (filters["fy"], filters["quarter"], filters["agency"]) == ("2024", 1, "all")


def test_an_unexpected_file_name_is_refused(settings):
    fake = FakeSession(file_name="something_else.zip")
    with pytest.raises(AcquireError, match="unexpected download response"):
        request_download(session(fake), settings, 2024, 1)


def test_waiting_polls_until_the_file_is_finished(settings):
    fake, slept = FakeSession(), list[float]()
    status = wait_until_ready(session(fake), settings, NAME, sleep=slept.append)
    assert status["status"] == "finished"
    assert fake.polls == 3
    assert slept == [30.0, 30.0]


def test_a_failed_build_is_reported_with_the_server_message(settings):
    fake = FakeSession(statuses=["running", "failed"])
    with pytest.raises(AcquireError, match="An error occurred"):
        wait_until_ready(session(fake), settings, NAME, sleep=lambda _: None)


def test_waiting_gives_up_after_the_timeout(settings):
    ticks = iter(range(0, 10_000, 100))
    fake = FakeSession(statuses=["running"])
    with pytest.raises(AcquireError, match="not ready after 250 seconds"):
        wait_until_ready(
            session(fake),
            settings,
            NAME,
            timeout_seconds=250,
            sleep=lambda _: None,
            clock=lambda: float(next(ticks)),
        )


def test_acquire_downloads_once_and_reuses_the_verified_file(settings):
    fake = FakeSession()
    (entry,) = acquire_outlays(settings, session(fake), sleep=lambda _: None)
    assert (entry.source, entry.fiscal_year, entry.file_name) == (SOURCE, 2024, NAME)
    assert (settings.bronze_dir / NAME).read_bytes() == ZIP
    assert read_manifest(settings.bronze_dir / "manifest.jsonl")[NAME] == entry

    again = FakeSession()
    assert acquire_outlays(settings, session(again), sleep=lambda _: None) == [entry]
    assert again.posted == []
    assert again.downloads == 0


def test_quarters_outside_one_to_four_are_refused(tmp_path):
    with pytest.raises(ValueError, match="less than or equal to 4"):
        PipelineSettings(
            _env_file=None,
            DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
            DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/api/v2/",
            DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
            DATA_SOURCE_ECFR_API_URL="https://ecfr.example.gov/api/versioner/v1/",
            DATA_OUTLAY_QUARTERS=[5],
        )
