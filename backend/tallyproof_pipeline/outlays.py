"""Download account-level outlay data (File C, "Account Breakdown by Award").

Contract archives say what was obligated. What was actually paid comes from a
different source: each agency's award financial submission, which USAspending
serves as a generated download. The file is built on request, so this module asks
for it, waits until the server reports it finished, and then downloads it with the
same resumable, rate-limited downloader and manifest as the contract archives.

A full fiscal year is too large for the server to build (the request fails after
about twelve minutes), so files are requested one quarter at a time. Each quarter's
file covers the fiscal year from period 1 to the quarter's last period, with
outlays cumulative from the start of the year.

Usage::

    python -m tallyproof_pipeline.outlays
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import requests

from tallyproof_pipeline.acquire import (
    AcquireError,
    ManifestEntry,
    download,
    read_manifest,
    sha256_file,
)
from tallyproof_pipeline.settings import PipelineSettings, get_settings

log = logging.getLogger(__name__)

SOURCE = "usaspending.award_financial"
ENDPOINT = "download/accounts/"
STATUS_ENDPOINT = "download/status"


@dataclass(frozen=True)
class GeneratedFile:
    """A download the server has been asked to build."""

    file_name: str
    file_url: str


def file_prefix(fiscal_year: int, quarter: int) -> str:
    """The start of the generated file's name, which is the same for every request."""
    return f"FY{fiscal_year}P01-P{quarter * 3:02d}_All_TAS_AccountBreakdownByAward"


def request_download(
    session: requests.Session, settings: PipelineSettings, fiscal_year: int, quarter: int
) -> GeneratedFile:
    """Ask the server to build one quarter's award financial file for every agency."""
    url = urljoin(str(settings.usaspending_api_url), ENDPOINT)
    body: dict[str, Any] = {
        "account_level": "treasury_account",
        "filters": {
            "budget_function": "all",
            "agency": "all",
            "submission_types": ["award_financial"],
            "fy": str(fiscal_year),
            "quarter": quarter,
        },
        "file_format": "csv",
    }
    response = session.post(url, json=body, timeout=60)
    response.raise_for_status()
    data = response.json()
    if not str(data.get("file_name", "")).startswith(file_prefix(fiscal_year, quarter)):
        raise AcquireError(f"unexpected download response: {data}")
    return GeneratedFile(data["file_name"], data["file_url"])


def wait_until_ready(
    session: requests.Session,
    settings: PipelineSettings,
    file_name: str,
    *,
    poll_seconds: float = 30.0,
    timeout_seconds: float = 3600.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Wait for the server to finish building a file and return its final status.

    The status starts as ``ready`` (queued), moves to ``running``, and ends as
    ``finished`` or ``failed``.

    Raises:
        AcquireError: If the build fails or takes longer than ``timeout_seconds``.
    """
    url = urljoin(str(settings.usaspending_api_url), STATUS_ENDPOINT)
    deadline = clock() + timeout_seconds
    while True:
        response = session.get(url, params={"file_name": file_name}, timeout=60)
        response.raise_for_status()
        status: dict[str, object] = response.json()
        if status.get("status") == "finished":
            return status
        if status.get("status") == "failed":
            raise AcquireError(f"the server failed to build {file_name}: {status.get('message')}")
        if clock() >= deadline:
            raise AcquireError(f"{file_name} was not ready after {timeout_seconds:.0f} seconds")
        sleep(poll_seconds)


def acquire_outlays(
    settings: PipelineSettings,
    session: requests.Session,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> list[ManifestEntry]:
    """Download each configured quarter that isn't already on disk and verified."""
    settings.bronze_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = settings.bronze_dir / "manifest.jsonl"
    manifest = read_manifest(manifest_path)
    results = []
    for quarter in settings.outlay_quarters:
        prefix = file_prefix(settings.outlay_fiscal_year, quarter)
        known = next(
            (
                entry
                for name, entry in sorted(manifest.items())
                if name.startswith(prefix)
                and (settings.bronze_dir / name).exists()
                and sha256_file(settings.bronze_dir / name) == entry.sha256
            ),
            None,
        )
        if known:
            log.info("%s already downloaded and verified", known.file_name)
            results.append(known)
            continue
        generated = request_download(session, settings, settings.outlay_fiscal_year, quarter)
        log.info("waiting for the server to build %s", generated.file_name)
        status = wait_until_ready(session, settings, generated.file_name, sleep=sleep)
        log.info("built: %s rows, %s KB", status.get("total_rows"), status.get("total_size"))
        destination = settings.bronze_dir / generated.file_name
        download(session, generated.file_url, destination, max_mbps=settings.download_max_mbps)
        entry = ManifestEntry(
            source=SOURCE,
            fiscal_year=settings.outlay_fiscal_year,
            file_name=generated.file_name,
            url=generated.file_url,
            size_bytes=destination.stat().st_size,
            sha256=sha256_file(destination),
            fetched_at=now().isoformat(timespec="seconds"),
        )
        with manifest_path.open("a") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        results.append(entry)
    return results


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Download the configured outlay quarters."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with requests.Session() as session:
        for entry in acquire_outlays(get_settings(), session):
            print(f"{entry.file_name}  {entry.size_bytes:,} bytes  sha256 {entry.sha256}")


if __name__ == "__main__":  # pragma: no cover
    main()
