"""Federal Acquisition Regulation sections as versioned policy documents.

The analyst quotes policy text, so a quote has to be checkable the same way a
number is. This module fetches selected parts of the FAR (48 CFR chapter 1) from
the official eCFR API, splits them into sections, and writes them to a corpus that
is committed to the repository. Policy text therefore changes only through a
reviewed pull request; there is no upload path at runtime.

Each section becomes one ``policy.published`` event carrying its full text, so a
quote can be checked against a proven leaf. The idempotency key includes a hash of
the text: an amended section becomes a new leaf, and an unchanged one is a
duplicate the ledger refuses.

Usage::

    python -m tallyproof_pipeline.policy fetch     # refresh the committed corpus
    python -m tallyproof_pipeline.policy publish   # send the corpus to the raw topic
"""

import argparse
import hashlib
import json
import logging
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree.ElementTree import Element

import requests
from defusedxml import ElementTree

from tallyproof_core.events import EventEnvelope
from tallyproof_core.ids import new_id
from tallyproof_pipeline.settings import PipelineSettings, get_settings
from tallyproof_pipeline.stream import Outgoing, partition_key

log = logging.getLogger(__name__)

TITLE = 48
CHAPTER = 1
ACCOUNT_ID = "policy-far"
MANIFEST = "manifest.json"
SKIPPED_TAGS = frozenset({"HEAD", "img", "MATH"})
"""Section children that carry no quotable text: the heading is kept separately."""


class PolicyError(RuntimeError):
    """The source or the corpus is not in the shape this module expects."""


@dataclass(frozen=True)
class Section:
    """One FAR section as plain text."""

    section: str
    title: str
    text: str

    @property
    def citation(self) -> str:
        """The section's Code of Federal Regulations citation, for example 48 CFR 32.906."""
        return f"{TITLE} CFR {self.section}"

    @property
    def sha256(self) -> str:
        """Hex SHA-256 of the section text, as recorded in the manifest."""
        return hashlib.sha256(self.text.encode()).hexdigest()


def latest_edition(session: requests.Session, settings: PipelineSettings) -> date:
    """The newest issue date eCFR has for Title 48."""
    url = urljoin(str(settings.ecfr_api_url), "titles.json")
    response = session.get(url, timeout=30)
    response.raise_for_status()
    for title in response.json().get("titles", []):
        if title.get("number") == TITLE:
            return date.fromisoformat(title["latest_issue_date"])
    raise PolicyError(f"eCFR lists no title {TITLE}")


def fetch_part(
    session: requests.Session, settings: PipelineSettings, edition: date, part: int
) -> bytes:
    """One FAR part as eCFR XML. The endpoint refuses uncompressed responses."""
    url = urljoin(str(settings.ecfr_api_url), f"full/{edition.isoformat()}/title-{TITLE}.xml")
    response = session.get(
        url,
        params={"chapter": str(CHAPTER), "part": str(part)},
        headers={"Accept-Encoding": "gzip"},
        timeout=120,
    )
    response.raise_for_status()
    return response.content


def _plain(element: Element) -> str:
    return " ".join("".join(element.itertext()).split())


def sections(xml: bytes) -> list[Section]:
    """Every section in a part, in document order. Reserved sections are skipped."""
    root = ElementTree.fromstring(xml)
    found: list[Section] = []
    for div in root.iter("DIV8"):
        if div.get("TYPE") != "SECTION":
            continue
        number = div.get("N", "")
        head = div.find("HEAD")
        heading = _plain(head) if head is not None else ""
        title = heading.removeprefix(number).strip() or number
        paragraphs = [_plain(child) for child in div if child.tag not in SKIPPED_TAGS]
        text = "\n\n".join(p for p in paragraphs if p)
        if not number or not text:
            continue
        found.append(Section(section=number, title=title, text=text))
    return found


