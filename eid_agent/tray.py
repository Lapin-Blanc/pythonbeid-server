"""Windows system tray application embedding the eid-agent API server.

The server runs in a background thread while a pystray icon provides
status checks and a clean shutdown. Designed to run without a console
(gui-script / PyInstaller --noconsole), so logging goes to a rotating
file under the per-user application data directory.
"""

from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn

from eid_agent import __version__
from eid_agent.app import create_app
from eid_agent.config import Settings, load_settings, validate_tls_settings
from eid_agent.errors import AgentError
from eid_agent.reader import PythonBeIDBackend

logger = logging.getLogger(__name__)

APP_NAME = "eID Agent"
APP_DIR_NAME = "eid-agent"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
STARTUP_TIMEOUT_SECONDS = 15.0


def get_app_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME}"


def setup_file_logging(app_data_dir: Path, level: str = "INFO") -> None:
    log_dir = app_data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "eid-agent.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def load_user_env(app_data_dir: Path) -> None:
    """Load a persistent per-user .env file (CORS origins, port, ...)."""
    env_path = app_data_dir / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - optional dependency fallback
        return
    try:
        load_dotenv(dotenv_path=env_path, override=False, encoding="utf-8")
        logger.info("Loaded user configuration from %s.", env_path)
    except UnicodeDecodeError:
        logger.warning("Ignored user .env file with invalid encoding: %s", env_path)


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


class ServerController:
    """Run the uvicorn server in a daemon thread with clean shutdown."""

    def __init__(
        self,
        settings: Settings,
        reader_backend: PythonBeIDBackend | None = None,
    ) -> None:
        self.settings = settings
        self.backend = reader_backend or PythonBeIDBackend()
        app = create_app(settings=settings, reader_backend=self.backend)
        config_kwargs: dict[str, Any] = {
            "host": "127.0.0.1",
            "port": settings.port,
            "log_level": settings.log_level.lower(),
            "log_config": None,
        }
        if settings.https_enabled:
            config_kwargs["ssl_certfile"] = settings.tls_cert_path
            config_kwargs["ssl_keyfile"] = settings.tls_key_path
        self._server = uvicorn.Server(uvicorn.Config(app, **config_kwargs))
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        scheme = "https" if self.settings.https_enabled else "http"
        return f"{scheme}://127.0.0.1:{self.settings.port}"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, timeout: float = STARTUP_TIMEOUT_SECONDS) -> None:
        self._thread = threading.Thread(
            target=self._server.run, name="eid-agent-server", daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                logger.info("Server started on %s.", self.base_url)
                return
            if not self._thread.is_alive():
                break
            time.sleep(0.05)
        raise RuntimeError(f"Server failed to start on {self.base_url}.")

    def stop(self, timeout: float = 5.0) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Server stopped.")


def _create_icon_image(size: int = 64):
    """Draw a stylized eID card (rounded card with chip) as the tray icon."""
    from PIL import Image, ImageDraw

    card_color = (13, 71, 161)
    chip_color = (255, 193, 7)
    line_color = (227, 242, 253)

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 10
    top = size // 4
    bottom = size - top
    draw.rounded_rectangle(
        (margin, top, size - margin, bottom),
        radius=size // 10,
        fill=card_color,
    )
    chip_left = margin + size // 8
    chip_top = top + size // 10
    draw.rounded_rectangle(
        (chip_left, chip_top, chip_left + size // 5, chip_top + size // 7),
        radius=size // 40,
        fill=chip_color,
    )
    line_left = margin + size // 8
    line_right = size - margin - size // 8
    line_y = bottom - size // 6
    draw.line((line_left, line_y, line_right, line_y), fill=line_color, width=max(1, size // 24))
    line_y -= size // 9
    draw.line((line_left, line_y, line_left + (line_right - line_left) // 2, line_y), fill=line_color, width=max(1, size // 24))
    return image


def _show_error_dialog(message: str) -> None:
    if sys.platform == "win32":
        MB_ICONERROR = 0x10
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, MB_ICONERROR)
    else:  # pragma: no cover - non-Windows fallback
        print(message, file=sys.stderr)


def _format_status(status_payload: dict[str, Any]) -> str:
    reader = "oui" if status_payload.get("has_reader") else "non"
    card = "oui" if status_payload.get("has_card") else "non"
    return f"Lecteur détecté : {reader}\nCarte insérée : {card}"


def _build_icon(controller: ServerController):
    import pystray

    def on_check_status(icon: "pystray.Icon", _item: Any) -> None:
        try:
            payload = controller.backend.status()
            message = _format_status(payload)
        except AgentError as exc:
            message = f"Erreur : {exc.message}"
        except Exception:
            logger.exception("Status check failed.")
            message = "Erreur inattendue lors de la vérification."
        icon.notify(message, APP_NAME)

    def on_open_health(_icon: Any, _item: Any) -> None:
        webbrowser.open(f"{controller.base_url}/v1/health")

    def on_open_config(_icon: Any, _item: Any) -> None:
        app_dir = get_app_data_dir()
        app_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(app_dir))  # noqa: S606 - opening local folder is intended

    def on_quit(icon: "pystray.Icon", _item: Any) -> None:
        controller.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            f"{APP_NAME} v{__version__} - {controller.base_url}",
            None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Vérifier lecteur / carte", on_check_status),
        pystray.MenuItem("Ouvrir le health check", on_open_health),
        pystray.MenuItem("Ouvrir le dossier de configuration", on_open_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", on_quit),
    )
    return pystray.Icon(
        name="eid-agent",
        icon=_create_icon_image(),
        title=f"{APP_NAME} - {controller.base_url}",
        menu=menu,
    )


def main() -> None:
    app_data_dir = get_app_data_dir()
    try:
        setup_file_logging(app_data_dir)
    except OSError:
        # Never block startup on logging issues; continue without file logs.
        pass

    load_user_env(app_data_dir)

    try:
        settings = load_settings()
        validate_tls_settings(settings)
    except ValueError as exc:
        logger.error("Invalid configuration: %s", exc)
        _show_error_dialog(f"Configuration invalide :\n{exc}")
        sys.exit(1)

    if not port_is_free(settings.port):
        message = (
            f"Le port {settings.port} est déjà utilisé.\n"
            f"{APP_NAME} est probablement déjà en cours d'exécution."
        )
        logger.error("Port %s is already in use; exiting.", settings.port)
        _show_error_dialog(message)
        sys.exit(1)

    controller = ServerController(settings)
    try:
        controller.start()
    except RuntimeError as exc:
        logger.error("%s", exc)
        _show_error_dialog(
            f"Impossible de démarrer le serveur sur {controller.base_url}.\n"
            "Consultez les logs pour plus de détails."
        )
        sys.exit(1)

    icon = _build_icon(controller)
    try:
        icon.run()
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
