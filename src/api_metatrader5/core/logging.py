from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings


def configure_logging(settings: Settings) -> None:
    logger = logging.getLogger("api_metatrader5")
    logger.setLevel(getattr(logging, settings.app_log_level.upper(), logging.INFO))
    logger.propagate = False
    if logger.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if settings.app_log_file:
        log_path = Path(settings.app_log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=settings.app_log_max_bytes,
            backupCount=settings.app_log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
