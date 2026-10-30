"""Measure the live pipeline under load: throughput, outbox lag, and end-to-end latency.

Run it through ``make load-test``, which starts a throwaway copy of the local stack
(its own Compose project and volumes, the same images and memory limits), migrates
it, runs this module, and removes the copy afterwards. The demo ledger is never
touched.

Three measurements, all on real gold events:

1. **Throughput and the single-writer ceiling.** A slice of events is loaded into
   the raw topic while no consumer runs. Then one, two, and three consumers (the
   topic has three partitions) drain a fresh slice each, while the checkpointer,
   the projections, and the outbox relay run as usual. Throughput is the slice size
   over the time between its first and last append. Every append takes the single
   log-head lock, so extra consumers parse in parallel but append one at a time.
2. **End-to-end latency.** Fresh events are published at a steady rate below the
   measured ceiling. Each is timed from the moment it is handed to the producer to
   three points: appended to the log, covered by a signed checkpoint, and announced
   on the appended topic by the outbox relay.
3. **Proof latency.** Inclusion proofs for a random sample of events, fetched from
   the API one at a time.

Postgres runs inside the Colima VM, so its timestamps are moved onto the host clock
using the offset measured between the two before each latency query.
"""

import argparse
import gzip
import json
import math
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.stream import partition_key

BACKEND = Path(__file__).resolve().parents[1]
SETTLE_SECONDS = 10
"""Time given to a consumer group to finish rebalancing before events are published."""


@dataclass(frozen=True)
class Distribution:
    """Nearest-rank percentiles of a set of durations, in milliseconds."""

    count: int
    p50: float
    p95: float
    p99: float
    max: float


@dataclass(frozen=True)
class Drain:
    """One throughput run: a preloaded slice drained by ``consumers`` consumers."""

    consumers: int
    events: int
    seconds: float
    per_second: float
    outbox_lag: Distribution


@dataclass(frozen=True)
class Paced:
    """The steady-rate run and its end-to-end latencies."""

    rate: int
    events: int
    consumers: int
    appended: Distribution
    checkpointed: Distribution
    announced: Distribution
    outbox_lag: Distribution


@dataclass
class Report:
    """Everything one load test measured, and what it ran on."""

    started_at: str
    hardware: dict[str, str]
    settings: dict[str, str]
    drains: list[Drain] = field(default_factory=list)
    paced: Paced | None = None
    proofs: Distribution | None = None
    proof_tree_size: int = 0
    partitions: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Message:
    """One gold event, ready to publish."""

    event_id: str
    key: bytes
    value: bytes


def distribution(values_ms: Sequence[float]) -> Distribution:
    """Nearest-rank p50, p95, p99, and the maximum. Empty input gives zeros."""
    if not values_ms:
        return Distribution(0, 0.0, 0.0, 0.0, 0.0)
    ordered = sorted(values_ms)

    def rank(p: float) -> float:
        return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]

    return Distribution(
        len(ordered),
        round(rank(50), 1),
        round(rank(95), 1),
        round(rank(99), 1),
        round(ordered[-1], 1),
    )


def clock_offset(samples: Iterable[tuple[float, float, float]]) -> float:
    """Seconds to subtract from a database time to put it on the host clock.

    Each sample is (host time before the query, database time, host time after).
    The sample with the shortest round trip is the most precise, and the database
    read is assumed to fall at its midpoint.
    """
    before, db, after = min(samples, key=lambda s: s[2] - s[0])
    return db - (before + after) / 2


def drain_rate(events: int, in_last_batch: int, span: float) -> tuple[float, float]:
    """Seconds and events per second for a drained backlog.

    Postgres stamps every row of an append with its transaction's start, so the span
    from the first stamp to the last covers every batch except the last one. The
    rate is therefore the events before the last batch over that span, and the
    reported duration adds one more batch at that rate.
    """
    if span <= 0:
        return 0.0, 0.0
    rate = (events - in_last_batch) / span
    return round(events / rate, 2), round(rate, 1)


