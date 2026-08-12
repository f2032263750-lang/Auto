from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dmm_calibration.config import (
    ConfigValidationError,
    Environment,
    WorkstationConfig,
    validate_config,
)


class SettingsDialog(QDialog):
    def __init__(self, config: WorkstationConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setMinimumWidth(620)
        self._original_config = config
        self._result_config: WorkstationConfig | None = None

        self._environment = QComboBox()
        for environment in Environment:
            self._environment.addItem(environment.value, environment)
        self._environment.setCurrentIndex(
            self._environment.findData(config.environment)
        )
        self._workstation_id = QLineEdit(config.workstation_id)
        self._calibrator_model = QLineEdit(config.calibrator_model)
        self._calibrator_interface = QLineEdit(config.calibrator_interface)
        self._gpib_controller = QLineEdit(config.calibrator_gpib_controller)
        self._gpib_address = QSpinBox()
        self._gpib_address.setRange(0, 30)
        self._gpib_address.setValue(config.calibrator_gpib_address)
        self._uut_terminal = QComboBox()
        self._uut_terminal.addItem("FRONT")
        self._template_path = QLineEdit(config.excel_template_path)
        self._cache_path = QLineEdit(config.cache_directory)
        self._log_path = QLineEdit(config.log_directory)
        self._server_host = QLineEdit(config.server_host)
        self._server_port = QLineEdit(
            "" if config.server_port is None else str(config.server_port)
        )
        self._server_port.setPlaceholderText("未配置")
        self._offline_cache = QCheckBox("允许服务器离线时使用本地缓存")
        self._offline_cache.setChecked(config.offline_cache_enabled)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("配置版本", QLabel(str(config.config_version)))
        form.addRow("运行环境", self._environment)
        form.addRow("工位编号", self._workstation_id)
        form.addRow("标准源型号", self._calibrator_model)
        form.addRow("标准源接口", self._calibrator_interface)
        form.addRow("GPIB 控制器", self._gpib_controller)
        form.addRow("9100 GPIB 地址", self._gpib_address)
        form.addRow("被校表输入端", self._uut_terminal)
        form.addRow("Excel 模板目录", self._path_editor(self._template_path))
        form.addRow("本地缓存目录", self._path_editor(self._cache_path))
        form.addRow("本地日志目录", self._path_editor(self._log_path))
        form.addRow("服务器地址", self._server_host)
        form.addRow("服务器端口", self._server_port)
        form.addRow("离线缓存", self._offline_cache)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def result_config(self) -> WorkstationConfig:
        if self._result_config is None:
            raise RuntimeError("设置窗口尚未产生有效配置")
        return self._result_config

    def _path_editor(self, line_edit: QLineEdit) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton("浏览…")
        browse.clicked.connect(lambda: self._browse_directory(line_edit))
        layout.addWidget(line_edit, 1)
        layout.addWidget(browse)
        return widget

    def _browse_directory(self, target: QLineEdit) -> None:
        initial = target.text().strip()
        if not initial or not Path(initial).exists():
            initial = str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "选择目录", initial)
        if selected:
            target.setText(selected)

    def _validate_and_accept(self) -> None:
        errors: list[str] = []
        port_text = self._server_port.text().strip()
        server_port: int | None = None
        if port_text:
            try:
                server_port = int(port_text)
            except ValueError:
                errors.append("服务器端口必须是整数")

        config = WorkstationConfig(
            config_version=1,
            environment=self._environment.currentData(),
            workstation_id=self._workstation_id.text().strip(),
            calibrator_model=self._calibrator_model.text().strip(),
            calibrator_interface=self._calibrator_interface.text().strip(),
            calibrator_gpib_controller=self._gpib_controller.text().strip(),
            calibrator_gpib_address=self._gpib_address.value(),
            uut_terminal=self._uut_terminal.currentText(),
            default_temperature=self._original_config.default_temperature,
            default_humidity=self._original_config.default_humidity,
            excel_template_path=self._template_path.text().strip(),
            cache_directory=self._cache_path.text().strip(),
            log_directory=self._log_path.text().strip(),
            server_host=self._server_host.text().strip(),
            server_port=server_port,
            offline_cache_enabled=self._offline_cache.isChecked(),
        )
        try:
            validate_config(config)
        except ConfigValidationError as exc:
            errors.extend(exc.errors)
        if errors:
            QMessageBox.warning(self, "配置无效", "\n".join(dict.fromkeys(errors)))
            return
        self._result_config = config
        self.accept()
