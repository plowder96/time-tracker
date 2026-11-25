"""File-backed repository, schema, and transaction checks."""

from datetime import date
import sqlite3
import os
from pathlib import Path
import pytest

from time_tracker.storage import (
    MissingBlockError, OverlapError, StorageError, TimeBlockRepository,
    UnsupportedSchemaError, resolve_database_path,
)


DAY = date(2026, 11, 5)


def test_database_path_uses_only_absolute_xdg_home(tmp_path):
    assert resolve_database_path(environ={}, home=None) == (
        Path(os.environ["HOME"]) / ".local/share/time-tracker/time-tracker.sqlite3"
    )
    home = tmp_path / "home"
    assert resolve_database_path(environ={}, home=home) == (
        home / ".local/share/time-tracker/time-tracker.sqlite3"
    )
    assert resolve_database_path(environ={"XDG_DATA_HOME": "relative/data"}, home=home) == (
        home / ".local/share/time-tracker/time-tracker.sqlite3"
    )
    assert resolve_database_path(environ={"XDG_DATA_HOME": str(tmp_path / "data")}, home=home) == (
        tmp_path / "data/time-tracker/time-tracker.sqlite3"
    )


def test_create_reopen_update_delete_and_week_order(tmp_path):
    path = tmp_path / "nested" / "blocks.sqlite3"
    with TimeBlockRepository(path) as repository:
        first = repository.save(DAY, 540, 570, "It's time ☕")
        second = repository.save(DAY, 570, 600, "adjacent")
        other_week = repository.save(date(2026, 11, 15), 540, 600, "later")
        assert first.id > 0
        assert second.id != first.id
        assert repository.list_week(DAY) == [first, second]
        assert other_week not in repository.list_week(DAY)
        assert repository.connection.execute("PRAGMA user_version").fetchone()[0] == 1

    with TimeBlockRepository(path) as repository:
        assert repository.list_week(DAY) == [first, second]
        edited = repository.save(DAY, 540, 570, "changed", block_id=first.id)
        assert edited.id == first.id
        repository.delete(second.id)
        assert repository.list_week(DAY) == [edited]

    with TimeBlockRepository(path) as repository:
        assert repository.list_week(DAY) == [edited]
        repository.delete(edited.id)
        assert repository.list_week(DAY) == []


def test_overlap_rejection_and_failed_update_preserve_existing_rows(tmp_path):
    with TimeBlockRepository(tmp_path / "blocks.sqlite3") as repository:
        first = repository.save(DAY, 540, 570, "first")
        second = repository.save(DAY, 570, 600, "second")
        for start, end in [(550, 580), (530, 610), (540, 570)]:
            with pytest.raises(OverlapError):
                repository.save(DAY, start, end, "collision")
        with pytest.raises(OverlapError):
            repository.save(DAY, 550, 580, "bad edit", block_id=second.id)
        assert repository.save(DAY, 540, 570, "first", block_id=first.id) == first
        assert repository.list_week(DAY) == [first, second]
        assert repository.save(date(2026, 11, 6), 540, 570, "other day").id > 0
        assert not repository.connection.in_transaction


def test_missing_record_and_invalid_intervals_write_nothing(tmp_path):
    with TimeBlockRepository(tmp_path / "blocks.sqlite3") as repository:
        with pytest.raises(MissingBlockError):
            repository.save(DAY, 540, 600, block_id=99)
        with pytest.raises(MissingBlockError):
            repository.delete(99)
        for start, end in [(540, 540), (600, 540), (1439, 1440)]:
            with pytest.raises(ValueError):
                repository.save(DAY, start, end)
        assert repository.list_week(DAY) == []
        assert not repository.connection.in_transaction


def test_newer_schema_is_rejected_without_changes(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 2")
        connection.execute("CREATE TABLE future_data (value TEXT)")
        connection.execute("INSERT INTO future_data VALUES ('keep')")
    with pytest.raises(UnsupportedSchemaError, match="newer"):
        TimeBlockRepository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT value FROM future_data").fetchone()[0] == "keep"


def test_schema_constraints_reject_bad_direct_writes(tmp_path):
    with TimeBlockRepository(tmp_path / "blocks.sqlite3") as repository:
        for start, end in [(-1, 1), (1439, 1440), (600, 600), (600, 599), (0, 1440)]:
            with pytest.raises(sqlite3.IntegrityError):
                repository.connection.execute(
                    """INSERT INTO time_blocks (date, start_minute, end_minute)
                       VALUES (?, ?, ?)""", (DAY.isoformat(), start, end),
                )
        assert repository.list_week(DAY) == []


def test_sql_failure_rolls_back_and_later_save_can_succeed(tmp_path):
    with TimeBlockRepository(tmp_path / "blocks.sqlite3") as repository:
        repository.connection.execute("""
            CREATE TRIGGER reject_description BEFORE INSERT ON time_blocks
            WHEN NEW.description = 'reject'
            BEGIN SELECT RAISE(ABORT, 'rejected by trigger'); END
        """)
        with pytest.raises(StorageError, match="rejected by trigger"):
            repository.save(DAY, 540, 600, "reject")
        assert not repository.connection.in_transaction
        assert repository.list_week(DAY) == []
        assert repository.save(DAY, 540, 600, "accepted").id > 0


def test_two_connections_check_overlap_under_write_transaction(tmp_path):
    path = tmp_path / "blocks.sqlite3"
    with TimeBlockRepository(path) as first, TimeBlockRepository(path) as second:
        first.save(DAY, 540, 570)
        with pytest.raises(OverlapError):
            second.save(DAY, 550, 580)
        assert len(second.list_week(DAY)) == 1
