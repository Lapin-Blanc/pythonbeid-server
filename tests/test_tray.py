from __future__ import annotations

import socket

import httpx

from eid_agent.config import Settings
from eid_agent.tray import ServerController, port_is_free


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_server_controller_start_serve_stop() -> None:
    port = _free_port()
    controller = ServerController(Settings(port=port))
    controller.start()
    try:
        assert controller.running
        assert not port_is_free(port)
        response = httpx.get(f"http://127.0.0.1:{port}/v1/health", timeout=5.0)
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["service"] == "eid-agent"
    finally:
        controller.stop()
    assert not controller.running
    assert port_is_free(port)
