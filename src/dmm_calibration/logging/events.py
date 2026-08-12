from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Mapping


LOG_SCHEMA_VERSION = 1


class LogChannel(StrEnum):
    BUSINESS = "business"
    AUDIT = "audit"
    COMMUNICATION = "communication"


class LogLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    @classmethod
    def from_name(cls, value: str) -> LogLevel:
        return cls[value.strip().upper()]


@dataclass(frozen=True, slots=True)
class LogEvent:
    channel: LogChannel
    level: LogLevel
    timestamp: datetime
    event_code: str
    module: str
    message: str
    workstation_id: str | None = None
    user_id: str | None = None
    task_id: str | None = None
    device: str | None = None
    interface: str | None = None
    operation: str | None = None
    duration_ms: int | None = None
    success: bool | None = None
    error_type: str | None = None
    error_message: str | None = None
    traceback_text: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema_version": LOG_SCHEMA_VERSION,
            "timestamp": self.timestamp.isoformat(timespec="milliseconds"),
            "channel": self.channel.value,
            "level": self.level.name,
            "event_code": self.event_code,
            "module": self.module,
            "message": self.message,
        }
        optional_fields = {
            "workstation_id": self.workstation_id,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "device": self.device,
            "interface": self.interface,
            "operation": self.operation,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback_text,
        }
        record.update(
            (name, value) for name, value in optional_fields.items() if value is not None
        )
        if self.details:
            record["details"] = dict(self.details)
        return record
