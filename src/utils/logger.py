"""Logging configuration"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from colorlog import ColoredFormatter

try:
    from colorlog import ColoredFormatter
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False
    ColoredFormatter = None  # type: ignore


def setup_logger(level: str = 'INFO', log_dir: str = 'logs', use_console: bool = False):
    """Setup console and file logger with optional color support"""
    
    # Create log directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create log filename with timestamp
    log_filename = f"saft_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = log_path / log_filename
    
    # Create formatters
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)-8s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if HAS_COLORLOG and ColoredFormatter is not None:
        console_formatter = ColoredFormatter(
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
        console_formatter = file_formatter
    
    # Setup file handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(file_handler)
    
    # Setup console handler (only if requested)
    if use_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Suppress verbose libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('simple_salesforce').setLevel(logging.WARNING)
    
    # Log the file location
    root_logger.info(f"Log file: {log_file.absolute()}")
