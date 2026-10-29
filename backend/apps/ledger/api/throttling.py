"""Per-client rate limits that an IPv6 client can't sidestep by rotating addresses."""

from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle

from tallyproof_core.addresses import address_key


class ClientRateThrottle(AnonRateThrottle):
    """DRF's anonymous throttle, counting each IPv6 /64 as one client."""

    def get_ident(self, request: Request) -> str:
        """The client's address as DRF finds it, keyed by :func:`address_key`."""
        return address_key(super().get_ident(request))
