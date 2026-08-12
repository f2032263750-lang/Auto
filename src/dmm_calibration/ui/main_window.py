from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dmm_calibration.config import ConfigValidationError, ConfigWriteError, WorkstationConfig
from dmm_calibration.ui.settings_dialog import SettingsDialog
from dmm_calibration.workflow import ApplicationController


class MainWindow(QMainWindow):
    def __init__(self, controller: ApplicationController):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("台式万用表自动校准软件 V0.1.0")
        self.resize(640, 280)

        self._workstation_value = QLabel()
        self._environment_value = QLabel()
        self._server_value = QLabel("未检查")
        self._server_value.setObjectName("serverStatus")
        self._server_detail = QLabel("尚未执行服务器健康检查")
        self._server_detail.setWordWrap(True)

        status_layout = QVBoxLayout()
        status_layout.addWidget(self._row("工位编号", self._workstation_value))
        status_layout.addWidget(self._row("运行环境", self._environment_value))
        status_layout.addWidget(self._row("服务器状态", self._server_value))
        status_layout.addWidget(self._server_detail)
        status_group = QGroupBox("客户端状态")
        status_group.setLayout(status_layout)

        settings_button = QPushButton("系统设置")
        settings_button.clicked.connect(self._open_settings)
        check_button = QPushButton("重新检查服务器")
        check_button.clicked.connect(self.controller.check_server)
        close_button = QPushButton("退出")
        close_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addWidget(settings_button)
        button_layout.addWidget(check_button)
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(status_group)
        layout.addLayout(button_layout)
        self.setCentralWidget(central)

        self.controller.config_changed.connect(self._apply_config)
        self.controller.health_check_started.connect(self._show_checking)
        self.controller.health_changed.connect(self._apply_health)
        self._apply_config(self.controller.config)

    @staticmethod
    def _row(label: str, value: QLabel) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(f"{label}：")
        title.setMinimumWidth(100)
        layout.addWidget(title)
        layout.addWidget(value, 1)
        return widget

    @Slot(object)
    def _apply_config(self, config: WorkstationConfig) -> None:
        self._workstation_value.setText(config.workstation_id)
        self._environment_value.setText(config.environment.value)

    @Slot()
    def _show_checking(self) -> None:
        self._server_value.setText("检测中")
        self._server_value.setStyleSheet("color: #8a5a00; font-weight: 600;")
        self._server_detail.setText("正在执行非阻塞健康检查…")

    @Slot(object)
    def _apply_health(self, result: object) -> None:
        self._server_value.setText("在线" if result.online else "离线")
        color = "#18794e" if result.online else "#b42318"
        self._server_value.setStyleSheet(f"color: {color}; font-weight: 600;")
        self._server_detail.setText(f"{result.detail}（{result.elapsed_ms} ms）")

    @Slot()
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.controller.config, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        try:
            self.controller.save_config(dialog.result_config)
        except (ConfigValidationError, ConfigWriteError) as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
