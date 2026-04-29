from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from typing import Any

try:
    import structlog  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    structlog = None


request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def configure_logging(debug: bool) -> None:
    if structlog is None:
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
            stream=sys.stdout,
        )
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG if debug else logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(message)s", stream=sys.stdout)


def set_request_id(request_id: str | None = None) -> str:
    value = request_id or str(uuid.uuid4())
    request_id_ctx.set(value)
    if structlog is not None:
        structlog.contextvars.bind_contextvars(request_id=value)
    return value


def get_request_id() -> str:
    return request_id_ctx.get("-")


def reset_request_id() -> None:
    request_id_ctx.set("-")
    if structlog is not None:
        structlog.contextvars.clear_contextvars()


def get_logger(name: str | None = None):
    return structlog.get_logger(name) if structlog is not None else logging.getLogger(name)


def log_event(logger: Any, level: int, message: str, **fields: Any) -> None:
    if hasattr(logger, "bind") and structlog is not None:
        if level >= logging.ERROR:
            logger.error(message, **fields)
        elif level >= logging.WARNING:
            logger.warning(message, **fields)
        elif level >= logging.INFO:
            logger.info(message, **fields)
        else:
            logger.debug(message, **fields)
        return

    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    plain_message = f"{message} {suffix}".strip()
    logger.log(level, plain_message)
