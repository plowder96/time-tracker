"""Versioned SQLite storage for local time blocks.

The connection uses autocommit mode so each write can explicitly acquire a
write lock before checking for overlaps. The repository contains no Qt code.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from time_tracker.domain import TimeBlock, validate_interval, week_bounds


SCHEMA_VERSION = 1


class StorageError(Exception):
    """The database or its directory could not be used."""


class UnsupportedSchemaError(StorageError):
    """The database was created by a newer application version."""


class OverlapError(ValueError):
    """A proposed block intersects another block on the same date."""


class MissingBlockError(ValueError):
    """An update or deletion refers to a block that no longer exists."""


def resolve_database_path(
    *, environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Use absolute XDG_DATA_HOME, or the standard per-user data directory."""

    variables = os.environ if environ is None else environ
    xdg_home = variables.get("XDG_DATA_HOME", "")
    base = Path(xdg_home) if xdg_home and Path(xdg_home).is_absolute() else (
        Path.home() if home is None else Path(home)
    ) / ".local" / "share"
    return base / "time-tracker" / "time-tracker.sqlite3"


class TimeBlockRepository:
    """Own one SQLite connection and perform atomic block operations."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_database_path() if path is None else Path(path)
        self._connection: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, isolation_level=None, timeout=1.0)
            self._connection.row_factory = sqlite3.Row
            self._initialize_schema()
        except (OSError, sqlite3.Error) as exc:
            self.close()
            raise StorageError(f"Could not open time-block database: {exc}") from exc
        except Exception:
            self.close()
            raise

    def __enter__(self) -> "TimeBlockRepository":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StorageError("Time-block database is closed")
        return self._connection

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def _initialize_schema(self) -> None:
        try:
            with self._write_transaction() as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise UnsupportedSchemaError(
                        f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}"
                    )
                if version == 0:
                    connection.execute("""
                        CREATE TABLE time_blocks (
                            id INTEGER PRIMARY KEY,
                            date TEXT NOT NULL,
                            start_minute INTEGER NOT NULL
                                CHECK (start_minute >= 0 AND start_minute < 1439),
                            end_minute INTEGER NOT NULL
                                CHECK (end_minute > start_minute AND end_minute <= 1439),
                            description TEXT NOT NULL DEFAULT ''
                        )
                    """) # Checks ensure no overlaps at DB level. Needs refactoring if overlapping timeblocks are implemented in the future.
                    connection.execute(
                        "CREATE INDEX time_blocks_date_start ON time_blocks (date, start_minute)"
                    )
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise StorageError(f"Could not initialize time-block database: {exc}") from exc

    @staticmethod
    def _block(row: sqlite3.Row) -> TimeBlock:
        try:
            day = date.fromisoformat(row["date"])
        except (TypeError, ValueError) as exc:
            raise StorageError("Database contains a block with an invalid date") from exc
        if day.isoformat() != row["date"]:
            raise StorageError("Database contains a block with an invalid date")
        return TimeBlock(
            row["id"], day, row["start_minute"], row["end_minute"], row["description"]
        )

    def list_week(self, day: date) -> list[TimeBlock]:
        if not isinstance(day, date):
            raise ValueError("Week lookup requires a calendar date")
        start, end = week_bounds(day)
        try:
            rows = self.connection.execute(
                """SELECT id, date, start_minute, end_minute, description
                   FROM time_blocks WHERE date >= ? AND date < ?
                   ORDER BY date, start_minute, id""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [self._block(row) for row in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"Could not list time blocks: {exc}") from exc

    def save(
        self, day: date, start_minute: int, end_minute: int,
        description: str = "", *, block_id: int | None = None,
    ) -> TimeBlock:
        """Insert or update after checking overlap under the write lock."""

        if not isinstance(day, date):
            raise ValueError("Block date must be a calendar date")
        validate_interval(start_minute, end_minute)
        if not isinstance(description, str):
            raise ValueError("Description must be text")
        if block_id is not None and (type(block_id) is not int or block_id <= 0):
            raise ValueError("Block ID must be a positive integer")
        iso_day = day.isoformat()
        try:
            with self._write_transaction() as connection:
                if block_id is not None and connection.execute(
                    "SELECT 1 FROM time_blocks WHERE id = ?", (block_id,)
                ).fetchone() is None:
                    raise MissingBlockError(f"Time block {block_id} no longer exists")
                overlap = connection.execute(
                    """SELECT id FROM time_blocks
                       WHERE date = ? AND start_minute < ? AND end_minute > ?
                         AND (? IS NULL OR id != ?)
                       LIMIT 1""",
                    (iso_day, end_minute, start_minute, block_id, block_id),
                ).fetchone()
                if overlap is not None:
                    raise OverlapError("Time block overlaps another block on this date")
                if block_id is None:
                    cursor = connection.execute(
                        """INSERT INTO time_blocks (date, start_minute, end_minute, description)
                           VALUES (?, ?, ?, ?)""",
                        (iso_day, start_minute, end_minute, description),
                    )
                    block_id = cursor.lastrowid
                else:
                    connection.execute(
                        """UPDATE time_blocks SET date = ?, start_minute = ?,
                           end_minute = ?, description = ? WHERE id = ?""",
                        (iso_day, start_minute, end_minute, description, block_id),
                    )
            return TimeBlock(block_id, day, start_minute, end_minute, description)
        except sqlite3.Error as exc:
            raise StorageError(f"Could not save time block: {exc}") from exc

    def delete(self, block_id: int) -> None:
        if type(block_id) is not int or block_id <= 0:
            raise ValueError("Block ID must be a positive integer")
        try:
            with self._write_transaction() as connection:
                cursor = connection.execute("DELETE FROM time_blocks WHERE id = ?", (block_id,))
                if cursor.rowcount == 0:
                    raise MissingBlockError(f"Time block {block_id} no longer exists")
        except sqlite3.Error as exc:
            raise StorageError(f"Could not remove time block: {exc}") from exc
