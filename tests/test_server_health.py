from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from dmm_calibration.config import WorkstationConfig
from dmm_calibration.data import ServerHealthClient


class _HealthHandler(BaseHTTPRequestHandler):
    response_code = 200

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(self.response_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def local_health_server(response_code: int):
    handler = type(
        "ConfiguredHealthHandler", (_HealthHandler,), {"response_code": response_code}
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ServerHealthClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.config = WorkstationConfig.default(Path(self.temporary_directory.name))
        self.client = ServerHealthClient(timeout_seconds=0.3)

    def test_unconfigured_server_is_offline_without_network_call(self) -> None:
        result = self.client.check(self.config)

        self.assertFalse(result.online)
        self.assertEqual(result.detail, "服务器未配置")
        self.assertIsNone(result.status_code)

    def test_http_200_is_online(self) -> None:
        with local_health_server(200) as port:
            configured = replace(
                self.config, server_host="127.0.0.1", server_port=port
            )
            result = self.client.check(configured)

        self.assertTrue(result.online)
        self.assertEqual(result.status_code, 200)

    def test_http_error_is_offline(self) -> None:
        with local_health_server(503) as port:
            configured = replace(
                self.config, server_host="127.0.0.1", server_port=port
            )
            result = self.client.check(configured)

        self.assertFalse(result.online)
        self.assertEqual(result.status_code, 503)
        self.assertIn("HTTP 503", result.detail)

    def test_unreachable_server_is_offline(self) -> None:
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
        probe.close()
        configured = replace(
            self.config, server_host="127.0.0.1", server_port=unused_port
        )

        result = self.client.check(configured)

        self.assertFalse(result.online)
        self.assertIn("不可达", result.detail)


if __name__ == "__main__":
    unittest.main()
