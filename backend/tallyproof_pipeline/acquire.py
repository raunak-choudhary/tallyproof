"""Download official USAspending contract archives into the bronze layer.

For each fiscal year, the USAspending API is asked for the current full
contracts archive, which is then downloaded with:

- resume support, so a dropped connection continues where it stopped;
- a speed cap, to be polite to the source and the local network;
- a size check against the server's Content-Length;
- a SHA-256 hash recorded in ``bronze/manifest.jsonl``.

Archives already in the manifest with a matching hash are not downloaded again.
The manifest's hashes are later appended to the Merkle log as source-file
leaves, so every ledger event can be traced to the exact file it came from.

Usage::

    python -m tallyproof_pipeline.acquire
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

from tallyproof_pipeline.settings import PipelineSettings, get_settings

log = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
SOURCE = "usaspending.contracts"


class AcquireError(RuntimeError):
    """Raised when an archive cannot be listed, downloaded, or verified."""


@dataclass(frozen=True)
class ManifestEntry:
    """One downloaded source file."""

    source: str
    fiscal_year: int
    file_name: str
    url: str
    size_bytes: int
    sha256: str
    fetched_at: str


def find_contract_archive(
    session: requests.Session, settings: PipelineSettings, fiscal_year: int
) -> tuple[str, str]:
    """Ask the USAspending API for the current full contracts archive of a fiscal year.

    Returns:
        The archive's file name and download URL.

    Raises:
        AcquireError: If the API lists no full archive for that year.
    """
    url = urljoin(str(settings.usaspending_api_url), "bulk_download/list_monthly_files/")
    response = session.post(
        url, json={"agency": "all", "fiscal_year": fiscal_year, "type": "contracts"}, timeout=60
    )
    response.raise_for_status()
    body = response.json()
    files = body.get("monthly_files", []) if isinstance(body, dict) else []
    for item in files:
        if item.get("fiscal_year") == fiscal_year and "_Full_" in item.get("file_name", ""):
            return str(item["file_name"]), str(item["url"])
    raise AcquireError(f"no full contracts archive listed for fiscal year {fiscal_year}")


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file, read in chunks to keep memory flat."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    max_mbps: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Download a file, resuming a partial download and capping the speed.

    Data streams into ``<destination>.part``, which is renamed only once the
    full size has arrived, so a file at ``destination`` is always complete.

    Raises:
        AcquireError: If the server's size and the received size disagree.
    """
    partial = destination.with_name(destination.name + ".part")
    already = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={already}-"} if already else {}
    response = session.get(url, headers=headers, stream=True, timeout=60)
    response.raise_for_status()

    if already and response.status_code != 206:
        log.info("server ignored the resume request; starting over")
        already = 0
    remaining = int(response.headers.get("Content-Length", "0"))
    expected_total = already + remaining

    bytes_per_second = max_mbps * 1024 * 1024
    started, sent = clock(), 0
    with partial.open("ab" if already else "wb") as handle:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            handle.write(chunk)
            sent += len(chunk)
            # Sleep just long enough to keep the average at or below the cap.
            ahead = sent / bytes_per_second - (clock() - started)
            if ahead > 0:
                sleep(ahead)

    received = partial.stat().st_size
    if remaining and received != expected_total:
        raise AcquireError(
            f"{destination.name}: expected {expected_total} bytes, received {received}"
        )
    partial.replace(destination)


def read_manifest(path: Path) -> dict[str, ManifestEntry]:
    """Load the manifest, keyed by file name."""
    if not path.exists():
        return {}
    entries = (ManifestEntry(**json.loads(line)) for line in path.read_text().splitlines() if line)
    return {entry.file_name: entry for entry in entries}


def acquire(
    settings: PipelineSettings,
    session: requests.Session,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> list[ManifestEntry]:
    """Download every configured fiscal year and record each file in the manifest.

    Returns:
        Manifest entries for the configured fiscal years, downloaded or reused.
    """
    settings.bronze_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = settings.bronze_dir / "manifest.jsonl"
    manifest = read_manifest(manifest_path)
    results = []
    for fiscal_year in settings.fiscal_years:
        file_name, url = find_contract_archive(session, settings, fiscal_year)
        destination = settings.bronze_dir / file_name
        known = manifest.get(file_name)
        if known and destination.exists() and sha256_file(destination) == known.sha256:
            log.info("%s already downloaded and verified", file_name)
            results.append(known)
            continue
        log.info("downloading %s", file_name)
        download(session, url, destination, max_mbps=settings.download_max_mbps)
        entry = ManifestEntry(
            source=SOURCE,
            fiscal_year=fiscal_year,
            file_name=file_name,
            url=url,
            size_bytes=destination.stat().st_size,
            sha256=sha256_file(destination),
            fetched_at=now().isoformat(timespec="seconds"),
        )
        with manifest_path.open("a") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        results.append(entry)
    return results


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Download the configured fiscal years."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with requests.Session() as session:
        for entry in acquire(get_settings(), session):
            print(f"{entry.file_name}  {entry.size_bytes:,} bytes  sha256 {entry.sha256}")


if __name__ == "__main__":  # pragma: no cover
    main()
