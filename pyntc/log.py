<<<<<<< HEAD
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

    Args:
        name (str, optional): Sublogger name. Defaults to None.

    Returns:
        (logger): Return a logger instance in the :data:`APP` namespace.
    """
    logger_name = f"{APP}.{name}" if name else APP
    # file handler
    handler = RotatingFileHandler(f"{logger_name}.log", maxBytes=2000)
    _logger = logging.getLogger(logger_name)
    _logger.addHandler(handler)

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

    logging.basicConfig(**kwargs)
    # info is defined at the end of the file
    info("Logging initialized for host %s.", kwargs.get("host"))


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
=======
"""
Logging utilities for pyntc.

This module contains helpers and wrappers for making logging more consistent across applications.

How to use me:

    >>> from pyntc.log import initialize_logging
    >>> log = initialize_logging(level="debug")
"""

import logging.config

APP = "pyntc"


def initialize_logging(config=None, level="INFO", filename=None):
    """Initialize logging using sensible defaults.

    Args:
        config (dict): User provided configuration dictionary.
        level (str): The level of logging for STDOUT logging.
        filename (str): Where to output debug logging to file.

    """
    if not config:
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
                "debug": {
                    "format": "%(asctime)s [%(levelname)s] [%(module)s] [%(funcName)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
            },
            "handlers": {
                "standard": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": level.upper(),
                },
            },
            "loggers": {
                "": {
                    "handlers": ["standard"],
                    "level": "DEBUG",
                }
            },
        }

        # If a filename is passed in, let's add a FileHandler
        if filename:
            config["handlers"].update(
                {
                    "file_output": {
                        "class": "logging.FileHandler",
                        "formatter": "debug",
                        "level": "DEBUG",
                        "filename": filename,
                    }
                }
            )
            config["loggers"][""]["handlers"].append("file_output")

    # Configure the logging
    logging.config.dictConfig(config)

    # Initialize root logger and advise logging has been initialized
    log = logging.getLogger(APP)
    log.debug("Logging initialized.")
>>>>>>> 2122990 (Cookie initially baked targeting develop by NetworkToCode Cookie Drift Manager Tool)
