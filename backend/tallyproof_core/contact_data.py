"""Contact details that never belong in the ledger: email addresses and phone numbers.

Tallyproof holds public spending records and no personal data. USAspending's
free-text descriptions sometimes carry a contracting contact's work email and
phone number. The batch pipeline removes them before an event is built, and the
event schema refuses a description that still carries one, so the ledger can't
hold them whatever the source.
"""

import re
from typing import overload

EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE = re.compile(
    # A North American number: a bracketed area code, or three, three, and four
    # digits joined by dashes or by dots (one separator throughout), or any of those
    # after an explicit +1. Nothing alphanumeric or separator-like may sit right
    # before or after it, so standards such as ASME B107.100-2020, clauses such as
    # 252.232-7006, account codes such as 012-016-2023/2024-0181, serials such as
    # 591.062.060.0491, and space-separated account numbers are left alone.
    r"(?<![0-9A-Za-z/.\-])(?:"
    r"\+1[-. ]?[0-9]{3}[-. ][0-9]{3}[-. ][0-9]{4}"
    r"|\([0-9]{3}\)[-. ]?[0-9]{3}[-. ][0-9]{4}"
    r"|[0-9]{3}([-.])[0-9]{3}\1[0-9]{4}"
    r")(?![0-9A-Za-z/.\-])"
)
REMOVED = "[contact removed]"


def find_contact_data(text: str) -> list[str]:
    """Every email address and phone number in ``text``, in order."""
    found = [(m.start(), m.group(0)) for m in EMAIL.finditer(text)]
    found += [(m.start(), m.group(0)) for m in PHONE.finditer(text)]
    return [value for _, value in sorted(found)]


@overload
def remove_contact_data(text: str) -> str: ...
@overload
def remove_contact_data(text: None) -> None: ...
def remove_contact_data(text: str | None) -> str | None:
    """``text`` with every email address and phone number replaced by a marker."""
    if text is None:
        return None
    return PHONE.sub(REMOVED, EMAIL.sub(REMOVED, text))
