"""Application-level validation, persistence, and error boundaries."""

from datetime import date, datetime
import sqlite3

import pytest

from time_tracker.service import ServiceStorageError, TimeTrackerService, ValidationError


DAY = date(2026, 11, 5)


def test_injected_clock_and_week_lookup(tmp_path):
    seen = []

    def clock():
        seen.append(True)
        return datetime(2026, 11, 5, 14, 37)

    with TimeTrackerService(tmp_path / "blocks.sqlite3", clock=clock) as service:
        block = service.save_block(DAY, "09:05", "10:00", "coffee ☕")
        assert service.current_time() == datetime(2026, 11, 5, 14, 37)
        assert service.list_week() == [block]
        assert len(seen) == 2
        assert service.list_week(date(2026, 11, 15)) == []


def test_create_reopen_update_remove_and_adjacency(tmp_path):
    path = tmp_path / "blocks.sqlite3"
    with TimeTrackerService(path) as service:
        first = service.save_block(DAY, "09:00", "09:30", "first")
        second = service.save_block(DAY, "09:30", "10:00", "second")
        assert first.id != second.id
        assert service.list_week(DAY) == [first, second]

    with TimeTrackerService(path) as service:
        assert service.list_week(DAY) == [first, second]
        edited = service.save_block(DAY, "09:00", "09:30", "edited", block_id=first.id)
        assert edited.id == first.id
        service.remove_block(second.id)
        assert service.list_week(DAY) == [edited]

    with TimeTrackerService(path) as service:
        assert service.list_week(DAY) == [edited]


@pytest.mark.parametrize(
    ("start", "end", "field"),
    [
        ("9:00", "10:00", "start_time"),
        ("09:00", "10:0", "end_time"),
        ("09:00", "24:00", "end_time"),
        ("09:00", "09:00", "end_time"),
        ("10:00", "09:00", "end_time"),
        ("23:59", "23:59", "end_time"),
    ],
)
def test_invalid_editor_times_do_not_write(tmp_path, start, end, field):
    with TimeTrackerService(tmp_path / "blocks.sqlite3") as service:
        with pytest.raises(ValidationError) as caught:
            service.save_block(DAY, start, end)
        assert caught.value.field == field
        assert service.list_week(DAY) == []


@pytest.mark.parametrize(
    ("desc","field"),
    [
        (True,"description"),
        (False,"description"),
        (1,"description")
    ]
)
def test_invalid_description_type(tmp_path,desc,field):
    with TimeTrackerService(tmp_path / "blocks.sqlite3") as service:
        with pytest.raises(ValidationError) as caught:
            service.save_block(DAY,"09:00","09:30",desc)
        assert caught.value.field == field
        assert service.list_week(DAY) == []

def test_overlap_and_stale_ids_are_validation_errors(tmp_path):
    with TimeTrackerService(tmp_path / "blocks.sqlite3") as service:
        first = service.save_block(DAY, "09:00", "09:30")
        second = service.save_block(DAY, "09:30", "10:00")
        with pytest.raises(ValidationError, match="overlaps"):
            service.save_block(DAY, "09:15", "09:45")
        with pytest.raises(ValidationError, match="overlaps"):
            service.save_block(DAY, "09:15", "09:45", block_id=second.id)
        with pytest.raises(ValidationError, match="no longer exists"):
            service.save_block(DAY, "10:00", "10:30", block_id=999)
        with pytest.raises(ValidationError, match="no longer exists"):
            service.remove_block(999)
        assert service.save_block(DAY, "09:00", "09:30", block_id=first.id) == first
        assert service.list_week(DAY) == [first, second]


def test_storage_errors_are_distinct_and_failed_save_preserves_rows(tmp_path):
    path = tmp_path / "blocks.sqlite3"
    with TimeTrackerService(path) as service:
        existing = service.save_block(DAY, "09:00", "09:30", "keep")
        with sqlite3.connect(path) as connection:
            connection.execute("""
                CREATE TRIGGER reject_edit BEFORE UPDATE ON time_blocks
                BEGIN SELECT RAISE(ABORT, 'rejected by trigger'); END
            """)
        with pytest.raises(ServiceStorageError, match="rejected by trigger"):
            service.save_block(DAY, "10:00", "10:30", "changed", block_id=existing.id)
        assert service.list_week(DAY) == [existing]


def test_database_open_error_is_service_storage_error(tmp_path):
    parent_file = tmp_path / "not_a_directory"
    parent_file.write_text("occupied")
    with pytest.raises(ServiceStorageError, match="Could not open"):
        TimeTrackerService(parent_file / "blocks.sqlite3")
