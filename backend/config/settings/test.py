"""Unit and module tests: fixed, non-secret values so tests never depend on a .env file."""

import os

_TEST_VALUES = {
    "DJANGO_SECRET_KEY": "test-only-not-secret",
    "DJANGO_ALLOWED_HOSTS": "testserver,localhost",
    "DATA_CLASSIFICATION": "public-no-pii",
    "DB_URL": "postgres://tallyproof_app@localhost:5432/tallyproof_test",
    "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
    "MERKLE_LOG_ORIGIN": "test.tallyproof.dev/log/v1",
    "CHECKPOINT_PUBLIC_KEY": "test.tallyproof.dev/log/v1+00000000+AQ==",
}
for _name, _value in _TEST_VALUES.items():
    os.environ.setdefault(_name, _value)

from config.settings.base import *  # noqa: E402
