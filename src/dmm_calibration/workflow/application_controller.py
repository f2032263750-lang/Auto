from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from dmm_calibration.config import ConfigRepository, WorkstationConfig
from dmm_calibration.data import HealthResult, ServerHealthClient


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
    ):
        super().__init__()
        self.repository = repository
        self.config = config
        self.health_client = health_client or ServerHealthClient()
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self._generation = 0
        self._workers: set[_HealthWorker] = set()

    def save_config(self, config: WorkstationConfig) -> None:
        self.repository.save(config)
        self.config = config
        self.config_changed.emit(config)
        self.check_server()

    def check_server(self) -> None:
        self._generation += 1
        generation = self._generation
        self.health_check_started.emit()
        if not self.config.server_host or self.config.server_port is None:
            self.health_changed.emit(self.health_client.check(self.config))
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
            self.health_changed.emit(result)
