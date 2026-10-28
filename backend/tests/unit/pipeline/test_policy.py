from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from tallyproof_core.events import EventEnvelope, EventType
from tallyproof_pipeline.policy import (
    PolicyError,
    Section,
    fetch,
    fetch_part,
    latest_edition,
    outgoing,
    read_corpus,
    sections,
    to_events,
    write_corpus,
)
from tallyproof_pipeline.settings import PipelineSettings

EDITION = date(2026, 10, 19)

# Trimmed from the real eCFR response for FAR part 32, including its odd corners: an
# entity-encoded em dash, inline italics, a reserved section, and a non-section DIV8.
PART_XML = b"""<?xml version="1.0"?>
<DIV5 N="32" TYPE="PART">
<HEAD>PART 32&#x2014;CONTRACT FINANCING</HEAD>
<DIV6 N="A" TYPE="SUBPART">
<DIV8 N="32.000" TYPE="SECTION">
<HEAD>32.000 Scope of part.</HEAD>
<P>This part prescribes policies and procedures for contract financing and other payment
matters. This part addresses&#x2014;</P>
<P>(a) Payment methods, including <I>partial payments</I>;</P>
<img src="x.png"/>
<CITA TYPE="N">[48 FR 42328, Sept. 19, 1983]</CITA>
</DIV8>
<DIV8 N="32.002" TYPE="SECTION"><HEAD>32.002 [Reserved]</HEAD></DIV8>
<DIV8 N="32.906" TYPE="SECTION">
<HEAD>32.906 Making payments.</HEAD>
<P>(a) Agencies shall make payments no earlier than 7 days prior to the due date.</P>
</DIV8>
<DIV8 N="note" TYPE="APPENDIX"><P>Not a section.</P></DIV8>
</DIV6>
</DIV5>
"""


def settings(tmp_path: Path) -> PipelineSettings:
    return PipelineSettings(
        _env_file=None,
        DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
        DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/",
        DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
        DATA_SOURCE_ECFR_API_URL="https://ecfr.example.gov/api/versioner/v1/",
        POLICY_FAR_PARTS=[32],
        POLICY_CORPUS_DIR=tmp_path / "far",
    )


@dataclass
class FakeResponse:
    body: object = None
    content: bytes = b""

    def raise_for_status(self) -> None: ...

    def json(self) -> object:
        return self.body


@dataclass
class FakeSession:
    titles: list[dict[str, object]]
    calls: list[tuple[str, dict[str, str] | None, dict[str, str] | None]] = field(
        default_factory=list
    )

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        if url.endswith("titles.json"):
            return FakeResponse(body={"titles": self.titles})
        return FakeResponse(content=PART_XML)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


TITLES = [
    {"number": 47, "latest_issue_date": "2026-10-01"},
    {"number": 48, "latest_issue_date": "2026-10-19"},
]


def test_sections_keep_paragraph_text_and_skip_headings_images_and_reserved_sections():
    found = sections(PART_XML)
    assert [s.section for s in found] == ["32.000", "32.906"]
    scope = found[0]
    assert scope.title == "Scope of part."
    assert scope.citation == "48 CFR 32.000"
    assert scope.text.split("\n\n") == [
        "This part prescribes policies and procedures for contract financing and other "
        "payment matters. This part addresses—",
        "(a) Payment methods, including partial payments;",
        "[48 FR 42328, Sept. 19, 1983]",
    ]


def test_latest_edition_reads_title_48_and_fails_when_it_is_missing(tmp_path):
    config = settings(tmp_path)
    assert latest_edition(FakeSession(TITLES), config) == EDITION  # type: ignore[arg-type]
    with pytest.raises(PolicyError, match="no title 48"):
        latest_edition(FakeSession(TITLES[:1]), config)  # type: ignore[arg-type]


def test_fetch_part_asks_for_one_compressed_part_of_chapter_one(tmp_path):
    session = FakeSession(TITLES)
    assert fetch_part(session, settings(tmp_path), EDITION, 32) == PART_XML  # type: ignore[arg-type]
    url, params, headers = session.calls[0]
    assert url == "https://ecfr.example.gov/api/versioner/v1/full/2026-10-19/title-48.xml"
    assert params == {"chapter": "1", "part": "32"}
    assert headers == {"Accept-Encoding": "gzip"}


def test_corpus_round_trips_and_refuses_text_that_drifted_from_the_manifest(tmp_path):
    directory = tmp_path / "far"
    found = sections(PART_XML)
    write_corpus(directory, EDITION, {32: found})
    assert read_corpus(directory) == (EDITION, found)

    path = directory / "part-32.jsonl"
    path.write_text(path.read_text().replace("7 days", "70 days"))
    with pytest.raises(PolicyError, match="does not match the manifest"):
        read_corpus(directory)


def test_rewriting_the_corpus_removes_parts_no_longer_configured(tmp_path):
    directory = tmp_path / "far"
    write_corpus(directory, EDITION, {4: sections(PART_XML), 32: sections(PART_XML)})
    write_corpus(directory, EDITION, {32: sections(PART_XML)})
    assert sorted(p.name for p in directory.glob("part-*.jsonl")) == ["part-32.jsonl"]


def test_fetch_downloads_the_configured_parts_of_the_latest_edition(tmp_path, monkeypatch):
    monkeypatch.setattr("tallyproof_pipeline.policy.requests.Session", lambda: FakeSession(TITLES))
    config = settings(tmp_path)
    edition, parts = fetch(config)
    assert edition == EDITION
    assert [s.section for s in parts[32]] == ["32.000", "32.906"]
    assert read_corpus(config.policy_corpus_dir)[0] == EDITION


def test_events_carry_the_full_text_and_version_by_content():
    found = sections(PART_XML)
    events = to_events(EDITION, found)
    assert [e.event_type for e in events] == [EventType.POLICY_PUBLISHED] * 2
    first = events[0]
    assert first.payload.model_dump(mode="json")["text"] == found[0].text
    assert first.idempotency_key == f"ecfr:far:32.000:{found[0].sha256[:16]}"
    assert first.occurred_at == first.emitted_at  # never flagged as a late arrival

    amended = Section("32.000", found[0].title, found[0].text + " Amended.")
    assert to_events(EDITION, [amended])[0].idempotency_key != first.idempotency_key


def test_events_are_ordered_by_section_number_not_text_order():
    found = [
        Section("52.219-10", "b", "text"),
        Section("52.219-9", "a", "text"),
        Section("2.101", "c", "text"),
    ]
    assert [e.payload.model_dump()["section"] for e in to_events(EDITION, found)] == [
        "2.101",
        "52.219-9",
        "52.219-10",
    ]


def test_a_large_definitions_section_still_fits_one_message():
    big = Section("2.101", "Definitions.", "x" * 150_000)
    (message,) = outgoing(to_events(EDITION, [big]))
    assert message.key == b"policy-far"
    assert len(message.value) < 1_000_000  # the broker's default message limit
    assert EventEnvelope.model_validate_json(message.value).payload.model_dump()["text"] == big.text
