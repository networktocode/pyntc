"""
Logging utilities for Versa
===========================

This module contains helpers and wrappers for making logging more consistent
across applications.
How to use me:

    >>> from . import log
    >>> log.init()
    2020-07-21 10:35:40,860 [INFO] bluecat: Logging initialized.
    >>> log.info("NTC")
    2020-07-21 10:39:40,463 [INFO] bluecat: NTC

"""
import os
import logging


APP = "versa"
""" Application name, used as the logging root. """

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
""" Logging format to use. """

DEBUG_FORMAT = (
    "%(asctime)s [%(levelname)s] [%(module)s] [%(funcName)s] %(name)s: %(message)s"
)
""" Logging format used when debug output is enabled. """


def get_log(name=None):
    """Return a logger instance in the :data:`APP` namespace.

    If *name* is supplied, it will be appended to the default name.

    Args:
        name (str): Sublogger name

    """
    name = f"{APP}.{name}" if name else APP
    return logging.getLogger(name)


def init(**kwargs):
    """Initialize logging using sensible defaults.

    If keyword arguments are passed to this function, they will be passed
    directly to the :func:`logging.basicConfig` call in turn.

    Args:
        **kwargs: Arguments to pass to logging configuration

    """
    debug = os.environ.get("DEBUG", None)
    log_format = DEBUG_FORMAT if debug else FORMAT

    log_level = getattr(logging, os.environ.get("LOG_LEVEL", "info").upper())
    log_level = logging.DEBUG if debug else log_level

    kwargs.setdefault("format", log_format)
    kwargs.setdefault("level", log_level)

    logging.basicConfig(**kwargs)
    info("Logging initialized.")


def logger(level):
    """Thin wrapper around app logger methods."""
    return getattr(get_log(), level)


critical = logger("critical")
error = logger("error")
warning = logger("warning")
info = logger("info")
debug = logger("debug")
exception = logger("exception")
