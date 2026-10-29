import pytest

from tallyproof_core.addresses import address_key


@pytest.mark.parametrize(
    ("address", "key"),
    [
        ("203.0.113.9", "203.0.113.9"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.9", "203.0.113.9"),
        ("unknown", "unknown"),
        ("", ""),
    ],
)
def test_ipv6_addresses_share_a_key_per_slash_64(address, key):
    assert address_key(address) == key
