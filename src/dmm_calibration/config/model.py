from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
import re
from typing import Any, Mapping


CURRENT_CONFIG_VERSION = 1
_WORKSTATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ConfigValidationError(ValueError):
    def __init__(self, errors: list[str] | tuple[str, ...]):
        self.errors = tuple(errors)
        super().__init__("；".join(self.errors))


@dataclass(frozen=True, slots=True)
class WorkstationConfig:
    config_version: int
    environment: Environment
    workstation_id: str
    calibrator_model: str
    calibrator_interface: str
    calibrator_gpib_controller: str
    calibrator_gpib_address: int
    uut_terminal: str
    default_temperature: Decimal
    default_humidity: Decimal
    excel_template_path: str
    cache_directory: str
    log_directory: str
    server_host: str
    server_port: int | None
    offline_cache_enabled: bool

    @classmethod
    def default(cls, base_directory: Path) -> WorkstationConfig:
        base = base_directory.resolve()
        return cls(
            config_version=CURRENT_CONFIG_VERSION,
            environment=Environment.DEVELOPMENT,
            workstation_id="CAL-01",
            calibrator_model="Fluke 9100",
            calibrator_interface="GPIB转USB",
            calibrator_gpib_controller="GPIB0",
            calibrator_gpib_address=10,
            uut_terminal="FRONT",
            default_temperature=Decimal("23"),
            default_humidity=Decimal("50"),
            excel_template_path=str(base / "templates"),
            cache_directory=str(base / "data" / "cache"),
            log_directory=str(base / "data" / "logs"),
            server_host="",
            server_port=None,
            offline_cache_enabled=True,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> WorkstationConfig:
        expected = {
            "config_version",
            "environment",
            "workstation_id",
            "calibrator_model",
            "calibrator_interface",
            "calibrator_gpib_controller",
            "calibrator_gpib_address",
            "uut_terminal",
            "default_temperature",
            "default_humidity",
            "excel_template_path",
            "cache_directory",
            "log_directory",
            "server_host",
            "server_port",
            "offline_cache_enabled",
        }
        missing = sorted(expected.difference(raw))
        unknown = sorted(set(raw).difference(expected))
        structural_errors: list[str] = []
        if missing:
            structural_errors.append(f"缺少字段：{', '.join(missing)}")
        if unknown:
            structural_errors.append(f"未知字段：{', '.join(unknown)}")
        if structural_errors:
            raise ConfigValidationError(structural_errors)

        errors: list[str] = []

        def integer(name: str, *, optional: bool = False) -> int | None:
            value = raw[name]
            if optional and value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{name} 必须是整数")
                return None
            return value

        def text(name: str) -> str:
            value = raw[name]
            if not isinstance(value, str):
                errors.append(f"{name} 必须是字符串")
                return ""
            return value.strip()

        def decimal_value(name: str) -> Decimal:
            value = raw[name]
            if isinstance(value, bool):
                errors.append(f"{name} 必须是十进制数")
                return Decimal(0)
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError):
                errors.append(f"{name} 必须是十进制数")
                return Decimal(0)

        version = integer("config_version")
        address = integer("calibrator_gpib_address")
        port = integer("server_port", optional=True)
        try:
            environment = Environment(text("environment"))
        except ValueError:
            environment = Environment.DEVELOPMENT
            errors.append("environment 必须是 development、test 或 production")

        offline = raw["offline_cache_enabled"]
        if not isinstance(offline, bool):
            errors.append("offline_cache_enabled 必须是布尔值")
            offline = False

        config = cls(
            config_version=version if version is not None else -1,
            environment=environment,
            workstation_id=text("workstation_id"),
            calibrator_model=text("calibrator_model"),
            calibrator_interface=text("calibrator_interface"),
            calibrator_gpib_controller=text("calibrator_gpib_controller"),
            calibrator_gpib_address=address if address is not None else -1,
            uut_terminal=text("uut_terminal").upper(),
            default_temperature=decimal_value("default_temperature"),
            default_humidity=decimal_value("default_humidity"),
            excel_template_path=text("excel_template_path"),
            cache_directory=text("cache_directory"),
            log_directory=text("log_directory"),
            server_host=text("server_host"),
            server_port=port,
            offline_cache_enabled=offline,
        )
        try:
            validate_config(config)
        except ConfigValidationError as exc:
            errors.extend(exc.errors)
        if errors:
            raise ConfigValidationError(errors)
        return config

    def to_mapping(self) -> dict[str, Any]:
        return {
            "config_version": self.config_version,
            "environment": self.environment.value,
            "workstation_id": self.workstation_id,
            "calibrator_model": self.calibrator_model,
            "calibrator_interface": self.calibrator_interface,
            "calibrator_gpib_controller": self.calibrator_gpib_controller,
            "calibrator_gpib_address": self.calibrator_gpib_address,
            "uut_terminal": self.uut_terminal,
            "default_temperature": str(self.default_temperature),
            "default_humidity": str(self.default_humidity),
            "excel_template_path": self.excel_template_path,
            "cache_directory": self.cache_directory,
            "log_directory": self.log_directory,
            "server_host": self.server_host,
            "server_port": self.server_port,
            "offline_cache_enabled": self.offline_cache_enabled,
        }


def validate_config(config: WorkstationConfig) -> None:
    errors: list[str] = []
    if config.config_version != CURRENT_CONFIG_VERSION:
        errors.append(
            f"不支持 config_version={config.config_version}，当前版本为 {CURRENT_CONFIG_VERSION}"
        )
    if not _WORKSTATION_ID_PATTERN.fullmatch(config.workstation_id):
        errors.append("workstation_id 只能包含字母、数字、下划线和连字符")
    for field_name, value in (
        ("calibrator_model", config.calibrator_model),
        ("calibrator_interface", config.calibrator_interface),
        ("calibrator_gpib_controller", config.calibrator_gpib_controller),
    ):
        if not value.strip():
            errors.append(f"{field_name} 不能为空")
    if not 0 <= config.calibrator_gpib_address <= 30:
        errors.append("calibrator_gpib_address 必须在 0～30 之间")
    if config.uut_terminal != "FRONT":
        errors.append("uut_terminal 首版必须为 FRONT")
    if not config.default_temperature.is_finite():
        errors.append("default_temperature 必须是有限十进制数")
    if not config.default_humidity.is_finite() or not Decimal("0") <= config.default_humidity <= Decimal("100"):
        errors.append("default_humidity 必须在 0～100 之间")
    for field_name, value in (
        ("excel_template_path", config.excel_template_path),
        ("cache_directory", config.cache_directory),
        ("log_directory", config.log_directory),
    ):
        if not value or not Path(value).is_absolute():
            errors.append(f"{field_name} 必须是绝对路径")
    host_configured = bool(config.server_host.strip())
    port_configured = config.server_port is not None
    if host_configured != port_configured:
        errors.append("server_host 和 server_port 必须同时填写或同时留空")
    if any(character.isspace() for character in config.server_host):
        errors.append("server_host 不能包含空白字符")
    if port_configured and not 1 <= config.server_port <= 65535:
        errors.append("server_port 必须在 1～65535 之间")
    if errors:
        raise ConfigValidationError(errors)
