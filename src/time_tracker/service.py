"""Application operations for time blocks, independent of Qt and SQLite details."""

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from time_tracker.domain import TimeBlock, parse_time, validate_interval
from time_tracker.storage import (
    MissingBlockError, OverlapError, StorageError, TimeBlockRepository,
)


class ValidationError(ValueError):
    """User input cannot be saved; ``field`` identifies the relevant editor input."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class ServiceStorageError(Exception):
    """A database operation failed independently of editor field validation."""


class TimeTrackerService:
    """Own a repository and expose operations for the dashboard and editor.

    ``clock`` returns local wall time. Supplying a database path and clock keeps
    application behavior deterministic in tests without changing global state.
    """

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._clock = clock
        try:
            self._repository = TimeBlockRepository(database_path)
        except StorageError as exc:
            raise ServiceStorageError(str(exc)) from exc

    def __enter__(self) -> "TimeTrackerService":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._repository.close()

    def current_time(self) -> datetime:
        """Read the injected local clock once for startup and Today actions."""

        return self._clock()

    def list_week(self, day: date | None = None) -> list[TimeBlock]:
        """List the Sunday-first week containing ``day`` or the current date."""

        if day is None:
            day = self.current_time().date()
        if type(day) is not date:
            raise ValidationError("Week lookup requires a calendar date", field="date")
        try:
            return self._repository.list_week(day)
        except StorageError as exc:
            raise ServiceStorageError(str(exc)) from exc

    def save_block(
        self,
        day: date,
        start_text: str,
        end_text: str,
        description: str = "",
        *,
        block_id: int | None = None,
    ) -> TimeBlock:
        """Validate current editor fields, then create or update one block."""

        if type(day) is not date:
            raise ValidationError("Block date must be a calendar date", field="date")
        try:
            start = parse_time(start_text)
        except ValueError as exc:
            raise ValidationError(f"Start time: {exc}", field="start_time") from exc
        try:
            end = parse_time(end_text)
        except ValueError as exc:
            raise ValidationError(f"End time: {exc}", field="end_time") from exc
        try:
            validate_interval(start, end)
        except ValueError as exc:
            raise ValidationError(str(exc), field="end_time") from exc
        if not isinstance(description, str):
            raise ValidationError("Description must be text", field="description")
        if block_id is not None and (type(block_id) is not int or block_id <= 0):
            raise ValidationError("Block ID must be a positive integer", field="block_id")

        try:
            return self._repository.save(
                day, start, end, description, block_id=block_id
            )
        except OverlapError as exc:
            raise ValidationError(str(exc), field="start_time") from exc
        except MissingBlockError as exc:
            raise ValidationError(str(exc), field="block_id") from exc
        except StorageError as exc:
            raise ServiceStorageError(str(exc)) from exc

    def remove_block(self, block_id: int) -> None:
        """Remove a persisted block, reporting a stale ID to the editor."""

        if type(block_id) is not int or block_id <= 0:
            raise ValidationError("Block ID must be a positive integer", field="block_id")
        try:
            self._repository.delete(block_id)
        except MissingBlockError as exc:
            raise ValidationError(str(exc), field="block_id") from exc
        except StorageError as exc:
            raise ServiceStorageError(str(exc)) from exc
