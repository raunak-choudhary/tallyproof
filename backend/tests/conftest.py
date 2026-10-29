import ipaddress
import os
import socket
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, settings

# Shared cross-language test vectors live at the repository root.
VECTORS_DIR = Path(__file__).resolve().parents[2] / "testdata" / "vectors"

# CI runs a fixed, larger set of examples so failures reproduce exactly.
settings.register_profile(
    "ci", derandomize=True, max_examples=300, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile("dev", max_examples=100)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


class NetworkBlockedError(RuntimeError):
    """A test tried to reach a machine other than this one."""


def _local(address: Any) -> bool:
    if not isinstance(address, tuple):
        return True  # a Unix socket path, such as Docker's
    host = str(address[0])
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def no_outside_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse any connection off this machine, so no test can reach a real service.

    Loopback stays open for the containers integration tests start, Spark's local
    gateway, and Docker's Unix socket. A model, a calendar server, or a data API has
    to be faked.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def connect(sock: socket.socket, address: Any) -> None:
        if not _local(address):
            raise NetworkBlockedError(f"tests may not connect to {address!r}")
        real_connect(sock, address)

    def connect_ex(sock: socket.socket, address: Any) -> int:
        if not _local(address):
            raise NetworkBlockedError(f"tests may not connect to {address!r}")
        return real_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
