import logging
import os
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO", log_dir: str = None):
    log_dir = log_dir or os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "obs_multichat.log")

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler (human-readable)
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    ch.setFormatter(fmt)

    # File handler (JSON structured)
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setLevel(getattr(logging, level.upper(), logging.INFO))
    json_formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    fh.setFormatter(json_formatter)

    # Avoid adding duplicate handlers when setup_logging is called multiple times
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == fh.baseFilename for h in logger.handlers if hasattr(h, 'baseFilename')):
        logger.addHandler(fh)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(ch)

    logger.debug(f"Logging initialized. File: {log_file}")
    return logger
