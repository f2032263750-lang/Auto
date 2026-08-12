from __future__ import annotations

import ast
from pathlib import Path
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "dmm_calibration"


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_forbidden_layer_imports_are_absent(self) -> None:
        forbidden = {
            "ui": (
                "dmm_calibration.devices",
                "dmm_calibration.communication",
                "dmm_calibration.calculation",
                "dmm_calibration.data",
            ),
            "workflow": ("dmm_calibration.ui",),
            "devices": ("dmm_calibration.ui", "dmm_calibration.workflow"),
            "communication": (
                "dmm_calibration.ui",
                "dmm_calibration.workflow",
                "dmm_calibration.devices",
                "dmm_calibration.calculation",
            ),
            "calculation": ("dmm_calibration.ui",),
        }
        violations: list[str] = []

        for layer, forbidden_prefixes in forbidden.items():
            for path in (SOURCE_ROOT / layer).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    imported: list[str] = []
                    if isinstance(node, ast.Import):
                        imported = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported = [node.module]
                    for name in imported:
                        if any(
                            name == prefix or name.startswith(prefix + ".")
                            for prefix in forbidden_prefixes
                        ):
                            violations.append(
                                f"{path.relative_to(SOURCE_ROOT)} imports {name}"
                            )

        self.assertEqual(violations, [])

    def test_unimplemented_layers_are_placeholders(self) -> None:
        for layer in ("devices", "communication", "calculation", "reports"):
            files = sorted(
                path.name for path in (SOURCE_ROOT / layer).glob("*.py")
            )
            self.assertEqual(files, ["__init__.py"], layer)

    def test_logging_layer_contains_only_m2_components(self) -> None:
        files = sorted(
            path.name for path in (SOURCE_ROOT / "logging").glob("*.py")
        )
        self.assertEqual(files, ["__init__.py", "events.py", "query.py", "service.py"])


if __name__ == "__main__":
    unittest.main()