def paced_rate(ceiling: float, share: float) -> int:
    """A steady rate below the ceiling, rounded down to a hundred, at least a hundred."""
    return max(100, int(ceiling * share) // 100 * 100)


def latencies(
    sent: dict[str, float], reached: Iterable[tuple[str, float | None]], offset: float
) -> list[float]:
    """Milliseconds from each send to the database time it reached a point.

    Events that never reached it, or were not sent in this run, are left out; the
    report counts them, so a gap is visible rather than hidden.
    """
    out = []
    for event_id, at in reached:
        start = sent.get(event_id)
        if start is not None and at is not None:
            out.append((at - offset - start) * 1000)
    return out


def read_messages(path: Path) -> Iterator[Message]:
    """Gold events in log order, as the replay would publish them (valid events only)."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            event = EventEnvelope.model_validate(json.loads(line))
            yield Message(event.event_id, partition_key(event), event.model_dump_json().encode())


def take(messages: Iterator[Message], count: int) -> list[Message]:
    """The next ``count`` messages, or fewer if the source runs out."""
    out = []
    for message in messages:
        out.append(message)
        if len(out) == count:
            break
    return out


def _row(cells: Sequence[object]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _dist_cells(d: Distribution) -> list[str]:
    return [f"{d.p50:,.0f}", f"{d.p95:,.0f}", f"{d.p99:,.0f}", f"{d.max:,.0f}"]


def markdown(report: Report) -> str:
    """The report as Markdown tables, for the run folder and the docs page."""
    lines = [f"Load test of {report.started_at}", ""]
    lines += ["| Hardware | |", "|---|---|"]
    lines += [_row([k, v]) for k, v in report.hardware.items()]
    lines += ["", "| Setting | Value |", "|---|---|"]
    lines += [_row([k, v]) for k, v in report.settings.items()]
    if report.drains:
        lines += [
            "",
            "Throughput, draining a preloaded backlog",
            "",
            "| Consumers | Events | Seconds | Events per second | "
            "Outbox lag p50 ms | p95 ms | p99 ms | max ms |",
            "|---|---|---|---|---|---|---|---|",
        ]
        lines += [
            _row(
                [
                    d.consumers,
                    f"{d.events:,}",
                    f"{d.seconds:.1f}",
                    f"{d.per_second:,.0f}",
                    *_dist_cells(d.outbox_lag),
                ]
            )
            for d in report.drains
        ]
    if report.paced:
        p = report.paced
        lines += [
            "",
            f"End to end at a steady {p.rate:,} events per second "
            f"({p.events:,} events, {p.consumers} consumer)",
            "",
            "| From send to | Events | p50 ms | p95 ms | p99 ms | max ms |",
            "|---|---|---|---|---|---|",
            _row(["appended to the log", f"{p.appended.count:,}", *_dist_cells(p.appended)]),
            _row(
                [
                    "covered by a signed checkpoint",
                    f"{p.checkpointed.count:,}",
                    *_dist_cells(p.checkpointed),
                ]
            ),
            _row(["announced by the outbox", f"{p.announced.count:,}", *_dist_cells(p.announced)]),
            _row(
                [
                    "outbox row to published (lag)",
                    f"{p.outbox_lag.count:,}",
                    *_dist_cells(p.outbox_lag),
                ]
            ),
        ]
    if report.proofs:
        lines += [
            "",
            f"Inclusion proofs from the API, log of {report.proof_tree_size:,} leaves",
            "",
            "| Requests | p50 ms | p95 ms | p99 ms | max ms |",
            "|---|---|---|---|---|",
            _row([f"{report.proofs.count:,}", *_dist_cells(report.proofs)]),
        ]
    if report.partitions:
        lines += ["", "| Partition | Events |", "|---|---|"]
        lines += [_row([k, f"{v:,}"]) for k, v in sorted(report.partitions.items())]
    return "\n".join(lines) + "\n"


# Everything below talks to real processes, Kafka, and Postgres. It is exercised by
# `make load-test`, not by the unit suite.


class Services:  # pragma: no cover - exercised by make load-test
    """The pipeline's host processes, started and stopped by name."""

    def __init__(self, logs: Path, env: dict[str, str]) -> None:
        """Write each process's output to ``logs/<name>.log``."""
        self.logs = logs
        self.env = env
        self.running: dict[str, subprocess.Popen[bytes]] = {}

    def start(self, name: str, *command: str) -> None:
        """Start a command from ``backend/`` under ``name``."""
        log = (self.logs / f"{name}.log").open("ab")
        self.running[name] = subprocess.Popen(  # noqa: S603 - fixed commands from this module
            command, cwd=BACKEND, env=self.env, stdout=log, stderr=subprocess.STDOUT
        )

    def manage(self, name: str, *args: str) -> None:
        """Start a Django management command under ``name``."""
        self.start(name, sys.executable, "manage.py", *args)

    def stop(self, name: str) -> None:
        """Interrupt a process like Ctrl+C, so it finishes its batch; kill it after a minute."""
        process = self.running.pop(name, None)
        if process is None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def stop_all(self) -> None:
        """Stop everything still running."""
        for name in list(self.running):
            self.stop(name)


class Probe:  # pragma: no cover - exercised by make load-test
    """Read-only queries against the throwaway ledger."""

    def __init__(self, url: str, appended_topic: str) -> None:
        """Connect with ``url``; outbox measurements read ``appended_topic`` rows."""
        import psycopg

        self.conn = psycopg.connect(url, autocommit=True)
        self.topic = appended_topic

    def scalar(self, sql: str, params: Sequence[object] = ()) -> Any:  # noqa: ANN401
        """The first column of the first row, or None."""
        row = self.conn.execute(sql, params).fetchone()
        return None if row is None else row[0]

    def rows(self, sql: str, params: Sequence[object] = ()) -> list[tuple[Any, ...]]:
        """Every row."""
        return self.conn.execute(sql, params).fetchall()

    def size(self) -> int:
        """The log's size: the next leaf index."""
        return int(self.scalar("SELECT next_leaf_index FROM merkle_log_head WHERE id = 1"))

    def processed(self) -> int:
        """Events the consumers have finished with: appended, or refused as duplicates.

        The gold data includes injected duplicates, which the ledger refuses, so the
        log alone never reaches the number of events sent.
        """
        return int(
            self.scalar(
                "SELECT (SELECT next_leaf_index FROM merkle_log_head WHERE id = 1)"
                " + (SELECT count(*) FROM dedupe_rejection)"
            )
        )

    def reached(self, processed: int) -> bool:
        """Whether at least ``processed`` events have been appended or refused."""
        return self.processed() >= processed

    def offset(self) -> float:
        """Seconds the database clock is ahead of the host's (see :func:`clock_offset`)."""
        samples = []
        for _ in range(20):
            before = time.time()
            db = float(self.scalar("SELECT extract(epoch FROM clock_timestamp())"))
            samples.append((before, db, time.time()))
        return clock_offset(samples)

    def settled(self, size: int) -> bool:
        """Every event appended, announced, published, and checkpointed."""
        return bool(
            self.scalar(
                "SELECT (SELECT next_leaf_index FROM merkle_log_head) >= %s"
                " AND (SELECT count(*) FROM outbox WHERE published_at IS NULL) = 0"
                " AND (SELECT count(*) FROM outbox WHERE topic = %s) >= %s"
                " AND coalesce((SELECT max(tree_size) FROM ledger_batch), 0) >= %s",
                [size, self.topic, size, size],
            )
        )

    def outbox_lag(self, lo: int, hi: int) -> list[float]:
        """Milliseconds from outbox row to publication, for leaves ``[lo, hi)``."""
        return [
            float(r[0])
            for r in self.rows(
                "SELECT extract(epoch FROM published_at - created_at) * 1000 FROM outbox"
                " WHERE topic = %s AND (payload->>'leaf_index')::bigint >= %s"
                " AND (payload->>'leaf_index')::bigint < %s",
                [self.topic, lo, hi],
            )
        ]


def wait_for(check: Callable[[], bool], timeout: float, what: str) -> None:  # pragma: no cover
    """Poll ``check`` four times a second until it holds, or give up after ``timeout``."""
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise TimeoutError(f"gave up waiting for {what} after {timeout:.0f} s")
        time.sleep(0.25)


def producer(bootstrap: str) -> Any:  # noqa: ANN401  # pragma: no cover
    """A producer configured like the replay's: idempotent, every replica confirms."""
    from confluent_kafka import Producer

    return Producer(
        {
            "bootstrap.servers": bootstrap,
            "acks": "all",
            "enable.idempotence": True,
            "linger.ms": 5,
            "compression.type": "lz4",
        }
    )


def send(  # pragma: no cover - exercised by make load-test
    sink: Any,  # noqa: ANN401
    topic: str,
    messages: Sequence[Message],
    rate: int | None = None,
) -> dict[str, float]:
    """Publish messages, paced when ``rate`` is set; return each event's send time."""
    sent: dict[str, float] = {}
    started = time.monotonic()
    for n, message in enumerate(messages):
        if rate:
            ahead = started + n / rate - time.monotonic()
            if ahead > 0:
                time.sleep(ahead)
        while True:
            try:
                sent[message.event_id] = time.time()
                sink.produce(topic, value=message.value, key=message.key)
                break
            except BufferError:
                sink.poll(0.05)
        sink.poll(0)
    if sink.flush(120):
        raise RuntimeError("the broker did not confirm every message")
    return sent


def hardware(profile: str, project: str) -> dict[str, str]:  # pragma: no cover
    """The host, the Colima VM, and each container's image and memory limit."""

    def sh(*cmd: str) -> str:
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603 - fixed commands
            return done.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    info = {"Host": f"{platform.system()} {platform.release()}, {platform.machine()}"}
    if platform.system() == "Darwin":
        host_gib = int(sh("sysctl", "-n", "hw.memsize") or 0) / 2**30
        info["CPU"] = f"{sh('sysctl', '-n', 'machdep.cpu.brand_string')}, {os.cpu_count()} cores"
        info["Memory"] = f"{host_gib:.0f} GiB"
    else:
        info["CPU"] = f"{os.cpu_count()} cores"
    for line in sh("colima", "list", "--json").splitlines():
        vm = json.loads(line)
        if vm.get("name") == profile:
            info["VM"] = (
                f"Colima {profile}: {vm.get('cpus')} CPUs, {int(vm.get('memory', 0)) / 2**30:.0f}"
                f" GiB memory"
            )
    docker = ["docker", "--context", f"colima-{profile}"]
    ids = sh(*docker, "ps", "-q", "--filter", f"label=com.docker.compose.project={project}")
    for cid in ids.split():
        name, image, memory = sh(
            *docker,
            "inspect",
            "--format",
            '{{index .Config.Labels "com.docker.compose.service"}} {{.Config.Image}}'
            " {{.HostConfig.Memory}}",
            cid,
        ).split()
        info[name.capitalize()] = f"{image}, limit {int(memory) / 2**20:,.0f} MiB"
    info["Python"] = platform.python_version()
    return info


def proof_latencies(api: str, event_ids: Sequence[str]) -> list[float]:  # pragma: no cover
    """Milliseconds per proof request, one at a time; the first warms the tree and is dropped."""
    out = []
    for n, event_id in enumerate(event_ids):
        started = time.perf_counter()
        with urllib.request.urlopen(f"{api}/api/v1/events/{event_id}/proof", timeout=30) as r:  # noqa: S310 - the configured local API
            r.read()
        if n:  # the first request warms the proof tree and is not counted
            out.append((time.perf_counter() - started) * 1000)
    return out


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - exercised by make load-test
    """Run the three measurements against the stack ``make load-test`` started."""
    from config.env import app_settings
    from tallyproof_pipeline.settings import REPO_ROOT, get_settings

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--events", type=int, default=30_000, help="events per throughput run")
    parser.add_argument("--consumers", default="1,2,3", help="consumer counts to drain with")
    parser.add_argument("--paced-events", type=int, default=15_000)
    parser.add_argument(
        "--paced-share", type=float, default=0.5, help="steady rate as a share of the ceiling"
    )
    parser.add_argument("--proofs", type=int, default=500, help="inclusion proofs to time")
    parser.add_argument("--source", type=Path, default=get_settings().gold_dir / "events.jsonl.gz")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "var" / "load-test")
    args = parser.parse_args(argv)

    env = app_settings()
    profile = os.environ.get("COLIMA_PROFILE", "tallyproof")
    project = os.environ.get("LOAD_TEST_PROJECT", "tallyproof-load")
    started = datetime.now(UTC)
    run_dir = args.out / started.strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    child_env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.local",
        "WITNESS_OTS_ENABLED": "false",
        "WITNESS_EXPORT_PATH": str(run_dir / "checkpoints.jsonl"),
        "API_THROTTLE_ANON_READS": "1000000/min",
        "LOG_LEVEL": "WARNING",
    }
    counts = [int(c) for c in args.consumers.split(",")]
    report = Report(
        started_at=started.strftime("%Y-%m-%d %H:%M UTC"),
        hardware=hardware(profile, project),
        settings={
            "Events per throughput run": f"{args.events:,}",
            "Raw topic partitions": "3",
            "INGEST_MAX_BATCH": str(env.ingest_max_batch),
            "Checkpoint every": (
                f"{env.merkle_batch_max_size} events or {env.merkle_batch_max_age_ms} ms"
            ),
            "External timestamping": "off for the test",
            "Source": "gold events in log order, valid events only",
        },
    )
    services = Services(run_dir, child_env)
    probe = Probe(env.db_url.get_secret_value(), env.kafka_topic_ledger_appended)
    sink = producer(env.kafka_bootstrap_servers)
    topic = env.kafka_topic_events_raw
    source = read_messages(args.source)
    try:
        services.manage("checkpointer", "checkpointer")
        services.manage("project", "project")
        services.manage("relay", "relay_outbox")
        for consumers in counts:
            lo, done = probe.size(), probe.processed()
            batch = take(source, args.events)
            for n in range(consumers):
                services.manage(f"ingest-{n}", "ingest")
            time.sleep(SETTLE_SECONDS)  # let the group finish rebalancing before the clock starts
            print(f"publishing {len(batch):,} events to {consumers} consumer(s)", flush=True)
            send(sink, topic, batch)
            wait_for(partial(probe.reached, done + len(batch)), 1800, "the backlog to drain")
            hi = probe.size()
            span, last = probe.rows(
                "WITH s AS (SELECT ingested_at FROM ledger_event"
                "  WHERE leaf_index >= %s AND leaf_index < %s)"
                " SELECT extract(epoch FROM max(ingested_at) - min(ingested_at)),"
                "  (SELECT count(*) FROM s WHERE ingested_at = (SELECT max(ingested_at) FROM s))"
                " FROM s",
                [lo, hi],
            )[0]
            seconds, per_second = drain_rate(hi - lo, int(last), float(span))
            for n in range(consumers):
                services.stop(f"ingest-{n}")
            wait_for(partial(probe.settled, hi), 600, "the projections to catch up")
            drain = Drain(
                consumers,
                hi - lo,
                seconds,
                per_second,
                distribution(probe.outbox_lag(lo, hi)),
            )
            report.drains.append(drain)
            print(f"  {drain.per_second:,.0f} events per second", flush=True)

        ceiling = max(d.per_second for d in report.drains)
        rate = paced_rate(ceiling, args.paced_share)
        lo, done = probe.size(), probe.processed()
        batch = take(source, args.paced_events)
        services.manage("ingest-0", "ingest")
        time.sleep(SETTLE_SECONDS)  # let the consumer join the group before the clock starts
        print(f"publishing {len(batch):,} events at {rate:,} per second", flush=True)
        sent = send(sink, topic, batch, rate)
        wait_for(partial(probe.reached, done + len(batch)), 600, "the paced events to arrive")
        hi = probe.size()
        wait_for(partial(probe.settled, hi), 600, "the paced events to settle")
        services.stop("ingest-0")
        offset = probe.offset()
        rows = probe.rows(
            "SELECT e.public_id, extract(epoch FROM e.ingested_at),"
            " (SELECT extract(epoch FROM b.closed_at) FROM ledger_batch b"
            "   WHERE b.tree_size > e.leaf_index ORDER BY b.tree_size LIMIT 1),"
            " extract(epoch FROM o.published_at)"
            " FROM ledger_event e LEFT JOIN outbox o"
            "   ON o.topic = %s AND o.payload->>'event_id' = e.public_id"
            " WHERE e.leaf_index >= %s AND e.leaf_index < %s",
            [env.kafka_topic_ledger_appended, lo, hi],
        )

        def at(i: int) -> list[tuple[str, float | None]]:
            return [(r[0], None if r[i] is None else float(r[i])) for r in rows]

        report.paced = Paced(
            rate,
            len(batch),
            1,
            distribution(latencies(sent, at(1), offset)),
            distribution(latencies(sent, at(2), offset)),
            distribution(latencies(sent, at(3), offset)),
            distribution(probe.outbox_lag(lo, hi)),
        )
        print(f"  append p95 {report.paced.appended.p95:,.0f} ms", flush=True)

        services.start(
            "api",
            str(Path(sys.executable).parent / "gunicorn"),
            "config.wsgi",
            "-c",
            "config/gunicorn_conf.py",
            "--bind",
            env.api_base_url.split("://", 1)[1],
        )
        wait_for(partial(_ready, env.api_base_url), 60, "the API")
        sample = [
            r[0]
            for r in probe.rows(
                "SELECT public_id FROM ledger_event ORDER BY random() LIMIT %s",
                [args.proofs + 1],
            )
        ]
        report.proof_tree_size = int(probe.scalar("SELECT max(tree_size) FROM ledger_batch"))
        report.proofs = distribution(proof_latencies(env.api_base_url, sample))
        report.partitions = {
            f"{topic}[{p}]": int(n)
            for p, n in probe.rows("SELECT kafka_partition, count(*) FROM ledger_event GROUP BY 1")
        }
    finally:
        services.stop_all()
    (run_dir / "report.json").write_text(json.dumps(asdict(report), indent=2) + "\n")
    text = markdown(report)
    (run_dir / "report.md").write_text(text)
    print(text)
    print(f"written to {run_dir}")
    return 0


def _ready(api: str) -> bool:  # pragma: no cover
    try:
        with urllib.request.urlopen(f"{api}/readyz", timeout=2) as r:  # noqa: S310 - the configured local API
            return bool(r.status == 200)
    except OSError:
        return False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
