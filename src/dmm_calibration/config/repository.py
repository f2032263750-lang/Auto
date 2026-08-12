from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from dmm_calibration.config.model import (
    ConfigValidationError,
    WorkstationConfig,
    validate_config,
)


class ConfigFileError(RuntimeError):
    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"无法读取配置文件 {path}：{reason}")


class ConfigWriteError(RuntimeError):
    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"无法保存配置文件 {path}：{reason}")


@dataclass(frozen=True, slots=True)
class LoadResult:
    config: WorkstationConfig
    created: bool


class ConfigRepository:
    def __init__(self, config_path: Path, base_directory: Path):
        self.config_path = config_path.resolve()
        self.base_directory = base_directory.resolve()

    def load_or_create(self) -> LoadResult:
        if not self.config_path.exists():
            config = WorkstationConfig.default(self.base_directory)
            self.save(config)
            return LoadResult(config=config, created=True)
        return LoadResult(config=self.load(), created=False)

    def load(self) -> WorkstationConfig:
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigFileError(self.config_path, str(exc)) from exc
        if not isinstance(raw, dict):
            raise ConfigFileError(self.config_path, "配置根节点必须是 JSON 对象")
        try:
            return WorkstationConfig.from_mapping(raw)
        except ConfigValidationError as exc:
            raise ConfigFileError(self.config_path, str(exc)) from exc

    def save(self, config: WorkstationConfig) -> None:
        validate_config(config)
        try:
            self._ensure_directories(config)
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                config.to_mapping(), ensure_ascii=False, indent=2
            ) + "\n"
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self.config_path.name}.",
                suffix=".tmp",
                dir=self.config_path.parent,
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, self.config_path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        except ConfigValidationError:
            raise
        except OSError as exc:
            raise ConfigWriteError(self.config_path, str(exc)) from exc

    def recover_default(self) -> tuple[WorkstationConfig, Path | None]:
        backup_path: Path | None = None
        if self.config_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_path = self.config_path.with_name(
                f"{self.config_path.stem}.broken.{timestamp}{self.config_path.suffix}"
            )
            try:
                os.replace(self.config_path, backup_path)
            except OSError as exc:
                raise ConfigWriteError(self.config_path, str(exc)) from exc
        config = WorkstationConfig.default(self.base_directory)
        self.save(config)
        return config, backup_path

    @staticmethod
    def _ensure_directories(config: WorkstationConfig) -> None:
        for raw_path in (
            config.excel_template_path,
            config.cache_directory,
            config.log_directory,
        ):
            Path(raw_path).mkdir(parents=True, exist_ok=True)
