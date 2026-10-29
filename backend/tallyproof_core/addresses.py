"""One key per client for rate limits, however its address is written.

An IPv6 client usually holds a whole /64 and can pick a fresh address in it for
every request, so per-address limits key IPv6 by its /64. An IPv4 address written
as IPv6 (``::ffff:203.0.113.9``) is keyed as the IPv4 address. Anything that
isn't an IP address is kept as it is.
"""

import ipaddress


def address_key(address: str) -> str:
    """The key that per-client limits count against."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)
