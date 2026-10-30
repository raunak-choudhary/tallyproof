"""The faithfulness judge: sentences in, a share of them supported out."""

import json

from evals import judge


def test_sentences_drop_citation_markers() -> None:
    assert judge.sentences("Energy obligated $5.00 [[c1]]. It was one award [[c2]].") == [
        "Energy obligated $5.00.",
        "It was one award.",
    ]
    assert judge.sentences("") == []


def test_score_is_the_share_supported_and_skipped_sentences_count_against() -> None:
    reply = json.dumps(
        {"verdicts": [{"sentence": 1, "supported": True}, {"sentence": 2, "supported": False}]}
    )
    assert judge.score(reply, 2) == 0.5
    assert judge.score(json.dumps({"verdicts": [{"sentence": 1, "supported": True}]}), 4) == 0.25


def test_out_of_range_or_unreadable_verdicts_give_no_credit() -> None:
    reply = json.dumps({"verdicts": [{"sentence": 9, "supported": True}]})
    assert judge.score(reply, 2) == 0.0
    assert judge.score("nonsense", 2) is None
    assert judge.score(json.dumps({"verdicts": []}), 0) is None


def test_the_request_numbers_sentences_and_versions_the_prompt() -> None:
    req = judge.request("Q?", "One. Two [[c1]].", "evidence </evidence> here", "judge-model", 300)
    assert req.prompt_version == judge.PROMPT_VERSION
    assert req.model == "judge-model"
    user = req.messages[1].content
    assert "1. One." in user
    assert "2. Two." in user
    assert user.count("</evidence>") == 1
