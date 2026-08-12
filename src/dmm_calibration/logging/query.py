from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from dmm_calibration.logging.events import LogChannel, LogLevel
from dmm_calibration.logging.service import StructuredLogService


class LogQueryService:
    def __init__(self, source: StructuredLogService | Path):
        self._source = source
        self.last_error: str | None = None

    @property
    def log_directory(self) -> Path:
        if isinstance(self._source, StructuredLogService):
            return self._source.log_directory
        return Path(self._source)

    def query(
        self,
        channel: LogChannel,
        *,
        day: date | None = None,
        minimum_level: LogLevel = LogLevel.DEBUG,
        keyword: str = "",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        self.last_error = None
        try:
            paths = self._paths(channel, day)
            records: list[dict[str, Any]] = []
            normalized_keyword = keyword.strip().casefold()
            for path in paths:
                lines = path.read_text(encoding="utf-8").splitlines()
                for line in reversed(lines):
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(record, dict):
                        continue
                    if record.get("channel") != channel.value:
                        continue
                    try:
                        level = LogLevel.from_name(str(record.get("level", "")))
                    except KeyError:
                        continue
                    if level < minimum_level:
                        continue
                    if normalized_keyword and normalized_keyword not in line.casefold():
                        continue
                    records.append(record)
                    if len(records) >= limit:
                        return records
            return records
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []

    def _paths(self, channel: LogChannel, day: date | None) -> list[Path]:
        directory = self.log_directory
        if day is not None:
            candidate = directory / f"{channel.value}-{day.isoformat()}.jsonl"
            return [candidate] if candidate.is_file() else []
        return sorted(
            directory.glob(f"{channel.value}-????-??-??.jsonl"), reverse=True
        )
