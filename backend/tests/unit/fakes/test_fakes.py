from confluent_kafka import TopicPartition

from tests.fakes import FakeBroker, FakeError, FakeMessage, FrozenClock


def test_the_broker_reads_back_what_was_produced_in_order():
    broker = FakeBroker()
    delivered: list[object] = []
    for n in range(3):
        broker.produce(
            "t", value=f"v{n}".encode(), key=b"k", on_delivery=lambda e, m: delivered.append(e)
        )
    consumer = broker.consumer()
    consumer.subscribe(["t"])
    batch = consumer.consume(num_messages=2)
    assert [(m.offset(), m.value()) for m in batch] == [(0, b"v0"), (1, b"v1")]
    assert [m.value() for m in consumer.consume(num_messages=10)] == [b"v2"]
    assert consumer.consume(num_messages=10) == []
    assert delivered == [None, None, None]


def test_seek_and_assign_move_the_read_position():
    broker = FakeBroker()
    for n in range(4):
        broker.produce("t", value=bytes([n]))
    consumer = broker.consumer()
    consumer.subscribe(
        ["t"], on_assign=lambda c, ps: c.assign([TopicPartition(p.topic, 0, 2) for p in ps])
    )
    assert [m.offset() for m in consumer.consume(10)] == [2, 3]
    consumer.seek(TopicPartition("t", 0, 1))
    assert [m.offset() for m in consumer.consume(10)] == [1, 2, 3]
    assert consumer.assignment()[0].offset == 4


def test_rejected_deliveries_report_an_error_and_store_nothing():
    broker = FakeBroker(reject=True)
    errors: list[object] = []
    broker.produce("t", value=b"x", on_delivery=lambda e, m: errors.append(e))
    assert errors == ["delivery rejected"]
    assert broker.messages("t") == []


def test_injected_messages_carry_their_error():
    broker = FakeBroker()
    broker.inject(FakeMessage("t", None, _error=FakeError()))
    consumer = broker.consumer()
    consumer.subscribe(["t"])
    (message,) = consumer.consume(5)
    assert message.error() is not None


def test_the_frozen_clock_moves_only_when_told():
    clock = FrozenClock(10.0)
    assert clock() == clock.time() == clock.monotonic() == 10.0
    clock.sleep(2.5)
    clock.advance(1)
    assert clock.now == 13.5
    assert clock.slept == [2.5]
