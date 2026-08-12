"""工位配置模型和持久化边界。"""

from dmm_calibration.config.model import (
    CURRENT_CONFIG_VERSION,
    Environment,
    WorkstationConfig,
    ConfigValidationError,
    validate_config,
)
from dmm_calibration.config.repository import (
    ConfigFileError,
    ConfigRepository,
    ConfigWriteError,
    LoadResult,
)

__all__ = [
    "CURRENT_CONFIG_VERSION",
    "ConfigFileError",
    "ConfigRepository",
    "ConfigValidationError",
    "ConfigWriteError",
    "Environment",
    "LoadResult",
    "WorkstationConfig",
    "validate_config",
]
