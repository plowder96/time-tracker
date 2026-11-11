"""Pure rules used by the later repository, service, and dashboard."""

from datetime import date

import pytest

from time_tracker.domain import (
    FocusCell, Interval, TimeBlock, block_at_position, first_intersecting_block,
    format_time, gap_at_position, hour_interval, intersects, move_focus,
    parse_time, shift_week, sunday_of, validate_interval, week_bounds,
)


@pytest.mark.parametrize("text,minute", [("00:00", 0), ("09:05", 545), ("23:59", 1439)])
def test_exact_time_round_trip(text, minute):
    assert parse_time(text) == minute
    assert format_time(minute) == text


@pytest.mark.parametrize("text", ["9:05", "09:5", "24:00", "12:60", " 09:05", "09:05 ",
                                      "09:05:00", "０９:０５", "09\n:05", "09:05\n"])
def test_invalid_time_text(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_recordable_interval_cutoff_and_adjacency():
    assert validate_interval(0, 1) == Interval(0, 1)
    assert validate_interval(1438, 1439) == Interval(1438, 1439)
    for start, end in [(0, 0), (10, 9), (1439, 1440), (-1, 1), (0, 1440)]:
        with pytest.raises(ValueError):
            validate_interval(start, end)
    with pytest.raises(ValueError):
        format_time(1440)
    assert intersects(Interval(10, 20), Interval(19, 30))
    assert not intersects(Interval(10, 20), Interval(20, 30))


def test_sunday_week_bounds_across_year_and_leap_day():
    assert sunday_of(date(2027, 1, 1)) == date(2026, 12, 27)
    assert week_bounds(date(2027, 1, 1)) == (date(2026, 12, 27), date(2027, 1, 3))
    assert week_bounds(date(2024, 2, 29)) == (date(2024, 2, 25), date(2024, 3, 3))
    assert shift_week(date(2026, 12, 27), 1) == date(2027, 1, 3)
    assert shift_week(date(2027, 1, 3), -1) == date(2026, 12, 27)


def test_enter_chooses_earliest_intersecting_block_and_ignores_ending_boundary():
    day = date(2026, 11, 5)
    ending_at_nine = TimeBlock(1, day, 8 * 60, 9 * 60, "earlier hour")
    later = TimeBlock(2, day, 9 * 60 + 30, 10 * 60, "later")
    earliest = TimeBlock(3, day, 9 * 60, 9 * 60 + 15, "earliest")
    assert first_intersecting_block([later, ending_at_nine, earliest], 9) == earliest
    assert first_intersecting_block([ending_at_nine], 9) is None
    assert hour_interval(23) == Interval(1380, 1439)


def test_click_uses_exact_block_and_minute_aligned_gap():
    day = date(2026, 11, 5)
    blocks = [
        TimeBlock(1, day, 9 * 60, 9 * 60 + 30, "first"),
        TimeBlock(2, day, 9 * 60 + 45, 10 * 60 + 10, "second"),
    ]
    assert block_at_position(blocks, 570) is None
    assert block_at_position(blocks, 585) == blocks[1]
    assert block_at_position(blocks, 569.999) == blocks[0]
    assert gap_at_position(blocks, 9, 570) == Interval(570, 585)
    assert gap_at_position(blocks, 9, 584.999) == Interval(570, 585)
    assert gap_at_position(blocks, 9, 585) is None
    assert gap_at_position(blocks, 10, 610) == Interval(610, 660)


def test_empty_hour_and_excluded_final_minute():
    assert gap_at_position([], 12, 12 * 60 + 30.5) == Interval(720, 780)
    assert gap_at_position([], 23, 1438.999) == Interval(1380, 1439)
    assert gap_at_position([], 23, 1439) is None
    assert gap_at_position([], 23, 1440) is None
    assert gap_at_position([], 12, 11 * 60 + 59) is None


@pytest.mark.parametrize("direction,expected", [
    ("h", FocusCell(2, 12)), ("left", FocusCell(2, 12)),
    ("l", FocusCell(4, 12)), ("right", FocusCell(4, 12)),
    ("k", FocusCell(3, 11)), ("up", FocusCell(3, 11)),
    ("j", FocusCell(3, 13)), ("down", FocusCell(3, 13)),
])
def test_focus_directions(direction, expected):
    assert move_focus(FocusCell(3, 12), direction) == expected


def test_focus_stops_at_day_and_week_boundaries():
    assert move_focus(FocusCell(0, 0), "h") == FocusCell(0, 0)
    assert move_focus(FocusCell(0, 0), "k") == FocusCell(0, 0)
    assert move_focus(FocusCell(6, 23), "l") == FocusCell(6, 23)
    assert move_focus(FocusCell(6, 23), "j") == FocusCell(6, 23)
    with pytest.raises(ValueError):
        move_focus(FocusCell(3, 12), "diagonal")
