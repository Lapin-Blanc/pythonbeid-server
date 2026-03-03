from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque

from eid_agent.errors import AgentError


class SessionStore:
    def __init__(self, ttl_seconds: int, max_tokens: int = 1) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_tokens = max_tokens
        self._tokens: dict[str, float] = {}

    def create_session(self) -> tuple[str, int]:
        self._cleanup_expired()
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self.ttl_seconds
        self._tokens[token] = expires_at
        self._enforce_capacity()
        return token, self.ttl_seconds

    def validate(self, token: str | None) -> str:
        self._cleanup_expired()
        if not token:
            raise AgentError(401, "UNAUTHORIZED", "Missing bearer token.")
        expires_at = self._tokens.get(token)
        if not expires_at:
            raise AgentError(401, "UNAUTHORIZED", "Invalid or expired session token.")
        if expires_at <= time.time():
            self._tokens.pop(token, None)
            raise AgentError(401, "UNAUTHORIZED", "Invalid or expired session token.")
        return token

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [token for token, expires_at in self._tokens.items() if expires_at <= now]
        for token in expired:
            self._tokens.pop(token, None)

    def _enforce_capacity(self) -> None:
        if len(self._tokens) <= self.max_tokens:
            return
        sorted_tokens = sorted(self._tokens.items(), key=lambda item: item[1])
        for token, _ in sorted_tokens[:-self.max_tokens]:
            self._tokens.pop(token, None)


def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise AgentError(401, "UNAUTHORIZED", "Missing Authorization header.")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AgentError(401, "UNAUTHORIZED", "Authorization must be Bearer <token>.")
    return token.strip()


class RateLimiter:
    def __init__(self, max_requests_per_minute: int) -> None:
        self.max_requests_per_minute = max_requests_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        queue = self._hits[key]
        while queue and (now - queue[0]) >= 60.0:
            queue.popleft()
        if len(queue) >= self.max_requests_per_minute:
            return False
        queue.append(now)
        return True
