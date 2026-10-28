from tallyproof_pipeline.policy import read_corpus, to_events
from tallyproof_pipeline.settings import PipelineSettings


def test_the_committed_corpus_matches_its_manifest_and_every_section_is_a_valid_event():
    config = PipelineSettings(
        _env_file=None,
        DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
        DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/",
        DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
        DATA_SOURCE_ECFR_API_URL="https://ecfr.example.gov/api/versioner/v1/",
    )
    edition, found = read_corpus(config.policy_corpus_dir)
    events = to_events(edition, found)
    assert len(events) == len(found) > 200
    assert len({e.idempotency_key for e in events}) == len(events)
    assert {"32.906", "43.103", "4.604"} <= {s.section for s in found}
