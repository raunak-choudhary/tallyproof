"""Ledger event schemas and the leaf document each event hashes to.

Every event has the same envelope and a payload whose shape depends on its type.
The leaf document is the exact set of fields that gets canonicalized and hashed
into the Merkle log. Tracing fields such as ``correlation_id`` are deliberately
left out of it, so they can never change a proof.

Validation enforces the rules that keep Python and the browser producing the same
bytes: money is a decimal string, integers stay within the safe range, strings
are valid Unicode, and no unknown fields are accepted.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from tallyproof_core.canonical import MAX_SAFE_INTEGER, canonicalize
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.ids import parse_id
from tallyproof_core.money import Money, MoneyError

SCHEMA_VERSION: Final = 1


def _money_text(value: str) -> str:
    try:
        return str(Money.parse(value))
    except MoneyError as error:
        raise ValueError(str(error)) from error


MoneyText = Annotated[str, AfterValidator(_money_text)]
"""A decimal amount as text, normalized to two decimal places."""

# Pydantic itself rejects strings that are not valid Unicode, such as lone surrogates.
Text = Annotated[str, Field(min_length=1, max_length=4000)]
OptionalText = Annotated[str | None, Field(default=None, max_length=4000)]
SafeInt = Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)


class EventType(StrEnum):
    """Every kind of event the ledger accepts."""

    OBLIGATION_RECORDED = "obligation.recorded"
    OBLIGATION_ADJUSTED = "obligation.adjusted"
    OUTLAY_REPORTED = "outlay.reported"
    CASH_MOVEMENT = "cash.movement"
    SOURCE_REGISTERED = "source.registered"


class ObligationRecorded(_Strict):
    """A new contract obligation: money committed to a recipient."""

    award_key: Text
    piid: Text
    awarding_agency: Text
    funding_agency: OptionalText
    amount: MoneyText
    currency: Literal["USD"] = "USD"
    action_date: date
    action_type: OptionalText
    naics_code: OptionalText
    psc_code: OptionalText
    description: OptionalText


class ObligationAdjusted(_Strict):
    """A modification to an existing award. Negative amounts are de-obligations."""

    award_key: Text
    modification_number: Text
    amount: MoneyText
    currency: Literal["USD"] = "USD"
    action_date: date
    action_type: OptionalText
    description: OptionalText


class OutlayReported(_Strict):
    """Money paid against an award during one fiscal period."""

    award_key: Text
    treasury_account: Text
    fiscal_year: SafeInt
    fiscal_period: Annotated[int, Field(ge=1, le=12)]
    cumulative_outlay: MoneyText
    period_outlay: MoneyText
    currency: Literal["USD"] = "USD"


class CashMovement(_Strict):
    """A deposit to or withdrawal from the Treasury operating cash account."""

    record_date: date
    account: Text
    direction: Literal["deposit", "withdrawal"]
    category: Text
    amount: MoneyText
    unit: Literal["millions"] = "millions"
    currency: Literal["USD"] = "USD"


class SourceRegistered(_Strict):
    """A downloaded source file, recorded so events can be traced to it."""

    file_name: Text
    url: Text
    size_bytes: SafeInt
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    fetched_at: datetime


PAYLOAD_TYPES: dict[EventType, type[_Strict]] = {
    EventType.OBLIGATION_RECORDED: ObligationRecorded,
    EventType.OBLIGATION_ADJUSTED: ObligationAdjusted,
    EventType.OUTLAY_REPORTED: OutlayReported,
    EventType.CASH_MOVEMENT: CashMovement,
    EventType.SOURCE_REGISTERED: SourceRegistered,
}

LEAF_FIELDS = (
    "event_id",
    "idempotency_key",
    "event_type",
    "schema_version",
    "occurred_at",
    "emitted_at",
    "account_id",
    "payload",
)
"""The envelope fields that are hashed. Everything else is transport or tracing."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone aware")
    return value.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class EventEnvelope(_Strict):
    """One event, as it travels through Kafka and is stored in the ledger."""

    event_id: str
    idempotency_key: Text
    event_type: EventType
    schema_version: Literal[1] = SCHEMA_VERSION
    occurred_at: Annotated[datetime, AfterValidator(_utc)]
    emitted_at: Annotated[datetime, AfterValidator(_utc)]
    account_id: Text
    correlation_id: Text
    payload: (
        ObligationRecorded | ObligationAdjusted | OutlayReported | CashMovement | SourceRegistered
    )

    @field_validator("event_id")
    @classmethod
    def _event_id(cls, value: str) -> str:
        parse_id(value, expected_prefix="evt")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_matches_type(cls, value: object, info: ValidationInfo) -> object:
        event_type = info.data.get("event_type")
        if event_type is None:
            return value
        model = PAYLOAD_TYPES[EventType(event_type)]
        if isinstance(value, model):
            return value
        if isinstance(value, BaseModel):
            raise ValueError(f"payload is not a {model.__name__}")
        return model.model_validate(value)

    def leaf_document(self) -> dict[str, object]:
        """Return the exact JSON document that is canonicalized and hashed."""
        document: dict[str, object] = {
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "event_type": self.event_type.value,
            "schema_version": self.schema_version,
            "occurred_at": _timestamp_text(self.occurred_at),
            "emitted_at": _timestamp_text(self.emitted_at),
            "account_id": self.account_id,
            "payload": self.payload.model_dump(mode="json", exclude_none=True),
        }
        assert tuple(document) == LEAF_FIELDS  # noqa: S101 - guards against silent drift
        return document

    def canonical_bytes(self) -> bytes:
        """Return the RFC 8785 bytes of the leaf document."""
        return canonicalize(self.leaf_document())

    def leaf_hash(self) -> bytes:
        """Return the Merkle leaf hash of this event."""
        return leaf_hash(self.canonical_bytes())
