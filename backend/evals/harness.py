"""A throwaway, fully built ledger for one evaluation run.

The runner never touches the local stack's database. It starts its own Postgres
in Docker with the same image, role script, and migrations as production, loads
the evaluation dataset and the FAR leaves, runs the journal and reconciliation
projections, and signs one checkpoint with a key used only for evaluations. The
analyst then queries it through the real read-only role.
"""

import hashlib
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from evals.dataset import OUT_DIR
from tallyproof_core.checkpoint import Signer, Verifier
from tallyproof_pipeline.settings import REPO_ROOT

POSTGRES_IMAGE = "pgvector/pgvector:0.8.7-pg16-trixie"
ROLE_SCRIPT = REPO_ROOT / "infra" / "postgres" / "create-roles.sql"
ORIGIN = "eval.tallyproof.dev/log/v1"
ROLES = ("owner", "app", "analyst")
SIGNER = Signer(ORIGIN, Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"eval only").digest()))
"""A fixed key used only here, so runs are reproducible. It signs nothing real."""


@dataclass(frozen=True)
class Built:
    """What the harness built: the signed size and how to verify its checkpoint."""

    tree_size: int
    checkpoint_note: str
    verifier: Verifier
    events: int
    policy_sections: int


def _url(host: str, port: int, role: str, password: str) -> str:
    return f"postgresql://tallyproof_{role}:{password}@{host}:{port}/tallyproof"


@contextmanager
def database() -> Iterator[None]:
    """Start Postgres, create the roles, and point Django at it as the app and analyst."""
    from testcontainers.community.postgres import PostgresContainer

    passwords = {role: secrets.token_urlsafe(16) for role in (*ROLES, "superuser")}
    container = PostgresContainer(
        POSTGRES_IMAGE,
        username="postgres",
        password=passwords["superuser"],
        dbname="tallyproof",
        driver=None,
    ).with_volume_mapping(str(ROLE_SCRIPT), "/infra/create-roles.sql", "ro")
    with container:
        variables = [f"-v{role}_password={passwords[role]}" for role in ROLES]
        result = container.exec(
            [
                "psql",
                "-U",
                "postgres",
                "-d",
                "tallyproof",
                *variables,
                "-f",
                "/infra/create-roles.sql",
            ]
        )
        if result.exit_code != 0:
            raise RuntimeError("the role script failed in the evaluation database")
        host, port = container.get_container_host_ip(), int(container.get_exposed_port(5432))
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
        os.environ["DB_URL"] = _url(host, port, "app", passwords["app"])
        os.environ["DB_ANALYST_URL"] = _url(host, port, "analyst", passwords["analyst"])
        os.environ["MERKLE_LOG_ORIGIN"] = ORIGIN
        os.environ["CHECKPOINT_PUBLIC_KEY"] = SIGNER.verifier_key()
        import django
        from django.core.management import call_command
        from django.db import connections

        django.setup()
        settings = connections["default"].settings_dict
        settings.update(USER="tallyproof_owner", PASSWORD=passwords["owner"])
        call_command("migrate", verbosity=0)
        connections["default"].close()
        settings.update(USER="tallyproof_app", PASSWORD=passwords["app"])
        yield


def build(dataset: Path = OUT_DIR) -> Built:
    """Load a dataset and the FAR leaves, project, and sign one checkpoint."""
    from django.db import transaction

    from apps.ledger.append import Delivery, append
    from apps.ledger.checkpointer import Checkpointer
    from apps.ledger.projections import JournalProjection, catch_up
    from apps.reconciliation.projection import ReconciliationProjection
    from tallyproof_pipeline.gold import read_events
    from tallyproof_pipeline.policy import read_corpus, to_events

    edition, sections = read_corpus(REPO_ROOT / "backend" / "corpus" / "far")
    policy = to_events(edition, sections)
    events = [*read_events(dataset / "events.jsonl.gz"), *policy]
    with transaction.atomic():
        append([Delivery(e, "eval", 0, i) for i, e in enumerate(events)])
    catch_up(JournalProjection())
    catch_up(ReconciliationProjection())
    signed = Checkpointer(SIGNER, batch_max_size=10**9, batch_max_age_ms=1).close()
    return Built(
        signed.tree_size,
        signed.note,
        Verifier.from_verifier_key(SIGNER.verifier_key()),
        len(events),
        len(policy),
    )
