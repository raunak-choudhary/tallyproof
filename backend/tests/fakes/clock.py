"""A clock that moves only when told to, so tests never sleep."""


class FrozenClock:
    """Stands in for ``time.time``, ``time.monotonic``, and ``time.sleep``.

    Call it, or use :meth:`time` or :meth:`monotonic`, for the current time.
    :meth:`sleep` records the wait and moves the clock forward by it, and
    :meth:`advance` moves it without recording a sleep.
    """

    def __init__(self, now: float = 100.0) -> None:
        self.now = now
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds
