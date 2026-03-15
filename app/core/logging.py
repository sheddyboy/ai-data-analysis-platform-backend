"""Loguru logging setup for the application."""

import logging
import sys

from loguru import logger

from app.config import settings


class InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, SQLAlchemy, LangChain, etc.) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """Configure loguru as the sole logging sink and intercept stdlib logging."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Intercept all stdlib loggers so uvicorn, SQLAlchemy, LangChain, etc.
    # all flow through loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in list(logging.root.manager.loggerDict):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False
