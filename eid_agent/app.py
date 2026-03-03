from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from eid_agent import __version__
from eid_agent.config import Settings, load_settings
from eid_agent.errors import AgentError
from eid_agent.reader import ALLOWED_FIELDS, DEFAULT_FIELDS, PythonBeIDBackend
from eid_agent.security import RateLimiter, SessionStore, extract_bearer_token

logger = logging.getLogger(__name__)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def success_response(**payload: Any) -> dict[str, Any]:
    return {"ok": True, "timestamp": utc_timestamp(), **payload}


def error_response(error: AgentError) -> dict[str, Any]:
    return {
        "ok": False,
        "timestamp": utc_timestamp(),
        "error": error.as_dict(),
    }


class ReadRequest(BaseModel):
    include_photo: bool = False
    fields: list[str] | None = Field(default=None)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(
    settings: Settings | None = None,
    reader_backend: PythonBeIDBackend | None = None,
) -> FastAPI:
    runtime_settings = settings or load_settings()
    _setup_logging(runtime_settings.log_level)

    app = FastAPI(title="eid-agent", version=__version__)
    app.state.settings = runtime_settings
    app.state.sessions = SessionStore(ttl_seconds=runtime_settings.session_ttl_seconds, max_tokens=1)
    app.state.rate_limiter = RateLimiter(runtime_settings.rate_limit_per_minute)
    app.state.reader_backend = reader_backend or PythonBeIDBackend()

    if "*" in runtime_settings.allowed_origins:
        raise ValueError("CORS wildcard '*' is not allowed.")

    if runtime_settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=runtime_settings.allowed_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )
        logger.info("CORS enabled for %s origin(s).", len(runtime_settings.allowed_origins))
    else:
        logger.info("CORS is disabled (EID_AGENT_ALLOWED_ORIGINS not set).")

    @app.exception_handler(AgentError)
    async def handle_agent_error(_: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_response(exc))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(item) for item in err.get('loc', []))}: {err.get('msg', 'Invalid request')}"
            for err in exc.errors()
        )
        error = AgentError(400, "BAD_REQUEST", "Invalid request payload.", details=details or None)
        return JSONResponse(status_code=400, content=error_response(error))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        if logger.isEnabledFor(logging.DEBUG):
            logger.exception("Unhandled error.")
        else:
            logger.error("Unhandled error: %s", exc)
        error = AgentError(500, "INTERNAL_ERROR", "Unexpected internal error.")
        return JSONResponse(status_code=500, content=error_response(error))

    def require_token(
        request: Request, authorization: str | None = Header(default=None)
    ) -> str:
        token = extract_bearer_token(authorization)
        return request.app.state.sessions.validate(token)

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        return success_response(service="eid-agent", version=__version__)

    @app.post("/v1/session")
    async def create_session(request: Request) -> dict[str, Any]:
        token, expires_in = request.app.state.sessions.create_session()
        return success_response(token=token, expires_in=expires_in)

    @app.get("/v1/status")
    async def status(request: Request, token: str = Depends(require_token)) -> dict[str, Any]:
        _ = token
        status_payload = request.app.state.reader_backend.status()
        return success_response(**status_payload)

    @app.post("/v1/read")
    async def read(
        body: ReadRequest,
        request: Request,
        token: str = Depends(require_token),
    ) -> dict[str, Any]:
        selected_fields = body.fields or list(DEFAULT_FIELDS)
        unknown_fields = [field for field in selected_fields if field not in ALLOWED_FIELDS]
        if unknown_fields:
            joined = ", ".join(sorted(unknown_fields))
            raise AgentError(400, "BAD_REQUEST", f"Unknown field(s): {joined}")

        if not request.app.state.rate_limiter.allow(key=token):
            raise AgentError(429, "RATE_LIMITED", "Rate limit exceeded for /v1/read.")

        raw_data = request.app.state.reader_backend.read(include_photo=body.include_photo)
        data = {field: raw_data.get(field) for field in selected_fields}
        data["photo_base64"] = raw_data.get("photo_base64") if body.include_photo else None
        if body.include_photo and raw_data.get("photo_mime"):
            data["photo_mime"] = raw_data["photo_mime"]

        return success_response(data=data)

    @app.post("/v1/logout")
    async def logout(request: Request, token: str = Depends(require_token)) -> dict[str, Any]:
        request.app.state.sessions.revoke(token)
        return success_response()

    return app


app = create_app()
