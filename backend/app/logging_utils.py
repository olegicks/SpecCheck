"""Logging setup with secret redaction applied to every record."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"
# OpenAI-style keys (sk-..., sk-proj-...) and bearer tokens, even if unknown to us.
_KEY_PATTERNS = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9_\-.]{8,}")

_known_secrets: list[str] = []


def register_secrets(secrets: Iterable[str]) -> None:
    """Remember exact secret values so they are redacted even if they lack a known prefix."""
    for secret in secrets:
        if secret and secret not in _known_secrets:
            _known_secrets.append(secret)


def redact(text: str) -> str:
    """Remove secrets from arbitrary text."""
    for secret in _known_secrets:
        text = text.replace(secret, REDACTED)
    return _KEY_PATTERNS.sub(REDACTED, text)


class RedactingFilter(logging.Filter):
    """Rewrites the final log message with secrets removed."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
            record.exc_text = None
        record.msg = redact(message)
        record.args = None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Install a redacting handler on the root and uvicorn loggers (idempotent)."""
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "openai"):
        logger = logging.getLogger(name)
        for h in logger.handlers:
            if not any(isinstance(f, RedactingFilter) for f in h.filters):
                h.addFilter(RedactingFilter())
    # The OpenAI SDK and httpx can log request details at DEBUG; keep them quiet.
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
