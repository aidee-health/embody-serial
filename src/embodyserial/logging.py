"""Logging utilities for the embodyserial library."""

import logging

# Library root logger name
LIBRARY_LOGGER_NAME = "embodyserial"


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger for the library."""
    if name:
        return logging.getLogger(f"{LIBRARY_LOGGER_NAME}.{name}")
    return logging.getLogger(LIBRARY_LOGGER_NAME)


def configure_library_logging(
    level: int = logging.INFO, format_string: str | None = None, datefmt: str | None = None
) -> None:
    """Configure library logging (primarily for CLI use)."""
    logger = logging.getLogger(LIBRARY_LOGGER_NAME)
    logger.setLevel(level)

    # Remove any existing NullHandlers and add StreamHandler for CLI
    logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.NullHandler)]

    if not logger.handlers:
        handler = logging.StreamHandler()

        if format_string:
            formatter = logging.Formatter(format_string, datefmt=datefmt)
            handler.setFormatter(formatter)

        logger.addHandler(handler)
