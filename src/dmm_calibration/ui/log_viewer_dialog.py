from __future__ import annotations

from datetime import date
import json

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dmm_calibration.logging import LogChannel, LogLevel, LogQueryService


class LogViewerDialog(QDialog):
    def __init__(self, query_service: LogQueryService, parent: QWidget | None = None):
        super().__init__(parent)
        self.query_service = query_service
        self._records: list[dict[str, object]] = []
        self.setWindowTitle("日志查看")
        self.resize(980, 620)

        self._channel = QComboBox()
        self._channel.setObjectName("logChannelFilter")
        self._channel.addItem("业务日志", LogChannel.BUSINESS)
        self._channel.addItem("审计日志", LogChannel.AUDIT)
        self._channel.addItem("通信日志", LogChannel.COMMUNICATION)

        self._date = QDateEdit()
        self._date.setObjectName("logDateFilter")
        self._date.setCalendarPopup(True)
        self._date.setDate(QDate.currentDate())
        self._date.setDisplayFormat("yyyy-MM-dd")

        self._level = QComboBox()
        self._level.setObjectName("logLevelFilter")
        for level in LogLevel:
            self._level.addItem(f"{level.name} 及以上", level)

        self._keyword = QLineEdit()
        self._keyword.setObjectName("logKeywordFilter")
        self._keyword.setPlaceholderText("事件、模块、设备或消息关键字")
        self._keyword.returnPressed.connect(self.refresh)

        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("refreshLogsButton")
        refresh_button.clicked.connect(self.refresh)

        filters = QHBoxLayout()
        form = QFormLayout()
        form.addRow("类型", self._channel)
        form.addRow("日期", self._date)
        form.addRow("级别", self._level)
        filters.addLayout(form)
        keyword_form = QFormLayout()
        keyword_form.addRow("关键字", self._keyword)
        filters.addLayout(keyword_form, 1)
        filters.addWidget(refresh_button, 0, Qt.AlignmentFlag.AlignBottom)

        self._table = QTableWidget(0, 6)
        self._table.setObjectName("logTable")
        self._table.setHorizontalHeaderLabels(
            ("时间", "级别", "事件", "模块", "结果", "消息")
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.currentCellChanged.connect(self._show_record)

        self._details = QPlainTextEdit()
        self._details.setObjectName("logDetails")
        self._details.setReadOnly(True)
        self._details.setMaximumBlockCount(5000)

        self._status = QLabel()
        self._status.setObjectName("logViewerStatus")
        self._status.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self._table, 3)
        layout.addWidget(QLabel("完整记录（只读）"))
        layout.addWidget(self._details, 2)
        layout.addWidget(self._status)
        layout.addWidget(buttons)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        selected_date = self._date.date()
        day = date(selected_date.year(), selected_date.month(), selected_date.day())
        self._records = self.query_service.query(
            LogChannel(self._channel.currentData()),
            day=day,
            minimum_level=LogLevel(self._level.currentData()),
            keyword=self._keyword.text(),
        )
        self._table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            success = record.get("success")
            result = "成功" if success is True else "失败" if success is False else ""
            values = (
                record.get("timestamp", ""),
                record.get("level", ""),
                record.get("event_code", ""),
                record.get("module", ""),
                result,
                record.get("message", ""),
            )
            for column, value in enumerate(values):
                self._table.setItem(row, column, QTableWidgetItem(str(value)))
        if self.query_service.last_error:
            self._status.setText(f"日志读取失败：{self.query_service.last_error}")
        else:
            self._status.setText(f"共显示 {len(self._records)} 条，最多加载 1000 条。")
        if self._records:
            self._table.selectRow(0)
            self._show_record(0, 0, -1, -1)
        else:
            self._details.clear()

    @Slot(int, int, int, int)
    def _show_record(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if not 0 <= current_row < len(self._records):
            self._details.clear()
            return
        self._details.setPlainText(
            json.dumps(self._records[current_row], ensure_ascii=False, indent=2)
        )
