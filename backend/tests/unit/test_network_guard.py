import socket

import pytest
import requests

from tests.conftest import NetworkBlockedError


def test_tests_cannot_reach_another_machine():
    with pytest.raises((NetworkBlockedError, requests.ConnectionError)):
        requests.get("http://192.0.2.1/", timeout=1)
    with socket.socket() as sock, pytest.raises(NetworkBlockedError):
        sock.connect(("192.0.2.1", 443))


def test_loopback_stays_open():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket() as client:
            client.connect(server.getsockname())