def write_corpus(directory: Path, edition: date, parts: dict[int, list[Section]]) -> None:
    """Write one JSON Lines file per part and a manifest with every section's hash."""
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("part-*.jsonl"):
        stale.unlink()
    for part, found in sorted(parts.items()):
        with (directory / f"part-{part}.jsonl").open("w", encoding="utf-8") as handle:
            for section in found:
                handle.write(json.dumps(asdict(section), ensure_ascii=False, sort_keys=True))
                handle.write("\n")
    manifest = {
        "source": "eCFR",
        "title": TITLE,
        "chapter": CHAPTER,
        "edition": edition.isoformat(),
        "parts": {
            str(part): {s.section: s.sha256 for s in found} for part, found in sorted(parts.items())
        },
    }
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def read_corpus(directory: Path) -> tuple[date, list[Section]]:
    """Load the committed corpus and check every section against the manifest."""
    manifest = json.loads((directory / MANIFEST).read_text())
    edition = date.fromisoformat(manifest["edition"])
    loaded: list[Section] = []
    for part, hashes in manifest["parts"].items():
        path = directory / f"part-{part}.jsonl"
        found = [Section(**json.loads(line)) for line in path.read_text().splitlines() if line]
        actual = {s.section: s.sha256 for s in found}
        if actual != hashes:
            changed = sorted(set(actual.items()) ^ set(hashes.items()))
            raise PolicyError(f"{path.name} does not match the manifest: {changed[:3]}")
        loaded.extend(found)
    return edition, loaded


def _sort_key(section: Section) -> tuple[int | str, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"[.-]", section.section))


def to_events(edition: date, found: list[Section]) -> list[EventEnvelope]:
    """One ``policy.published`` event per section, stamped with the edition date."""
    stamped = datetime.combine(edition, time.min, tzinfo=UTC)
    return [
        EventEnvelope.model_validate(
            {
                "event_id": new_id("evt", now=stamped),
                "idempotency_key": f"ecfr:far:{s.section}:{s.sha256[:16]}",
                "event_type": "policy.published",
                "occurred_at": stamped,
                "emitted_at": stamped,
                "account_id": ACCOUNT_ID,
                "correlation_id": f"far-{edition.isoformat()}",
                "payload": {
                    "source": "FAR",
                    "citation": s.citation,
                    "section": s.section,
                    "title": s.title,
                    "edition": edition,
                    "text": s.text,
                },
            }
        )
        for s in sorted(found, key=_sort_key)
    ]


def outgoing(events: list[EventEnvelope]) -> Iterator[Outgoing]:
    """Messages for the replay producer's publisher."""
    for event in events:
        yield Outgoing(partition_key(event), event.model_dump_json().encode(), valid=True)


def fetch(settings: PipelineSettings) -> tuple[date, dict[int, list[Section]]]:
    """Download the configured parts of the latest edition and rewrite the corpus."""
    with requests.Session() as session:
        edition = latest_edition(session, settings)
        parts = {
            part: sections(fetch_part(session, settings, edition, part))
            for part in settings.far_parts
        }
    write_corpus(settings.policy_corpus_dir, edition, parts)
    return edition, parts


def main() -> None:  # pragma: no cover - thin command-line wrapper around tested functions
    """Refresh the corpus, or publish it to the raw topic."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "publish"])
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "fetch":
        edition, parts = fetch(settings)
        for part, found in sorted(parts.items()):
            log.info("FAR part %d (%s edition): %d sections", part, edition, len(found))
        return

    from confluent_kafka import Producer

    from tallyproof_pipeline.stream import publish

    edition, found = read_corpus(settings.policy_corpus_dir)
    producer = Producer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "acks": "all",
            "enable.idempotence": True,
        }
    )
    summary = publish(
        outgoing(to_events(edition, found)), producer, settings.kafka_topic_events_raw, 1000
    )
    log.info("published %d FAR sections from the %s edition", summary.events, edition)


if __name__ == "__main__":  # pragma: no cover
    main()
