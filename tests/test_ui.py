from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from dmm_calibration.bootstrap import (
    application_root,
    configure_application_font,
    default_config_directory,
    run,
)
from dmm_calibration.config import ConfigRepository, Environment
from dmm_calibration.data import HealthResult
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
