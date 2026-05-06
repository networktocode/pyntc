"""Logging utilities for Pyntc."""

import logging
import os
from logging.handlers import RotatingFileHandler

APP = "pyntc"
""" Application name, used as the logging root. """

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
""" Logging format to use. """

DEBUG_FORMAT = "%(asctime)s [%(levelname)s] [%(module)s] [%(funcName)s] %(name)s: %(message)s"
""" Logging format used when debug output is enabled. """


def get_log(name=None):
    """Get log namespace and creates logger and rotating file handler.

    A :class:`RotatingFileHandler` is attached if the ``PYNTC_LOG_FILE``
    environment variable is set, in which case its value is used as the log
    file path.

    Args:
        name (str, optional): Sublogger name. Defaults to None.

    Returns:
        (logger): Return a logger instance in the :data:`APP` namespace.
    """
    logger_name = f"{APP}.{name}" if name else APP
    _logger = logging.getLogger(logger_name)

    log_file = os.environ.get("PYNTC_LOG_FILE")
    if log_file and not any(
        isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(log_file)
        for h in _logger.handlers
    ):
        _logger.addHandler(RotatingFileHandler(log_file, maxBytes=2000))

    return _logger


def init(**kwargs):
    """Initialize logging using sensible defaults.

    If keyword arguments are passed to this function, they will be passed
    directly to the :func:`logging.basicConfig` call in turn.

    Args:
        **kwargs (dict): Arguments to pass for logging configuration


    """
    _debug = os.environ.get("PYNTC_DEBUG", None)
    log_format = DEBUG_FORMAT if _debug else FORMAT

    log_level = getattr(logging, os.environ.get("PYNTC_LOG_LEVEL", "info").upper())
    log_level = logging.DEBUG if _debug else log_level

    kwargs.setdefault("format", log_format)
    kwargs.setdefault("level", log_level)
    host = kwargs.pop("host", None)

    logging.basicConfig(**kwargs)
    # info is defined at the end of the file
    info("Logging initialized for host %s.", host)


def logger(level):
    """Wrap around logger methods.

    Args:
        level (str): defines the log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        (str): Returns logger.<level> type of string.
    """
    return getattr(get_log(), level)


critical = logger("critical")
error = logger("error")
warning = logger("warning")
info = logger("info")
debug = logger("debug")
exception = logger("exception")
