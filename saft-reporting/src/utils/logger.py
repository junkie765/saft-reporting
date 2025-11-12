"""Logging configuration"""
import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from colorlog import ColoredFormatter

try:
    from colorlog import ColoredFormatter
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False
    ColoredFormatter = None  # type: ignore


def setup_logger(level: str = 'INFO'):
    """Setup console logger with optional color support"""
    
    # Create formatter
    if HAS_COLORLOG and ColoredFormatter is not None:
        formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s - %(levelname)-8s%(reset)s - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            reset=True,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)-8s - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(console_handler)
    
    # Suppress verbose libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('simple_salesforce').setLevel(logging.WARNING)
