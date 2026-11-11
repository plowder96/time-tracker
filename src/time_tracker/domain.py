"""Qt-independent calendar, time-block, draft, and grid-focus rules."""

from dataclasses import dataclass
from datetime import date, timedelta
import re
from collections.abc import Iterable


LAST_END_MINUTE = 23 * 60 + 59
MINUTES_PER_DAY = 24 * 60
_TIME_PATTERN = re.compile(r"[0-9]{2}:[0-9]{2}\Z", re.ASCII)


@dataclass(frozen=True)
class Interval:
    """A half-open range of local wall-clock minutes: [start, end)."""

    start: int
    end: int


@dataclass(frozen=True)
class TimeBlock:
    id: int
    date: date
    start_minute: int
    end_minute: int
    description: str


@dataclass(frozen=True)
class FocusCell:
    """One hour cell in a Sunday-first week."""

    weekday: int
    hour: int

    def __post_init__(self) -> None: # Validates the constructed values are within seven-day/24-hour grid
        if not 0 <= self.weekday <= 6 or not 0 <= self.hour <= 23:
            raise ValueError("Focus must be within the seven-day, 24-hour grid")


def parse_time(text: str) -> int: # translates user-facing time values to internal integer representation
    """Parse exactly HH:MM in 24-hour ASCII notation."""

    if not isinstance(text, str) or _TIME_PATTERN.fullmatch(text) is None:
        raise ValueError("Time must use exactly HH:MM in 24-hour format")
    hour, minute = int(text[:2]), int(text[3:])
    if hour > 23 or minute > 59:
        raise ValueError("Hour must be 00–23 and minute must be 00–59")
    return hour * 60 + minute


def format_time(minute: int) -> str: # translates internal integer time values to user-facing time values
    """Format a minute index as HH:MM, including 23:59."""

    if not isinstance(minute, int) or isinstance(minute, bool) or not 0 <= minute < MINUTES_PER_DAY:
        raise ValueError("Time minute must be an integer from 0 through 1439")
    return f"{minute // 60:02d}:{minute % 60:02d}"


def validate_interval(start: int, end: int) -> Interval:
    """Require a positive, single-day recordable interval."""

    if (not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or not 0 <= start < end <= LAST_END_MINUTE):
        raise ValueError("Block must have positive duration and end by 23:59")
    return Interval(start, end)


def sunday_of(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def week_bounds(day: date) -> tuple[date, date]:
    """Return Sunday and the following Sunday (exclusive)."""

    start = sunday_of(day)
    return start, start + timedelta(days=7)


def shift_week(day: date, weeks: int) -> date:
    """Move a displayed week by whole weeks; focus is kept separately."""

    return sunday_of(day) + timedelta(weeks=weeks)


def intersects(first: Interval, second: Interval) -> bool:
    """Test half-open overlap; touching endpoints are adjacent."""

    return first.start < second.end and second.start < first.end


def first_intersecting_block(blocks: Iterable[TimeBlock], hour: int) -> TimeBlock | None:
    """Pick the earliest saved block touched by Enter in an hour cell."""

    cell = hour_interval(hour)
    matches = (block for block in blocks
               if intersects(Interval(block.start_minute, block.end_minute), cell))
    return min(matches, key=lambda block: (block.start_minute, block.id), default=None)


def hour_interval(hour: int) -> Interval:
    if not isinstance(hour, int) or isinstance(hour, bool) or not 0 <= hour <= 23:
        raise ValueError("Hour must be an integer from 0 through 23")
    return Interval(hour * 60, min((hour + 1) * 60, LAST_END_MINUTE))


def block_at_position(blocks: Iterable[TimeBlock], position: float) -> TimeBlock | None:
    """Find the block under a continuous minute position in one day."""

    return next((block for block in blocks
                 if block.start_minute <= position < block.end_minute), None)


def gap_at_position(blocks: Iterable[TimeBlock], hour: int, position: float) -> Interval | None:
    """Find the recordable empty gap containing a click in an hour cell.

    ``position`` is the unrounded minute coordinate derived from the grid's Y
    position. Saved blocks are expected to be non-overlapping and from one day.
    """

    cell = hour_interval(hour)
    if not cell.start <= position < cell.end:
        return None

    occupied = sorted(
        (max(cell.start, block.start_minute), min(cell.end, block.end_minute))
        for block in blocks
        if block.start_minute < cell.end and block.end_minute > cell.start
    )
    gap_start = cell.start
    for start, end in occupied:
        if gap_start <= position < start:
            return Interval(gap_start, start)
        if start <= position < end:
            return None
        gap_start = max(gap_start, end)
    return Interval(gap_start, cell.end) if gap_start <= position < cell.end else None


_MOVEMENT = {
    "left": (-1, 0), "h": (-1, 0),
    "right": (1, 0), "l": (1, 0),
    "up": (0, -1), "k": (0, -1),
    "down": (0, 1), "j": (0, 1),
}


def move_focus(cell: FocusCell, direction: str) -> FocusCell:
    """Move one hour cell, stopping at the displayed week/day boundaries."""

    try:
        weekday_delta, hour_delta = _MOVEMENT[direction]
    except (KeyError, TypeError):
        raise ValueError(f"Unsupported focus direction: {direction!r}") from None
    return FocusCell(
        min(6, max(0, cell.weekday + weekday_delta)),
        min(23, max(0, cell.hour + hour_delta)),
    )
