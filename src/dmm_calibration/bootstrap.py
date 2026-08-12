from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from dmm_calibration.config import ConfigFileError, ConfigRepository, ConfigWriteError
from dmm_calibration.ui.main_window import MainWindow
from dmm_calibration.workflow import ApplicationController


def application_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_directory() -> Path:
    override = os.environ.get("DMM_CALIBRATION_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return application_root().parent / "data" / "config"


def configure_application_font(app: QApplication) -> str:
    preferred_families = (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
    )
    available = set(QFontDatabase.families())
    for family in preferred_families:
        if family in available:
            app.setFont(QFont(family, 10))
            return family

    windows_directory = os.environ.get("WINDIR")
    if windows_directory:
        font_directory = Path(windows_directory) / "Fonts"
        for filename in ("msyh.ttc", "simhei.ttf", "simsun.ttc"):
            font_path = font_directory / filename
            if not font_path.is_file():
                continue
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0], 10))
                return families[0]
    return app.font().family()


def run(config_directory: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    configure_application_font(app)
    selected_config_directory = (config_directory or default_config_directory()).resolve()
    base_directory = (
        application_root().parent
        if config_directory is None
        else selected_config_directory.parent
    )
    repository = ConfigRepository(
        selected_config_directory / "workstation.json", base_directory
    )

    try:
        load_result = repository.load_or_create()
        config = load_result.config
    except ConfigFileError as exc:
        answer = QMessageBox.question(
            None,
            "配置文件损坏",
            f"{exc}\n\n是否备份损坏文件并恢复默认配置？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            QMessageBox.information(None, "启动已取消", "配置未被修改，客户端将退出。")
            return 2
        try:
            config, backup_path = repository.recover_default()
        except ConfigWriteError as write_error:
            QMessageBox.critical(None, "配置恢复失败", str(write_error))
            return 3
        backup_message = f"\n损坏文件备份：{backup_path}" if backup_path else ""
        QMessageBox.information(
            None, "配置已恢复", f"已恢复默认配置。{backup_message}"
        )
    except ConfigWriteError as exc:
        QMessageBox.critical(None, "客户端启动失败", str(exc))
        return 3

    controller = ApplicationController(repository, config)
    window = MainWindow(controller)
    window.show()
    controller.check_server()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="台式万用表自动校准软件客户端")
    parser.add_argument(
        "--config-dir",
        type=Path,
        help="覆盖默认工位配置目录",
    )
    args = parser.parse_args(argv)
    return run(args.config_dir)
