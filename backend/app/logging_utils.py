"""Logging setup with secret redaction applied to every record.

Redaction happens in a log-record factory, i.e. when a record is *created*, so every
handler (console, files, test capture, third-party integrations) only ever sees the
redacted text — including formatted exception tracebacks.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"
# OpenAI-style keys (sk-..., sk-proj-...) and bearer tokens, even if unknown to us.
_KEY_PATTERNS = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9_\-.]{8,}")

_known_secrets: list[str] = []
_factory_installed = False


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


def redact_record(record: logging.LogRecord) -> logging.LogRecord:
    """Freeze the record's message (incl. traceback) into redacted plain text."""
    try:
        message = record.getMessage()
    except Exception:  # malformed format args: fall back to the raw template
        message = str(record.msg)
    if record.exc_info:
        message += "\n" + logging.Formatter().formatException(record.exc_info)
        record.exc_info = None
        record.exc_text = None
    record.msg = redact(message)
    record.args = None
    return record


class RedactingFilter(logging.Filter):
    """Handler-level safety net (e.g. for records created before the factory existed)."""

    def filter(self, record: logging.LogRecord) -> bool:
        redact_record(record)
        return True


def _install_record_factory() -> None:
    global _factory_installed
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs) -> logging.LogRecord:
        return redact_record(previous(*args, **kwargs))

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(level: int = logging.INFO) -> None:
    """Install redaction and a console handler (idempotent)."""
    _install_record_factory()
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)
    root.setLevel(level)
    # The OpenAI SDK and httpx can log request details at DEBUG; keep them quiet.
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
