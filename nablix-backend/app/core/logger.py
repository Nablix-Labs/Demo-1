from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


STANDARD_LOG_RECORD_FIELDS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
)


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "event": record.getMessage(),
        }
        metadata: dict[str, object] = {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_LOG_RECORD_FIELDS and key != "message"
        }
        payload.update(metadata)
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logger(name: str) -> logging.Logger:
    configured_logger = logging.getLogger(name)
    configured_logger.setLevel(logging.INFO)
    configured_logger.propagate = False
    if len(configured_logger.handlers) > 0:
        return configured_logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(StructuredJsonFormatter())
    configured_logger.addHandler(handler)
    return configured_logger


logger: logging.Logger = setup_logger("nablix_backend")
