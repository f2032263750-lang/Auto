from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from dmm_calibration.logging import (
    LOG_SCHEMA_VERSION,
    LogChannel,
    LogLevel,
    LogQueryService,
    StructuredLogService,
)
from dmm_calibration.config import ConfigRepository, ConfigValidationError, Environment
from dmm_calibration.workflow import ApplicationController


FIXED_NOW = datetime(2026, 8, 12, 9, 30, 15, 123000, timezone(timedelta(hours=8)))


class StructuredLogServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.log_directory = Path(self.temporary_directory.name)
        self.service = StructuredLogService(
            self.log_directory,
            clock=lambda: FIXED_NOW,
        )

    def _records(self, channel: LogChannel) -> list[dict[str, object]]:
        path = self.log_directory / f"{channel.value}-2026-08-12.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_three_channels_are_separate_valid_json_lines(self) -> None:
        self.assertTrue(
            self.service.business(
                "app_started",
                "客户端启动",
                module="bootstrap",
                workstation_id="CAL-01",
                success=True,
                details={"temperature": Decimal("23")},
            )
        )
        self.assertTrue(
            self.service.audit(
                "config_saved",
                "工位配置已保存",
                module="config",
            )
        )
        self.assertTrue(
            self.service.communication(
                "scpi_query",
                "查询设备状态",
                module="communication",
                device="Fluke 9100",
                interface="GPIB0::10",
                operation="OUTP?",
                duration_ms=52,
                success=True,
                details={"response": "OFF"},
            )
        )

        for channel in LogChannel:
            records = self._records(channel)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["schema_version"], LOG_SCHEMA_VERSION)
            self.assertEqual(records[0]["channel"], channel.value)
            self.assertEqual(records[0]["timestamp"], "2026-08-12T09:30:15.123+08:00")

    def test_sensitive_values_are_redacted_recursively_and_in_text(self) -> None:
        self.service.audit(
            "login",
            "password=plain Authorization: Bearer abc.def token:xyz",
            details={
                "password": "plain",
                "profile": {"access_token": "abc", "name": "operator"},
            },
        )

        serialized = json.dumps(self._records(LogChannel.AUDIT)[0], ensure_ascii=False)
        self.assertNotIn("plain", serialized)
        self.assertNotIn("abc.def", serialized)
        self.assertNotIn('"abc"', serialized)
        self.assertNotIn("xyz", serialized)
        self.assertIn("[REDACTED]", serialized)
        self.assertIn("operator", serialized)

    def test_minimum_level_filters_debug_events(self) -> None:
        service = StructuredLogService(
            self.log_directory,
            minimum_level=LogLevel.INFO,
            clock=lambda: FIXED_NOW,
        )

        self.assertFalse(
            service.business("debug_probe", "debug", level=LogLevel.DEBUG)
        )
        self.assertTrue(service.business("info_probe", "info"))
        records = self._records(LogChannel.BUSINESS)
        self.assertEqual([record["event_code"] for record in records], ["INFO_PROBE"])

    def test_write_failure_never_raises_to_caller(self) -> None:
        with patch.object(self.service, "_append_line", side_effect=OSError("disk full")):
            result = self.service.business("write_failed", "模拟写入失败")

        self.assertFalse(result)
        self.assertIn("disk full", self.service.last_error or "")

    def test_exception_includes_traceback(self) -> None:
        try:
            raise ValueError("bad value")
        except ValueError as exc:
            self.service.exception(
                LogChannel.BUSINESS,
                "unhandled_exception",
                "未捕获异常",
                exc,
            )

        record = self._records(LogChannel.BUSINESS)[0]
        self.assertEqual(record["level"], "ERROR")
        self.assertEqual(record["error_type"], "ValueError")
        self.assertIn("bad value", str(record["traceback"]))

    def test_daily_retention_removes_only_expired_matching_files(self) -> None:
        expired = self.log_directory / "business-2026-08-09.jsonl"
        retained = self.log_directory / "business-2026-08-10.jsonl"
        unrelated = self.log_directory / "manual-notes.jsonl"
        for path in (expired, retained, unrelated):
            path.write_text("{}\n", encoding="utf-8")
        service = StructuredLogService(
            self.log_directory,
            retention_days=3,
            clock=lambda: FIXED_NOW,
        )

        service.business("rotation_probe", "轮转测试")

        self.assertFalse(expired.exists())
        self.assertTrue(retained.exists())
        self.assertTrue(unrelated.exists())

    def test_concurrent_writes_keep_each_line_complete(self) -> None:
        def write_batch(worker: int) -> None:
            for sequence in range(20):
                self.service.business(
                    "concurrent_write",
                    "并发写入",
                    details={"worker": worker, "sequence": sequence},
                )

        threads = [Thread(target=write_batch, args=(worker,)) for worker in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        records = self._records(LogChannel.BUSINESS)
        self.assertEqual(len(records), 160)
        self.assertTrue(all(record["event_code"] == "CONCURRENT_WRITE" for record in records))


class LogQueryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.log_directory = Path(self.temporary_directory.name)
        self.service = StructuredLogService(
            self.log_directory,
            clock=lambda: FIXED_NOW,
        )
        self.query = LogQueryService(self.service)

    def test_query_filters_day_level_and_keyword_and_skips_bad_lines(self) -> None:
        self.service.business(
            "first",
            "启动成功",
            level=LogLevel.INFO,
            workstation_id="CAL-01",
        )
        self.service.business(
            "second",
            "服务器不可达",
            level=LogLevel.WARNING,
            workstation_id="CAL-01",
        )
        path = self.log_directory / "business-2026-08-12.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write("not-json\n")

        records = self.query.query(
            LogChannel.BUSINESS,
            day=date(2026, 8, 12),
            minimum_level=LogLevel.WARNING,
            keyword="不可达",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_code"], "SECOND")

    def test_query_follows_reconfigured_log_directory(self) -> None:
        changed = self.log_directory / "changed"
        self.service.reconfigure(changed)
        self.service.audit("config_changed", "配置路径已变更")

        records = self.query.query(LogChannel.AUDIT, day=date(2026, 8, 12))

        self.assertEqual(len(records), 1)
        self.assertEqual(self.query.log_directory, changed)


class ApplicationLoggingIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.base = Path(self.temporary_directory.name)
        self.repository = ConfigRepository(
            self.base / "config" / "workstation.json", self.base
        )
        self.config = self.repository.load_or_create().config
        self.service = StructuredLogService(
            Path(self.config.log_directory),
            clock=lambda: FIXED_NOW,
        )
        self.controller = ApplicationController(
            self.repository,
            self.config,
            log_service=self.service,
        )

    def _records(self, directory: Path, channel: LogChannel) -> list[dict[str, object]]:
        path = directory / f"{channel.value}-2026-08-12.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_health_check_records_started_and_completed_events(self) -> None:
        self.controller.check_server()

        records = self._records(Path(self.config.log_directory), LogChannel.BUSINESS)

        self.assertEqual(
            [record["event_code"] for record in records],
            ["SERVER_HEALTH_CHECK_STARTED", "SERVER_HEALTH_CHECK_COMPLETED"],
        )
        self.assertFalse(records[-1]["success"])
        self.assertEqual(records[-1]["details"]["detail"], "服务器未配置")

    def test_config_save_reconfigures_logging_and_records_changed_fields(self) -> None:
        changed_log_directory = self.base / "changed-logs"
        changed = replace(
            self.config,
            environment=Environment.PRODUCTION,
            workstation_id="CAL-09",
            log_directory=str(changed_log_directory),
        )

        self.controller.save_config(changed)

        records = self._records(changed_log_directory, LogChannel.AUDIT)
        self.assertEqual(records[0]["event_code"], "CONFIG_UPDATED")
        self.assertEqual(
            records[0]["details"]["changed_fields"],
            ["environment", "log_directory", "workstation_id"],
        )
        self.assertEqual(self.service.log_directory, changed_log_directory)
        self.assertEqual(self.service.minimum_level, LogLevel.INFO)

    def test_invalid_config_is_logged_and_still_rejected(self) -> None:
        invalid = replace(self.config, workstation_id="invalid id")

        with self.assertRaises(ConfigValidationError):
            self.controller.save_config(invalid)

        records = self._records(Path(self.config.log_directory), LogChannel.AUDIT)
        self.assertEqual(records[0]["event_code"], "CONFIG_UPDATE_FAILED")
        self.assertEqual(records[0]["level"], "ERROR")
        self.assertFalse(records[0]["success"])


if __name__ == "__main__":
    unittest.main()
