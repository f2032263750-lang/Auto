from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dmm_calibration.config import (
    ConfigFileError,
    ConfigRepository,
    ConfigValidationError,
    ConfigWriteError,
    Environment,
)


class ConfigRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.base = Path(self.temporary_directory.name)
        self.config_path = self.base / "data" / "config" / "workstation.json"
        self.repository = ConfigRepository(self.config_path, self.base)

    def test_first_load_creates_default_config_and_runtime_directories(self) -> None:
        result = self.repository.load_or_create()

        self.assertTrue(result.created)
        self.assertEqual(result.config.config_version, 1)
        self.assertEqual(result.config.environment, Environment.DEVELOPMENT)
        self.assertEqual(result.config.workstation_id, "CAL-01")
        self.assertTrue(self.config_path.exists())
        self.assertTrue((self.base / "templates").is_dir())
        self.assertTrue((self.base / "data" / "cache").is_dir())
        self.assertTrue((self.base / "data" / "logs").is_dir())

        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["default_temperature"], "23")
        self.assertEqual(raw["default_humidity"], "50")

    def test_saved_config_is_loaded_after_restart(self) -> None:
        original = self.repository.load_or_create().config
        changed = replace(
            original,
            environment=Environment.TEST,
            workstation_id="CAL-02",
            server_host="127.0.0.1",
            server_port=8080,
        )

        self.repository.save(changed)
        reloaded = ConfigRepository(self.config_path, self.base).load_or_create()

        self.assertFalse(reloaded.created)
        self.assertEqual(reloaded.config, changed)

    def test_invalid_config_is_rejected_without_overwriting_file(self) -> None:
        original = self.repository.load_or_create().config
        before = self.config_path.read_bytes()
        invalid = replace(original, calibrator_gpib_address=31)

        with self.assertRaises(ConfigValidationError):
            self.repository.save(invalid)

        self.assertEqual(self.config_path.read_bytes(), before)

    def test_server_host_and_port_must_be_configured_together(self) -> None:
        original = self.repository.load_or_create().config

        with self.assertRaisesRegex(
            ConfigValidationError, "server_host 和 server_port"
        ):
            self.repository.save(replace(original, server_host="127.0.0.1"))

    def test_corrupt_config_is_backed_up_before_default_recovery(self) -> None:
        self.config_path.parent.mkdir(parents=True)
        corrupt_content = "{not-json"
        self.config_path.write_text(corrupt_content, encoding="utf-8")

        with self.assertRaises(ConfigFileError):
            self.repository.load_or_create()

        recovered, backup_path = self.repository.recover_default()

        self.assertEqual(recovered.workstation_id, "CAL-01")
        self.assertIsNotNone(backup_path)
        assert backup_path is not None
        self.assertEqual(backup_path.read_text(encoding="utf-8"), corrupt_content)
        self.assertEqual(self.repository.load(), recovered)

    def test_atomic_replace_failure_preserves_previous_config(self) -> None:
        original = self.repository.load_or_create().config
        before = self.config_path.read_bytes()

        with patch(
            "dmm_calibration.config.repository.os.replace",
            side_effect=OSError("injected replace failure"),
        ):
            with self.assertRaises(ConfigWriteError):
                self.repository.save(replace(original, workstation_id="CAL-03"))

        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(list(self.config_path.parent.glob("*.tmp")), [])

    def test_missing_and_unknown_fields_are_rejected(self) -> None:
        config = self.repository.load_or_create().config
        raw = config.to_mapping()
        raw.pop("workstation_id")
        raw["unexpected"] = "value"
        self.config_path.write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8"
        )

        with self.assertRaisesRegex(ConfigFileError, "缺少字段"):
            self.repository.load()


if __name__ == "__main__":
    unittest.main()
