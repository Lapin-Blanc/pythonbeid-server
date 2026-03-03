from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentError(Exception):
    status_code: int
    code: str
    message: str
    details: str | None = None

    def as_dict(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload
