import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from tallyproof_pipeline.acquire import (
    AcquireError,
    acquire,
    download,
    find_contract_archive,
    read_manifest,
)
from tallyproof_pipeline.settings import PipelineSettings

ARCHIVE = b"PK fake archive contents " * 4000
LISTING = {
    "monthly_files": [
        {"fiscal_year": None, "file_name": "FY(All)_All_Contracts_Delta_20261006.zip", "url": "x"},
        {
            "fiscal_year": 2025,
            "file_name": "FY2025_All_Contracts_Full_20261006.zip",
            "url": "https://files.example.gov/FY2025_All_Contracts_Full_20261006.zip",
        },
    ]
}


@dataclass
class FakeResponse:
    status_code: int = 200
    body: bytes = b""
    payload: object = None
    headers: CaseInsensitiveDict[str] = field(default_factory=CaseInsensitiveDict)

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start : start + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@dataclass
class FakeSession:
    content: bytes = ARCHIVE
    honor_range: bool = True
    truncate: bool = False
    gets: list[dict[str, str]] = field(default_factory=list)

    def post(self, url, *, json, timeout):
        return FakeResponse(payload=LISTING)

    def get(self, url, *, headers, stream, timeout):
        self.gets.append(headers)
        start = 0
        if "Range" in headers and self.honor_range:
            start = int(headers["Range"].removeprefix("bytes=").rstrip("-"))
        body = self.content[start:]
        length = len(body)
        if self.truncate:
            body = body[: length // 2]
        return FakeResponse(
            status_code=206 if start else 200,
            body=body,
            headers=CaseInsensitiveDict({"Content-Length": str(length)}),
        )


def fake(**kwargs: Any) -> requests.Session:
    # The fake implements only the calls the downloader makes.
    return cast("requests.Session", FakeSession(**kwargs))


@pytest.fixture
def settings(tmp_path):
    return PipelineSettings(
        _env_file=None,
        DATA_DIR=tmp_path,
        DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
        DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/api/v2/",
        DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
        DATA_FISCAL_YEARS=[2025],
        DATA_DOWNLOAD_MAX_MBPS=1000,
    )


def test_finds_the_full_archive_for_the_year(settings):
    name, url = find_contract_archive(fake(), settings, 2025)
    assert name == "FY2025_All_Contracts_Full_20261006.zip"
    assert url.endswith(name)


def test_missing_year_is_an_error(settings):
    with pytest.raises(AcquireError, match="fiscal year 2019"):
        find_contract_archive(fake(), settings, 2019)


def test_download_records_size_and_hash_in_the_manifest(settings):
    fixed = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    [entry] = acquire(settings, fake(), now=lambda: fixed)
    assert entry.size_bytes == len(ARCHIVE)
    assert entry.sha256 == hashlib.sha256(ARCHIVE).hexdigest()
    assert entry.fetched_at == "2026-10-27T12:00:00+00:00"
    assert read_manifest(settings.bronze_dir / "manifest.jsonl")[entry.file_name] == entry
    assert (settings.bronze_dir / entry.file_name).read_bytes() == ARCHIVE


def test_verified_archives_are_not_downloaded_again(settings):
    acquire(settings, fake())
    session = FakeSession()
    acquire(settings, cast("requests.Session", session))
    assert session.gets == []
    lines = (settings.bronze_dir / "manifest.jsonl").read_text().splitlines()
    assert len(lines) == 1


def test_a_corrupted_local_copy_is_downloaded_again(settings):
    [entry] = acquire(settings, fake())
    (settings.bronze_dir / entry.file_name).write_bytes(b"corrupted")
    session = FakeSession()
    acquire(settings, cast("requests.Session", session))
    assert len(session.gets) == 1
    assert (settings.bronze_dir / entry.file_name).read_bytes() == ARCHIVE


def test_partial_download_resumes_with_a_range_request(tmp_path):
    destination = tmp_path / "archive.zip"
    (tmp_path / "archive.zip.part").write_bytes(ARCHIVE[:30000])
    session = FakeSession()
    download(
        cast("requests.Session", session),
        "https://files.example.gov/a.zip",
        destination,
        max_mbps=1000,
    )
    assert session.gets == [{"Range": "bytes=30000-"}]
    assert destination.read_bytes() == ARCHIVE


def test_server_that_ignores_resume_restarts_cleanly(tmp_path):
    destination = tmp_path / "archive.zip"
    (tmp_path / "archive.zip.part").write_bytes(b"stale partial data")
    download(fake(honor_range=False), "u", destination, max_mbps=1000)
    assert destination.read_bytes() == ARCHIVE


def test_truncated_download_is_rejected_and_not_promoted(tmp_path):
    destination = tmp_path / "archive.zip"
    with pytest.raises(AcquireError, match="expected"):
        download(fake(truncate=True), "u", destination, max_mbps=1000)
    assert not destination.exists()


def test_speed_cap_sleeps_when_ahead_of_the_limit(tmp_path):
    sleeps: list[float] = []
    download(
        fake(content=b"x" * 3 * 1024 * 1024),
        "u",
        tmp_path / "f",
        max_mbps=1,
        sleep=sleeps.append,
        clock=lambda: 0.0,
    )
    # Three 1 MiB chunks at 1 MiB/s with a frozen clock: wait 1, 2, then 3 seconds.
    assert sleeps == [1.0, 2.0, 3.0]


def test_manifest_lines_are_sorted_json(settings):
    acquire(settings, fake())
    line = (settings.bronze_dir / "manifest.jsonl").read_text().splitlines()[0]
    assert list(json.loads(line)) == sorted(json.loads(line))
