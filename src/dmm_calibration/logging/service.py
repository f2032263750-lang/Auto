from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
import json
from pathlib import Path
import re
from threading import RLock
import traceback
from typing import Any

from dmm_calibration.logging.events import LogChannel, LogEvent, LogLevel


_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "authorization",
    "credential",
    "api_key",
    "apikey",
)
_INLINE_SECRET = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)"
    r"\s*([:=])\s*([^\s,;]+)"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\b(authorization)\s*([:=])\s*(?:bearer\s+)?([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")


def minimum_level_for_environment(environment: object) -> LogLevel:
    value = getattr(environment, "value", environment)
    return LogLevel.INFO if str(value) == "production" else LogLevel.DEBUG


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_text(value: str) -> str:
    redacted = _AUTHORIZATION_VALUE.sub(r"\1\2[REDACTED]", value)
    redacted = _INLINE_SECRET.sub(r"\1\2[REDACTED]", redacted)
    return _BEARER_TOKEN.sub("Bearer [REDACTED]", redacted)


def redact(value: Any, *, key: object | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): redact(item, key=item_key) for item_key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, Path)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


class StructuredLogService:
    def __init__(
        self,
        log_directory: Path,
        *,
        minimum_level: LogLevel = LogLevel.DEBUG,
        retention_days: int = 365,
        clock: Callable[[], datetime] | None = None,
    ):
        if retention_days < 1:
            raise ValueError("retention_days 必须大于等于 1")
        self._log_directory = Path(log_directory)
        self.minimum_level = minimum_level
        self.retention_days = retention_days
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._lock = RLock()
        self._pruned: set[tuple[Path, LogChannel, date]] = set()
        self.last_error: str | None = None
        self._ensure_directory()

    @property
    def log_directory(self) -> Path:
        with self._lock:
            return self._log_directory

    def reconfigure(self, log_directory: Path) -> bool:
        with self._lock:
            self._log_directory = Path(log_directory)
            self._pruned.clear()
            return self._ensure_directory()

    def business(self, event_code: str, message: str, **fields: Any) -> bool:
        return self.emit(LogChannel.BUSINESS, event_code, message, **fields)

    def audit(self, event_code: str, message: str, **fields: Any) -> bool:
        return self.emit(LogChannel.AUDIT, event_code, message, **fields)

    def communication(self, event_code: str, message: str, **fields: Any) -> bool:
        return self.emit(LogChannel.COMMUNICATION, event_code, message, **fields)

    def exception(
        self,
        channel: LogChannel,
        event_code: str,
        message: str,
        error: BaseException,
        **fields: Any,
    ) -> bool:
        return self.emit(
            channel,
            event_code,
            message,
            level=LogLevel.ERROR,
            error_type=type(error).__name__,
            error_message=str(error),
            traceback_text="".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
            **fields,
        )

    def emit(
        self,
        channel: LogChannel,
        event_code: str,
        message: str,
        *,
        level: LogLevel = LogLevel.INFO,
        module: str = "application",
        workstation_id: str | None = None,
        user_id: str | None = None,
        task_id: str | None = None,
        device: str | None = None,
        interface: str | None = None,
        operation: str | None = None,
        duration_ms: int | None = None,
        success: bool | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        traceback_text: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        if level < self.minimum_level:
            return False
        try:
            timestamp = self._clock()
            if timestamp.tzinfo is None:
                timestamp = timestamp.astimezone()
            event = LogEvent(
                channel=channel,
                level=level,
                timestamp=timestamp,
                event_code=event_code.strip().upper(),
                module=module.strip(),
                message=message,
                workstation_id=workstation_id,
                user_id=user_id,
                task_id=task_id,
                device=device,
                interface=interface,
                operation=operation,
                duration_ms=duration_ms,
                success=success,
                error_type=error_type,
                error_message=error_message,
                traceback_text=traceback_text,
                details=details or {},
            )
            record = redact(event.to_record())
            line = json.dumps(
                record,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            with self._lock:
                self._append_line(channel, timestamp.date(), line)
                self._prune_once(channel, timestamp.date())
                self.last_error = None
            return True
        except Exception as exc:
            with self._lock:
                self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def _ensure_directory(self) -> bool:
        try:
            self._log_directory.mkdir(parents=True, exist_ok=True)
            self.last_error = None
            return True
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def _append_line(self, channel: LogChannel, day: date, line: str) -> None:
        self._log_directory.mkdir(parents=True, exist_ok=True)
        path = self._log_directory / f"{channel.value}-{day.isoformat()}.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.write("\n")
            stream.flush()

    def _prune_once(self, channel: LogChannel, today: date) -> None:
        marker = (self._log_directory, channel, today)
        if marker in self._pruned:
            return
        oldest_kept = today - timedelta(days=self.retention_days - 1)
        pattern = re.compile(
            rf"^{re.escape(channel.value)}-(\d{{4}}-\d{{2}}-\d{{2}})\.jsonl$"
        )
        for path in self._log_directory.glob(f"{channel.value}-*.jsonl"):
            match = pattern.fullmatch(path.name)
            if match is None:
                continue
            try:
                file_day = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if file_day < oldest_kept:
                try:
                    path.unlink()
                except OSError:
                    continue
        self._pruned.add(marker)
