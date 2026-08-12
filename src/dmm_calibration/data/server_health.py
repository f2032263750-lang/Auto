from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dmm_calibration.config import WorkstationConfig


@dataclass(frozen=True, slots=True)
class HealthResult:
    online: bool
    detail: str
    checked_at: datetime
    elapsed_ms: int
    status_code: int | None = None


class ServerHealthClient:
    """M1 客户端健康探测；不代表正式服务端框架选择。"""

    def __init__(self, timeout_seconds: float = 2.0):
        self.timeout_seconds = timeout_seconds

    def check(self, config: WorkstationConfig) -> HealthResult:
        started = perf_counter()
        if not config.server_host or config.server_port is None:
            return self._result(False, "服务器未配置", started)

        url = f"http://{config.server_host}:{config.server_port}/health"
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "dmm-calibration/0.1.0"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = response.status
                response.read(1024)
            if 200 <= status_code < 300:
                return self._result(True, "服务器在线", started, status_code)
            return self._result(
                False, f"服务器返回 HTTP {status_code}", started, status_code
            )
        except HTTPError as exc:
            return self._result(
                False, f"服务器返回 HTTP {exc.code}", started, exc.code
            )
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return self._result(False, f"服务器不可达：{reason}", started)

    @staticmethod
    def _result(
        online: bool,
        detail: str,
        started: float,
        status_code: int | None = None,
    ) -> HealthResult:
        return HealthResult(
            online=online,
            detail=detail,
            checked_at=datetime.now(timezone.utc),
            elapsed_ms=max(0, round((perf_counter() - started) * 1000)),
            status_code=status_code,
        )
