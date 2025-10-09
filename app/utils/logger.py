"""
Logging setup with loguru
Writes logs to both console and files with rotation
"""

import sys
from pathlib import Path
from loguru import logger

from app.config import settings


def setup_logger():
    """Set up loguru for the whole app"""

    # remove default handler
    logger.remove()

    # === Console output ===
    # pretty colors and timestamps
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.log_level,
        colorize=True,
    )

    # === File output ===
    # create logs folder if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # write to files with daily rotation
    logger.add(
        "logs/bridge_bot_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # new file every day at midnight
        retention="30 days",  # keep logs for 30 days
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        compression="zip",  # compress old logs
    )

    # separate file for errors so they're easier to find
    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="90 days",  # keep errors longer
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    return logger


# initialize logger when module is imported
logger = setup_logger()