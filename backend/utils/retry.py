"""
CVM Analyzer - Retry Utilities
============================

Provides retry logic with exponential backoff for downloads and API calls.
"""

import time
import asyncio
import logging
from typing import TypeVar, Callable, Optional, Union, Type, Tuple
from functools import wraps
import httpx


T = TypeVar('T')


class RetryError(Exception):
    """Raised when all retry attempts fail."""
    
    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


def retry_sync(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger: Optional[logging.Logger] = None
):
    """
    Decorator for synchronous retry with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exception types to catch
        logger: Logger for retry messages
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        # Calculate delay with exponential backoff
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        
                        if logger:
                            logger.warning(
                                f"Attempt {attempt + 1}/{max_retries} failed for "
                                f"{func.__name__}: {e}. Retrying in {delay:.1f}s..."
                            )
                        
                        time.sleep(delay)
                    else:
                        if logger:
                            logger.error(
                                f"All {max_retries} attempts failed for {func.__name__}: {e}"
                            )
            
            raise RetryError(
                f"All {max_retries} attempts failed for {func.__name__}",
                last_exception
            )
        
        return wrapper
    return decorator


def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger: Optional[logging.Logger] = None
):
    """
    Decorator for async retry with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exception types to catch
        logger: Logger for retry messages
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        
                        if logger:
                            logger.warning(
                                f"Attempt {attempt + 1}/{max_retries} failed for "
                                f"{func.__name__}: {e}. Retrying in {delay:.1f}s..."
                            )
                        
                        await asyncio.sleep(delay)
                    else:
                        if logger:
                            logger.error(
                                f"All {max_retries} attempts failed for {func.__name__}: {e}"
                            )
            
            raise RetryError(
                f"All {max_retries} attempts failed for {func.__name__}",
                last_exception
            )
        
        return wrapper
    return decorator


async def download_with_retry(
    url: str,
    timeout: int = 180,
    max_retries: int = 3,
    logger: Optional[logging.Logger] = None
) -> bytes:
    """
    Download content from URL with retry and exponential backoff.
    
    Args:
        url: URL to download
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        logger: Logger instance
        
    Returns:
        Downloaded content as bytes
        
    Raises:
        RetryError: If all retries fail
    """
    last_exception = None
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                if logger:
                    logger.debug(f"Downloading (attempt {attempt + 1}): {url}")
                
                response = await client.get(url)
                response.raise_for_status()
                
                if logger:
                    logger.info(f"Downloaded {len(response.content)} bytes from {url}")
                
                return response.content
                
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
                last_exception = e
                
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # 1s, 2s, 4s
                    
                    if logger:
                        logger.warning(
                            f"Download attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                    
                    await asyncio.sleep(delay)
                else:
                    if logger:
                        logger.error(f"All download attempts failed for {url}: {e}")
    
    raise RetryError(
        f"Failed to download {url} after {max_retries} attempts",
        last_exception
    )


def download_with_retry_sync(
    url: str,
    timeout: int = 180,
    max_retries: int = 3,
    logger: Optional[logging.Logger] = None
) -> bytes:
    """
    Synchronous version of download_with_retry.
    
    Args:
        url: URL to download
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        logger: Logger instance
        
    Returns:
        Downloaded content as bytes
    """
    last_exception = None
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                if logger:
                    logger.debug(f"Downloading (attempt {attempt + 1}): {url}")
                
                response = client.get(url)
                response.raise_for_status()
                
                if logger:
                    logger.info(f"Downloaded {len(response.content)} bytes from {url}")
                
                return response.content
                
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
                last_exception = e
                
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    
                    if logger:
                        logger.warning(
                            f"Download attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                    
                    time.sleep(delay)
                else:
                    if logger:
                        logger.error(f"All download attempts failed for {url}: {e}")
    
    raise RetryError(
        f"Failed to download {url} after {max_retries} attempts",
        last_exception
    )
