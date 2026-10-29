import pytest

from tallyproof_core.contact_data import REMOVED, find_contact_data, remove_contact_data


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("POC: JANE.DOE@EXAMPLE.MIL (O) 301-555-0112 | (M) 240.555.0199", 3),
        ("Call (555) 555-0100 for delivery", 1),
        ("contact jane.doe+ops@example.co.uk", 1),
        ("tel +1 555-555-0100", 1),
        ("tel +1 555 555 0100", 1),
        ("call 555.555.0100 today", 1),
    ],
)
def test_emails_and_phone_numbers_are_found(text, found):
    assert len(find_contact_data(text)) == found
    cleaned = remove_contact_data(text)
    assert find_contact_data(cleaned) == []
    assert REMOVED in cleaned


@pytest.mark.parametrize(
    "text",
    [
        "treasury account 012-016-2023/2024-0181",
        "SERIAL 591.062.060.0491 USED IN ASSEMBLY",
        "PIID W911NF24F0001 MOD P00003 FY 2024-2025",
        "NSN 5340-01-123-4567",
        "WRENCH, ADJUSTABLE: IAW ASME B107.100-2020, FLAT WRENCHES",
        "CHANGE THE WAWF CLAUSE, 252.232-7006, FROM REFERENCE TO FULL TEXT",
        "AS CONTAINED IN ASME B107.500-2010; THIS DELIVERY",
        "DFARS 252.204-7012 APPLIES",
        "ALARM LINES ACCT # 351 415 768 0001 63",
        "FY24 P.O.T.S ACCT.# 019 002 0888 001-OCT 2023",
        "ENGINEERING SERVICES",
        "",
    ],
)
def test_codes_dates_and_plain_text_are_left_alone(text):
    assert find_contact_data(text) == []
    assert remove_contact_data(text) == text


def test_none_passes_through():
    assert remove_contact_data(None) is None
