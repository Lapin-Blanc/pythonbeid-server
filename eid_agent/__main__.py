from __future__ import annotations

import logging

import uvicorn

from eid_agent.app import create_app
from eid_agent.config import load_settings, validate_tls_settings


def main() -> None:
    settings = load_settings()
    validate_tls_settings(settings)

    app = create_app(settings=settings)
    host = "127.0.0.1"

    uvicorn_kwargs = {
        "host": host,
        "port": settings.port,
        "log_level": settings.log_level.lower(),
    }
    if settings.https_enabled:
        uvicorn_kwargs["ssl_certfile"] = settings.tls_cert_path
        uvicorn_kwargs["ssl_keyfile"] = settings.tls_key_path
        logging.getLogger(__name__).info("Starting in HTTPS mode.")
    else:
        logging.getLogger(__name__).info("Starting in HTTP mode.")

    logging.getLogger(__name__).info(
        "eid-agent listening on %s:%s (origins=%s).",
        host,
        settings.port,
        len(settings.allowed_origins),
    )

    uvicorn.run(app, **uvicorn_kwargs)


if __name__ == "__main__":
    main()
