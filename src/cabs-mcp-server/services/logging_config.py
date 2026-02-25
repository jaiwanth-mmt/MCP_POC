"""
Centralized logging configuration for MCP Cab Booking System.

This module provides a consistent logging setup across all services with:
- Structured log formatting
- Context-aware logging
- Performance tracking
- Easy debugging capabilities
"""

import logging
import sys
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color coding for different log levels."""
    
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
    }
    RESET = '\033[0m'
    
    ICONS = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️ ',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '🔥',
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        icon = self.ICONS.get(record.levelname, '  ')
        
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S.%f')[:-3]
        module_info = f"{record.module}.{record.funcName}"
        
        formatted = (
            f"{color}{icon} {timestamp}{self.RESET} "
            f"{color}[{record.levelname:8}]{self.RESET} "
            f"[{module_info:30}] "
            f"{record.getMessage()}"
        )
        
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


class StructuredLogger(logging.LoggerAdapter):
    
    def process(self, msg, kwargs):
        extra = kwargs.get('extra', {})
        if extra:
            context_str = " | ".join(f"{k}={v}" for k, v in extra.items())
            msg = f"{msg} [{context_str}]"
        return msg, kwargs


def setup_logging(level: str = "INFO", use_colors: bool = True, use_stderr: bool = True) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    stream = sys.stderr if use_stderr else sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setLevel(numeric_level)
    
    if use_colors:
        formatter = ColoredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] [%(name)s.%(funcName)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


def get_logger(name: str, **context) -> StructuredLogger:
    base_logger = logging.getLogger(name)
    return StructuredLogger(base_logger, context)


def log_async_function_call(func):
    import functools
    import time
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"→ Entering {func.__name__}({signature})")
        
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"← Exiting {func.__name__} (took {elapsed:.2f}ms)")
            return result
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(
                f"✗ Exception in {func.__name__} after {elapsed:.2f}ms: {type(e).__name__}: {e}"
            )
            raise
    
    return wrapper


setup_logging(use_stderr=True)
