"""Recipient bursts: many new awards to one recipient in an hour, after a quiet month.

On real federal spending, many awards to one vendor in an hour is ordinary: large
schedule contractors get dozens. What stands out is a burst to a recipient that
had no awards at all in the previous 30 days, the pattern of a contract split into
pieces to stay under a review threshold. So the rule is:

    at least ``threshold`` new awards to one recipient within an hour, and none to
    that recipient on any of the 30 days before the day the hour began.

Counting is done with Count-Min Sketches (:mod:`tallyproof_core.sketch`), so memory
doesn't grow with the number of recipients:

- **Hours.** Four sets of one-hour windows, offset by 15 minutes, each with a small
  sketch. Any burst that spans at most 45 minutes falls wholly inside one of them;
  with two sets offset by 30 minutes, a 35-minute burst starting late in the hour
  would be split across every window. When a recipient's estimate reaches
  the threshold, its awards in the window are counted exactly from a two-hour
  buffer of recent awards, so a sketch collision can never raise a break.
- **The quiet month.** One sketch per day for the last 30 days. Sketches never
  undercount, so a collision can only make a quiet recipient look busy and hide a
  burst; it can never invent one. With 65,536 counters a row and four rows, a day
  with 10,000 recipients hides one in about 2,000 checks, and an ordinary day far
  fewer.

Time is the event's ``emitted_at``, its arrival, read in log order.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from tallyproof_core.sketch import CountMinSketch

EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
WINDOW = timedelta(hours=1)
HOP = timedelta(minutes=15)
QUIET_DAYS = 30
THRESHOLD = 8
WINDOW_WIDTH, DAY_WIDTH, DEPTH = 4096, 65_536, 4


@dataclass(frozen=True)
class Award:
    """A new award as the rule sees it."""

    at: datetime
    recipient: str
    event_id: str
    award_key: str


@dataclass(frozen=True)
class Burst:
    """A detected burst: the awards in the window, oldest first."""

    recipient: str
    start: datetime
    awards: tuple[Award, ...]


@dataclass
class BurstDetector:
    """Feed it new awards in log order; it returns a burst when one completes."""

    threshold: int = THRESHOLD
    window: timedelta = WINDOW
    hop: timedelta = HOP
    quiet_days: int = QUIET_DAYS
    _windows: dict[tuple[int, int], CountMinSketch] = field(default_factory=dict)
    _days: dict[int, CountMinSketch] = field(default_factory=dict)
    _recent: deque[Award] = field(default_factory=deque)
    _flagged: dict[str, datetime] = field(default_factory=dict)
    _latest: datetime = EPOCH

    def observe(self, award: Award) -> Burst | None:
        """Count one new award; return the burst it completes, if any."""
        self._latest = max(self._latest, award.at)
        self._recent.append(award)
        while self._recent and self._recent[0].at < self._latest - 2 * self.window:
            self._recent.popleft()
        key = award.recipient.encode("utf-8")
        found: Burst | None = None
        offsets = [k * self.hop for k in range(self.window // self.hop)]
        for offset_index, offset in enumerate(offsets):
            bucket = (award.at - EPOCH - offset) // self.window
            sketch = self._windows.get((offset_index, bucket))
            if sketch is None:
                sketch = self._windows[(offset_index, bucket)] = CountMinSketch(WINDOW_WIDTH, DEPTH)
                for old in [k for k in self._windows if k[0] == offset_index and k[1] < bucket - 1]:
                    del self._windows[old]
            if found is None and sketch.add(key) >= self.threshold:
                start = EPOCH + offset + bucket * self.window
                found = self._confirm(award.recipient, start)
            elif found is not None:
                sketch.add(key)
        day = award.at.date().toordinal()
        sketch = self._days.get(day)
        if sketch is None:
            sketch = self._days[day] = CountMinSketch(DAY_WIDTH, DEPTH)
            for stale in [d for d in self._days if d < day - self.quiet_days - 1]:
                del self._days[stale]
        sketch.add(key)
        return found

    def _confirm(self, recipient: str, start: datetime) -> Burst | None:
        end = start + self.window
        awards = tuple(a for a in self._recent if a.recipient == recipient and start <= a.at < end)
        if len(awards) < self.threshold:
            return None  # the sketch overcounted; the exact count says no
        previous = self._flagged.get(recipient)
        if previous is not None and abs(start - previous) < self.window:
            return None  # the other window already reported this burst
        if not self._quiet_before(recipient, start.date()):
            return None
        self._flagged[recipient] = start
        return Burst(recipient, start, awards)

    def _quiet_before(self, recipient: str, first_day: date) -> bool:
        """No award to the recipient on any of the ``quiet_days`` days before ``first_day``."""
        key = recipient.encode("utf-8")
        day = first_day.toordinal()
        return all(
            (sketch := self._days.get(d)) is None or sketch.estimate(key) == 0
            for d in range(day - self.quiet_days, day)
        )
