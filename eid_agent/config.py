from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    load_dotenv = None


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be > 0.")
    return value


def _parse_origins(raw: str | None) -> list[str]:
    if raw is None:
        return []
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        return []
    if "*" in origins:
        raise ValueError("EID_AGENT_ALLOWED_ORIGINS cannot contain '*'.")
    return origins


@dataclass(frozen=True)
class Settings:
    port: int = 8765
    allowed_origins: list[str] = field(default_factory=list)
    session_ttl_seconds: int = 120
    rate_limit_per_minute: int = 10
    log_level: str = "INFO"
    https_enabled: bool = False
    tls_cert_path: str | None = None
    tls_key_path: str | None = None


def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file and load_dotenv is not None:
        dotenv_path = Path(".env")
        if dotenv_path.is_file():
            try:
                load_dotenv(dotenv_path=dotenv_path, override=False, encoding="utf-8")
            except UnicodeDecodeError:
                # Ignore invalid .env encoding and continue with OS env variables.
                pass

    settings = Settings(
        port=_parse_int("EID_AGENT_PORT", 8765),
        allowed_origins=_parse_origins(os.getenv("EID_AGENT_ALLOWED_ORIGINS")),
        session_ttl_seconds=_parse_int("EID_AGENT_SESSION_TTL_SECONDS", 120),
        rate_limit_per_minute=_parse_int("EID_AGENT_RATE_LIMIT_PER_MINUTE", 10),
        log_level=os.getenv("EID_AGENT_LOG_LEVEL", "INFO").upper(),
        https_enabled=_parse_bool(os.getenv("EID_AGENT_HTTPS"), default=False),
        tls_cert_path=os.getenv("EID_AGENT_TLS_CERT_PATH"),
        tls_key_path=os.getenv("EID_AGENT_TLS_KEY_PATH"),
    )
    return settings


def validate_tls_settings(settings: Settings) -> None:
    if not settings.https_enabled:
        return
    if not settings.tls_cert_path or not settings.tls_key_path:
        raise ValueError(
            "HTTPS is enabled but EID_AGENT_TLS_CERT_PATH or EID_AGENT_TLS_KEY_PATH is missing."
        )
    cert_path = Path(settings.tls_cert_path)
    key_path = Path(settings.tls_key_path)
    if not cert_path.is_file() or not key_path.is_file():
        raise ValueError("HTTPS certificate/key paths are invalid.")
