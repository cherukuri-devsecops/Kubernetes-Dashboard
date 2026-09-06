import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Some uvicorn loggers stop propagation, so the file handler has to be attached
# to them directly or request logs never reach the collector. Attaching to a
# logger that *does* propagate would write each record twice - once here and
# again at the ancestor that holds the same handler - so propagation is checked
# at attach time rather than assumed.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_MAX_BYTES = 16 * 1024 * 1024
_BACKUP_COUNT = 3


class JsonLineFormatter(logging.Formatter):
    """One JSON object per line, matching monitoring/fluent-bit/parsers.conf."""

    def format(self, record: logging.LogRecord) -> str:
        moment = datetime.fromtimestamp(record.created, timezone.utc)
        payload = {
            # Fluent Bit's %L wants milliseconds and %z wants +0000, no colon.
            "time": f"{moment.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}+0000",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str, log_file: str = "") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    if not log_file:
        return

    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT)
    except OSError as exc:
        # A read-only or missing mount must not stop the API from starting.
        logging.getLogger("kubernetes-dashboard").warning("file logging disabled: %s", exc)
        return

    handler.setFormatter(JsonLineFormatter())
    handler.setLevel(numeric_level)

    logging.getLogger().addHandler(handler)
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        if not uvicorn_logger.propagate:
            uvicorn_logger.addHandler(handler)
