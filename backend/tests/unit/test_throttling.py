from rest_framework.test import APIRequestFactory

from apps.analyst.api import QueryRateThrottle
from apps.ledger.api.throttling import ClientRateThrottle


def test_rotating_ipv6_addresses_in_one_network_count_as_one_client():
    factory = APIRequestFactory()
    first = factory.get("/", REMOTE_ADDR="2001:db8:1:2::1")
    second = factory.get("/", REMOTE_ADDR="2001:db8:1:2::abcd")
    for throttle in (ClientRateThrottle(), QueryRateThrottle()):
        assert throttle.get_ident(first) == throttle.get_ident(second) == "2001:db8:1:2::/64"
    assert ClientRateThrottle().get_ident(factory.get("/", REMOTE_ADDR="203.0.113.9")) == (
        "203.0.113.9"
    )
