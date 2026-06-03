"""
CaseHub - Resilience Utilities
Retry decorators and circuit breaker for external service calls.

Usage:
    from core.resilience import retry_external, CircuitBreaker

    @retry_external(max_retries=3)
    async def call_notion_api():
        ...

    stripe_breaker = CircuitBreaker("stripe", failure_threshold=5)
    with stripe_breaker:
        stripe.Customer.create(...)
"""
import asyncio
import functools
import logging
import time
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def retry_external(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    service_name: str = "",
):
    """
    Decorator for retrying external service calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds (doubles each retry)
        max_delay: Maximum delay cap
        exceptions: Tuple of exception types to retry on
        service_name: Name for logging (auto-detected from function if empty)
    """

    def decorator(func):
        name = service_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            "External call %s failed (attempt %d/%d): %s. Retrying in %.1fs",
                            name, attempt + 1, max_retries + 1, str(e)[:200], delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "External call %s failed after %d attempts: %s",
                            name, max_retries + 1, str(e)[:200],
                        )
            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            "External call %s failed (attempt %d/%d): %s. Retrying in %.1fs",
                            name, attempt + 1, max_retries + 1, str(e)[:200], delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "External call %s failed after %d attempts: %s",
                            name, max_retries + 1, str(e)[:200],
                        )
            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class CircuitBreaker:
    """
    Simple circuit breaker for external services.

    States:
        CLOSED: Normal operation, requests pass through
        OPEN: Service is down, requests fail fast without calling the service
        HALF_OPEN: Testing if service recovered (allows one request through)

    Usage:
        breaker = CircuitBreaker("stripe", failure_threshold=5, reset_timeout=60)

        if breaker.allow_request():
            try:
                result = call_stripe()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            raise ServiceUnavailableError("Stripe circuit is open")
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if self._last_failure_time and (
                    time.time() - self._last_failure_time > self.reset_timeout
                ):
                    self._state = self.HALF_OPEN
                    logger.info("Circuit breaker %s: OPEN -> HALF_OPEN", self.service_name)
            return self._state

    def allow_request(self) -> bool:
        current_state = self.state
        if current_state == self.CLOSED:
            return True
        if current_state == self.HALF_OPEN:
            return True
        return False

    def record_success(self):
        with self._lock:
            if self._state == self.HALF_OPEN:
                logger.info("Circuit breaker %s: HALF_OPEN -> CLOSED", self.service_name)
            self._state = self.CLOSED
            self._failure_count = 0

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                if self._state != self.OPEN:
                    logger.error(
                        "Circuit breaker %s: OPEN after %d failures",
                        self.service_name, self._failure_count,
                    )
                self._state = self.OPEN

    def reset(self):
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0
            self._last_failure_time = None


# Pre-configured circuit breakers for known services
stripe_breaker = CircuitBreaker("stripe", failure_threshold=5, reset_timeout=60)
notion_breaker = CircuitBreaker("notion", failure_threshold=3, reset_timeout=120)
google_breaker = CircuitBreaker("google", failure_threshold=5, reset_timeout=90)
moskit_breaker = CircuitBreaker("moskit", failure_threshold=3, reset_timeout=60)
