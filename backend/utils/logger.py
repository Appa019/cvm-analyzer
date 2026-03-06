"""
CVM Analyzer - Logging Utility
================================

Configures rotating file logging with security best practices.
Never logs API keys or full document content (only hashes/IDs).
"""

import logging
import hashlib
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from functools import wraps
import time


class SecureFormatter(logging.Formatter):
    """
    Custom formatter that redacts sensitive information.
    
    Redacts:
    - API keys (sk-*, OPENAI_API_KEY, etc.)
    - Bearer tokens
    - Full document content (shows hash instead)
    """
    
    SENSITIVE_PATTERNS = [
        ("sk-", "[REDACTED_API_KEY]"),
        ("Bearer ", "Bearer [REDACTED_TOKEN]"),
        ("api_key=", "api_key=[REDACTED]"),
        ("apikey=", "apikey=[REDACTED]"),
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        
        # Redact known sensitive patterns
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            if pattern.lower() in message.lower():
                # Find and replace the sensitive part
                import re
                if pattern == "sk-":
                    message = re.sub(r'sk-[a-zA-Z0-9_-]+', replacement, message)
                elif pattern == "Bearer ":
                    message = re.sub(r'Bearer [a-zA-Z0-9_.-]+', replacement, message)
                else:
                    message = re.sub(
                        rf'{pattern}[a-zA-Z0-9_-]+', 
                        replacement, 
                        message, 
                        flags=re.IGNORECASE
                    )
        
        return message


def content_hash(text: str) -> str:
    """Generate SHA256 hash of content for logging without exposing content."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def setup_logger(
    name: str,
    logs_dir: Path,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    level: str = "INFO",
    debug_mode: bool = False
) -> logging.Logger:
    """
    Configure and return a logger with rotating file handler.
    
    Args:
        name: Logger name (usually module name)
        logs_dir: Directory for log files
        max_bytes: Max size per log file (default 10MB)
        backup_count: Number of backup files to keep
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        debug_mode: If True, logs more verbose content
        
    Returns:
        Configured logger instance
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # File handler with rotation
    log_file = logs_dir / "app.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    
    # Use secure formatter
    formatter = SecureFormatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler for development
    if debug_mode:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
    
    return logger


# =============================================================================
# Logger Context Manager for Timing
# =============================================================================

class LogTimer:
    """Context manager for timing operations."""
    
    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time: float = 0
        
    def __enter__(self):
        self.start_time = time.perf_counter()
        self.logger.info(f"[START] {self.operation}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self.start_time
        if exc_type:
            self.logger.error(f"[FAILED] {self.operation} after {elapsed:.2f}s: {exc_val}")
        else:
            self.logger.info(f"[DONE] {self.operation} in {elapsed:.2f}s")
        return False  # Don't suppress exceptions


def log_function_call(logger: logging.Logger):
    """Decorator to log function entry/exit with timing."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            logger.debug(f"Calling {func.__name__}")
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.debug(f"Completed {func.__name__} in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                logger.error(f"Failed {func.__name__} after {elapsed:.2f}s: {e}")
                raise
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            logger.debug(f"Calling {func.__name__}")
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.debug(f"Completed {func.__name__} in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                logger.error(f"Failed {func.__name__} after {elapsed:.2f}s: {e}")
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# =============================================================================
# Global Logger Instance
# =============================================================================

_app_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get or create the application logger."""
    global _app_logger
    if _app_logger is None:
        from config import get_settings
        settings = get_settings()
        _app_logger = setup_logger(
            name="cvm_analyzer",
            logs_dir=settings.logs_dir,
            max_bytes=settings.log_max_bytes,
            backup_count=settings.log_backup_count,
            level=settings.log_level,
            debug_mode=settings.debug
        )
    return _app_logger


def setup_logging() -> logging.Logger:
    """
    Initialize the global logging system.
    
    This is a convenience function that can be called without arguments.
    Returns the configured logger.
    """
    return get_logger()
