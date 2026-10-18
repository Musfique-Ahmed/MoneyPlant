"""Structured logging configuration.

The default formatter is JSON. When ``LOG_REDACT_FINANCIAL`` is true, log
records containing keys whose name matches ``REDACT_KEYS`` are replaced with
``"[REDACTED]"``. This is deliberately a coarse redaction — the engine
itself does not log monetary values.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

REDACT_KEYS = {
    "amount",
    "money",
    "balance",
    "transaction_amount",
    "revenue",
    "expense",
    "profit",
    "cash",
    "salary",
    "price",
    "total",
    "subtotal",
    "tax",
    "fee",
    "cost",
    "value",
    "wage",
    "payment",
    "credit",
    "debit",
    "openai_api_key",
    "anthropic_api_key",
    "secret_key",
    "authorization",
    "api_key",
}


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        return True

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        # JSON-friendly: the standard Formatter is replaced below.
        return super().format(record)


class JsonFormatter(logging.Formatter):
    def __init__(self, redact: bool = True) -> None:
        super().__init__()
        self._redact = redact

    def _scrub(self, obj: Any) -> Any:
        if not self._redact:
            return obj
        if isinstance(obj, dict):
            return {k: ("[REDACTED]" if k.lower() in REDACT_KEYS else self._scrub(v)) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._scrub(v) for v in obj]
        return obj

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Optional structured fields attached via `logger.info("msg", extra={...})`
        for key, value in record.__dict__.items():
            if key in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "message",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
            }:
                continue
            payload[key] = self._scrub(value)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", redact: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(redact=redact))
    root = logging.getLogger()
    # Replace existing handlers so config is idempotent across reloads.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Silence noisy libs.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
