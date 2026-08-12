from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from dmm_calibration.config import (
    ConfigRepository,
    ConfigValidationError,
    ConfigWriteError,
    WorkstationConfig,
)
from dmm_calibration.data import HealthResult, ServerHealthClient
from dmm_calibration.logging import (
    LogChannel,
    StructuredLogService,
    minimum_level_for_environment,
)


class _WorkerSignals(QObject):
    completed = Signal(int, object)


class _HealthWorker(QRunnable):
    def __init__(
        self,
        generation: int,
        client: ServerHealthClient,
        config: WorkstationConfig,
    ):
        super().__init__()
        self.generation = generation
        self.client = client
        self.config = config
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        self.signals.completed.emit(
            self.generation, self.client.check(self.config)
        )


class ApplicationController(QObject):
    config_changed = Signal(object)
    health_check_started = Signal()
    health_changed = Signal(object)

    def __init__(
        self,
        repository: ConfigRepository,
        config: WorkstationConfig,
        health_client: ServerHealthClient | None = None,
        thread_pool: QThreadPool | None = None,
        log_service: StructuredLogService | None = None,
    ):
        super().__init__()
        self.repository = repository
        self.config = config
        self.health_client = health_client or ServerHealthClient()
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self.log_service = log_service
        self._generation = 0
        self._workers: set[_HealthWorker] = set()

    def save_config(self, config: WorkstationConfig) -> None:
        previous = self.config
        try:
            self.repository.save(config)
        except (ConfigValidationError, ConfigWriteError) as exc:
            if self.log_service is not None:
                self.log_service.exception(
                    channel=LogChannel.AUDIT,
                    event_code="CONFIG_UPDATE_FAILED",
                    message="工位配置保存失败",
                    error=exc,
                    module="config",
                    workstation_id=previous.workstation_id,
                    success=False,
                )
            raise
        self.config = config
        if self.log_service is not None:
            self.log_service.minimum_level = minimum_level_for_environment(
                config.environment
            )
            self.log_service.reconfigure(Path(config.log_directory))
            previous_values = previous.to_mapping()
            current_values = config.to_mapping()
            changed_fields = sorted(
                name
                for name, value in current_values.items()
                if value != previous_values[name]
            )
            self.log_service.audit(
                "CONFIG_UPDATED",
                "工位配置已保存",
                module="config",
                workstation_id=config.workstation_id,
                success=True,
                details={"changed_fields": changed_fields},
            )
        self.config_changed.emit(config)
        self.check_server()

    def check_server(self) -> None:
        self._generation += 1
        generation = self._generation
        if self.log_service is not None:
            self.log_service.business(
                "SERVER_HEALTH_CHECK_STARTED",
                "开始服务器健康检查",
                module="data.server_health",
                workstation_id=self.config.workstation_id,
                details={"configured": bool(self.config.server_host)},
            )
        self.health_check_started.emit()
        if not self.config.server_host or self.config.server_port is None:
            result = self.health_client.check(self.config)
            self._log_health_result(result)
            self.health_changed.emit(result)
            return
        worker = _HealthWorker(generation, self.health_client, self.config)
        self._workers.add(worker)
        worker.signals.completed.connect(self._finish_health_check)
        self.thread_pool.start(worker)

    @Slot(int, object)
    def _finish_health_check(self, generation: int, result: HealthResult) -> None:
        sender = self.sender()
        if isinstance(sender, _WorkerSignals):
            for worker in tuple(self._workers):
                if worker.signals is sender:
                    self._workers.discard(worker)
                    break
        if generation == self._generation:
            self._log_health_result(result)
            self.health_changed.emit(result)

    def _log_health_result(self, result: HealthResult) -> None:
        if self.log_service is None:
            return
        self.log_service.business(
            "SERVER_HEALTH_CHECK_COMPLETED",
            "服务器健康检查完成",
            module="data.server_health",
            workstation_id=self.config.workstation_id,
            duration_ms=result.elapsed_ms,
            success=result.online,
            details={
                "detail": result.detail,
                "status_code": result.status_code,
            },
        )
