from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
)

from dmm_calibration.bootstrap import (
    application_root,
    configure_application_font,
    default_config_directory,
    run,
)
from dmm_calibration.config import ConfigRepository, Environment
from dmm_calibration.data import HealthResult
from dmm_calibration.logging import LogQueryService, StructuredLogService
from dmm_calibration.ui.log_viewer_dialog import LogViewerDialog
from dmm_calibration.ui.main_window import MainWindow
from dmm_calibration.ui.settings_dialog import SettingsDialog
from dmm_calibration.workflow import ApplicationController


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.base = Path(self.temporary_directory.name)
        self.repository = ConfigRepository(
            self.base / "config" / "workstation.json", self.base
        )
        self.config = self.repository.load_or_create().config

    def test_default_paths_derive_from_application_location(self) -> None:
        self.assertEqual(application_root(), Path(__file__).resolve().parents[1])
        self.assertEqual(
            default_config_directory(), application_root().parent / "data" / "config"
        )

    def test_application_font_supports_chinese_on_windows(self) -> None:
        selected = configure_application_font(self.app)

        self.assertTrue(selected)
        if os.environ.get("WINDIR"):
            self.assertIn(
                selected,
                ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun"),
            )

    def test_bootstrap_recovers_corrupt_config_without_crashing(self) -> None:
        config_directory = self.base / "bootstrap-config"
        config_directory.mkdir()
        (config_directory / "workstation.json").write_text(
            "{broken-json", encoding="utf-8"
        )
        QTimer.singleShot(0, self.app.quit)
        original_excepthook = sys.excepthook

        with patch(
            "dmm_calibration.bootstrap.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("dmm_calibration.bootstrap.QMessageBox.information"):
            exit_code = run(config_directory)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            ConfigRepository(
                config_directory / "workstation.json", config_directory.parent
            ).load().config_version,
            1,
        )
        self.assertEqual(
            len(list(config_directory.glob("workstation.broken.*.json"))), 1
        )
        log_files = list((self.base / "data" / "logs").glob("business-*.jsonl"))
        self.assertEqual(len(log_files), 1)
        event_codes = [
            json.loads(line)["event_code"]
            for line in log_files[0].read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("APP_STARTED", event_codes)
        self.assertIn("APP_STOPPED", event_codes)
        audit_files = list((self.base / "data" / "logs").glob("audit-*.jsonl"))
        self.assertEqual(len(audit_files), 1)
        audit_records = [
            json.loads(line)
            for line in audit_files[0].read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(audit_records[0]["event_code"], "CONFIG_RECOVERED")
        self.assertEqual(sys.excepthook, original_excepthook)

    def test_main_window_can_start_offline_and_close(self) -> None:
        controller = ApplicationController(self.repository, self.config)
        window = MainWindow(controller)
        self.addCleanup(window.close)

        window.show()
        controller.check_server()
        self.app.processEvents()

        status = window.findChild(QLabel, "serverStatus")
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status.text(), "离线")
        self.assertTrue(window.isVisible())

    def test_bootstrap_restores_exception_hook_if_window_creation_fails(self) -> None:
        config_directory = self.base / "failed-bootstrap-config"
        original_excepthook = sys.excepthook

        with patch(
            "dmm_calibration.bootstrap.MainWindow",
            side_effect=RuntimeError("window failed"),
        ), self.assertRaisesRegex(RuntimeError, "window failed"):
            run(config_directory)

        self.assertEqual(sys.excepthook, original_excepthook)
        log_files = list((self.base / "data" / "logs").glob("business-*.jsonl"))
        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([record["event_code"] for record in records], ["APP_STARTED"])

    def test_config_change_updates_window_and_persists(self) -> None:
        controller = ApplicationController(self.repository, self.config)
        window = MainWindow(controller)
        self.addCleanup(window.close)
        changed = replace(
            self.config,
            environment=Environment.PRODUCTION,
            workstation_id="CAL-09",
        )

        controller.save_config(changed)
        self.app.processEvents()

        labels = [label.text() for label in window.findChildren(QLabel)]
        self.assertIn("CAL-09", labels)
        self.assertIn("production", labels)
        self.assertEqual(self.repository.load(), changed)

    def test_settings_dialog_accepts_current_valid_config(self) -> None:
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertNotIn("默认温度（℃）", labels)
        self.assertNotIn("默认湿度（%RH）", labels)

        dialog._validate_and_accept()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.result_config, self.config)

    def test_log_viewer_is_read_only_and_filters_records(self) -> None:
        log_service = StructuredLogService(Path(self.config.log_directory))
        log_service.business("APP_STARTED", "客户端启动")
        log_service.business("SERVER_OFFLINE", "服务器不可达")
        dialog = LogViewerDialog(LogQueryService(log_service))
        self.addCleanup(dialog.close)

        table = dialog.findChild(QTableWidget, "logTable")
        keyword = dialog.findChild(QLineEdit, "logKeywordFilter")
        self.assertIsNotNone(table)
        self.assertIsNotNone(keyword)
        assert table is not None and keyword is not None
        self.assertEqual(
            table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.assertEqual(table.rowCount(), 2)

        keyword.setText("不可达")
        dialog.refresh()

        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.item(0, 2).text(), "SERVER_OFFLINE")

    def test_main_window_enables_log_viewer_when_service_is_configured(self) -> None:
        log_service = StructuredLogService(Path(self.config.log_directory))
        controller = ApplicationController(
            self.repository,
            self.config,
            log_service=log_service,
        )
        window = MainWindow(controller)
        self.addCleanup(window.close)

        button = window.findChild(QPushButton, "openLogViewerButton")

        self.assertIsNotNone(button)
        assert button is not None
        self.assertFalse(button.isHidden())

    def test_production_hides_log_viewer_until_role_authorization_exists(self) -> None:
        production = replace(self.config, environment=Environment.PRODUCTION)
        log_service = StructuredLogService(Path(production.log_directory))
        controller = ApplicationController(
            self.repository,
            production,
            log_service=log_service,
        )
        window = MainWindow(controller)
        self.addCleanup(window.close)

        button = window.findChild(QPushButton, "openLogViewerButton")

        self.assertIsNotNone(button)
        assert button is not None
        self.assertTrue(button.isHidden())

    def test_switching_to_production_hides_log_viewer_immediately(self) -> None:
        log_service = StructuredLogService(Path(self.config.log_directory))
        controller = ApplicationController(
            self.repository,
            self.config,
            log_service=log_service,
        )
        window = MainWindow(controller)
        self.addCleanup(window.close)
        button = window.findChild(QPushButton, "openLogViewerButton")
        assert button is not None

        controller.save_config(
            replace(self.config, environment=Environment.PRODUCTION)
        )
        self.app.processEvents()

        self.assertTrue(button.isHidden())

    def test_health_check_does_not_block_caller(self) -> None:
        class SlowHealthClient:
            def check(self, config: object) -> HealthResult:
                sleep(0.2)
                return HealthResult(
                    online=True,
                    detail="服务器在线",
                    checked_at=datetime.now(timezone.utc),
                    elapsed_ms=200,
                    status_code=200,
                )

        pool = QThreadPool()
        configured = replace(
            self.config, server_host="127.0.0.1", server_port=8080
        )
        controller = ApplicationController(
            self.repository,
            configured,
            health_client=SlowHealthClient(),
            thread_pool=pool,
        )
        received: list[HealthResult] = []
        controller.health_changed.connect(received.append)

        started = perf_counter()
        controller.check_server()
        elapsed = perf_counter() - started

        self.assertLess(elapsed, 0.1)
        self.assertTrue(pool.waitForDone(1000))
        self.app.processEvents()
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].online)


if __name__ == "__main__":
    unittest.main()
