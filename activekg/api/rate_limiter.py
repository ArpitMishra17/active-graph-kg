"""Redis-backed rate limiter for Active Graph KG.

Implements fixed-window (per-second bucket) rate limiting per tenant/IP with concurrency caps.

Architecture:
    - Fixed 1-second window buckets (not true sliding window)
    - Burst limit enforced within each second
    - Keys expire after 1 second (TTL)
    - Concurrency tracking via sorted sets

Note:
    Window-boundary bursts can "double spend" across consecutive seconds.
    Upgrade to true sliding window if stricter enforcement needed.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from prometheus_client import Counter

from activekg.common.logger import get_enhanced_logger

logger = get_enhanced_logger(__name__)

# Prometheus metrics
api_rate_limited_total = Counter(
    "api_rate_limited_total",
    "Total number of rate-limited requests (HTTP 429)",
    ["endpoint", "reason"],
)

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Proxy/IP trust configuration
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"
REAL_IP_HEADER = os.getenv("REAL_IP_HEADER", "X-Forwarded-For")  # or X-Real-IP


def _get_limit(name: str, default_rate: int, default_burst: int) -> dict:
    rate_env = os.getenv(f"RATE_LIMIT_{name.upper()}_RATE")
    burst_env = os.getenv(f"RATE_LIMIT_{name.upper()}_BURST")
    try:
        rate = int(rate_env) if rate_env is not None else default_rate
    except Exception:
        rate = default_rate
    try:
        burst = int(burst_env) if burst_env is not None else default_burst
    except Exception:
        burst = default_burst
    return {"rate": rate, "burst": burst}


# Per-endpoint limits (requests per second, burst) with env overrides
RATE_LIMITS = {
    "search": _get_limit("search", 50, 100),  # /search
    "ask": _get_limit("ask", 3, 5),  # /ask
    "ask_stream": _get_limit("ask_stream", 1, 3),  # /ask/stream
    "admin_refresh": _get_limit("admin_refresh", 1, 2),  # /admin/refresh
    "webhook_s3": _get_limit(
        "webhook_s3", 100, 200
    ),  # /_webhooks/s3 (high burst for notifications)
    "webhook_gcs": _get_limit(
        "webhook_gcs", 100, 200
    ),  # /_webhooks/gcs (high burst for notifications)
    "default": _get_limit("default", 100, 200),  # Other endpoints
}


# Concurrency limits (max in-flight requests per tenant) with env overrides
def _get_concurrency(name: str, default_value: int) -> int:
    v = os.getenv(f"CONCURRENCY_{name.upper()}")
    try:
        return int(v) if v is not None else default_value
    except Exception:
        return default_value


CONCURRENCY_LIMITS = {
    "ask": _get_concurrency("ask", 3),
    "ask_stream": _get_concurrency("ask_stream", 2),
}


@dataclass
class RateLimitInfo:
    """Rate limit status information."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int | None = None  # Seconds


class RateLimiter:
    """Redis-backed sliding window rate limiter.

    Uses token bucket algorithm with Redis INCR/EXPIRE for simplicity and atomicity.
    """

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis = None
        self.enabled = RATE_LIMIT_ENABLED

        if self.enabled:
            try:
                import redis

                self._redis = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self._redis.ping()
                logger.info("Rate limiter enabled", extra_fields={"redis_url": redis_url})
            except ImportError:
                logger.warning(
                    "Redis not installed, rate limiting disabled. Install: pip install redis"
                )
                self.enabled = False
            except Exception as e:
                logger.warning(f"Failed to connect to Redis, rate limiting disabled: {e}")
                self.enabled = False

    def _get_key(self, identifier: str, endpoint: str, window: str = "second") -> str:
        """Generate Redis key for rate limit bucket.

        Args:
            identifier: tenant_id or IP address
            endpoint: Endpoint name (e.g., "ask", "search")
            window: Time window ("second", "minute", "hour", "day")

        Returns:
            Redis key string
        """
        return f"ratelimit:{endpoint}:{identifier}:{window}:{int(time.time())}"

    def check_limit(
        self,
        identifier: str,
        endpoint: str,
        custom_limit: int | None = None,
        custom_burst: int | None = None,
    ) -> RateLimitInfo:
        """Check if request is within rate limit.

        Args:
            identifier: tenant_id or IP address
            endpoint: Endpoint name
            custom_limit: Override default rate limit (req/s)
            custom_burst: Override default burst limit

        Returns:
            RateLimitInfo with allowed status and headers
        """
        # Disabled mode: always allow
        if not self.enabled or not self._redis:
            return RateLimitInfo(
                allowed=True, limit=9999, remaining=9999, reset_at=int(time.time()) + 60
            )

        # Get limits for this endpoint
        limits = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
        rate = custom_limit or limits["rate"]
        burst = custom_burst or limits["burst"]

        # Sliding window key (per second)
        now = int(time.time())
        key = f"ratelimit:{endpoint}:{identifier}:{now}"

        try:
            # Atomic increment + expire
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 1)  # 1 second TTL
            results = pipe.execute()
            current = results[0]

            # Check burst limit
            if current > burst:
                retry_after = 1  # Retry after 1 second
                return RateLimitInfo(
                    allowed=False,
                    limit=burst,
                    remaining=0,
                    reset_at=now + 1,
                    retry_after=retry_after,
                )

            # Check rate limit (average over last second)
            remaining = max(0, burst - current)
            return RateLimitInfo(allowed=True, limit=burst, remaining=remaining, reset_at=now + 1)

        except Exception as e:
            logger.error(f"Rate limiter error: {e}, allowing request")
            # Fail open: allow request if Redis is down
            return RateLimitInfo(allowed=True, limit=rate, remaining=rate, reset_at=now + 60)

    def check_concurrency(self, identifier: str, endpoint: str) -> bool:
        """Check if concurrent request limit is exceeded.

        Uses Redis sorted sets to track in-flight requests.

        Args:
            identifier: tenant_id or IP address
            endpoint: Endpoint name

        Returns:
            True if allowed, False if concurrency limit exceeded

        Note:
            Relies on explicit mark_request_end() calls in finally blocks.
            Stale entries cleaned up via key TTL (120s) if finally blocks don't run.
        """
        if not self.enabled or not self._redis:
            return True

        limit = CONCURRENCY_LIMITS.get(endpoint)
        if not limit:
            return True  # No concurrency limit for this endpoint

        key = f"concurrency:{endpoint}:{identifier}"
        now = time.time()

        try:
            # Remove expired entries (older than 10 minutes)
            # High threshold to avoid dropping long-running requests (streams, slow LLM calls)
            # Explicit mark_request_end() in finally blocks is primary cleanup mechanism
            self._redis.zremrangebyscore(key, 0, now - 600)

            # Count current in-flight requests
            current = self._redis.zcard(key)

            if current >= limit:
                return False

            return True

        except Exception as e:
            logger.error(f"Concurrency check error: {e}, allowing request")
            return True  # Fail open

    def mark_request_start(self, identifier: str, endpoint: str, request_id: str):
        """Mark request as in-flight for concurrency tracking."""
        if not self.enabled or not self._redis:
            return

        limit = CONCURRENCY_LIMITS.get(endpoint)
        if not limit:
            return

        key = f"concurrency:{endpoint}:{identifier}"
        now = time.time()

        try:
            self._redis.zadd(key, {request_id: now})
            self._redis.expire(key, 120)  # 2 minute TTL
        except Exception as e:
            logger.error(f"Failed to mark request start: {e}")

    def mark_request_end(self, identifier: str, endpoint: str, request_id: str):
        """Mark request as complete for concurrency tracking."""
        if not self.enabled or not self._redis:
            return

        limit = CONCURRENCY_LIMITS.get(endpoint)
        if not limit:
            return

        key = f"concurrency:{endpoint}:{identifier}"

        try:
            self._redis.zrem(key, request_id)
        except Exception as e:
            logger.error(f"Failed to mark request end: {e}")


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_identifier(request: Request, tenant_id: str | None = None) -> str:
    """Get rate limit identifier (tenant_id or IP).

    Args:
        request: FastAPI request
        tenant_id: Tenant ID from JWT (preferred)

    Returns:
        Identifier string for rate limiting

    Security:
        Only trusts proxy headers (X-Forwarded-For, X-Real-IP) if TRUST_PROXY=true.
        Without TRUST_PROXY, uses direct client IP to prevent spoofing.
    """
    if tenant_id:
        return f"tenant:{tenant_id}"

    # Fallback to IP address
    # Only trust proxy headers if explicitly configured
    if TRUST_PROXY:
        real_ip = request.headers.get(REAL_IP_HEADER)
        if real_ip:
            # For X-Forwarded-For, use leftmost (original client) IP
            return f"ip:{real_ip.split(',')[0].strip()}"

    # Direct client IP (when no proxy or TRUST_PROXY=false)
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


async def rate_limit_dependency(
    request: Request, endpoint: str, tenant_id: str | None = None
) -> None:
    """FastAPI dependency for rate limiting.

    Usage:
        @app.post("/ask")
        async def ask(
            request: AskRequest,
            _: None = Depends(lambda req: rate_limit_dependency(req, "ask", req.tenant_id))
        ):
            ...

    Raises:
        HTTPException 429 if rate limit exceeded
    """
    if not rate_limiter.enabled:
        return

    identifier = get_identifier(request, tenant_id)

    # Check rate limit
    limit_info = rate_limiter.check_limit(identifier, endpoint)

    # Set rate limit headers (even if allowed)
    request.state.rate_limit_info = limit_info

    if not limit_info.allowed:
        # Increment Prometheus metric
        api_rate_limited_total.labels(endpoint=endpoint, reason="rate_limit").inc()

        logger.warning(
            "Rate limit exceeded",
            extra_fields={
                "identifier": identifier,
                "endpoint": endpoint,
                "limit": limit_info.limit,
                "retry_after": limit_info.retry_after,
            },
        )

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit_info.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(limit_info.reset_at),
                "Retry-After": str(limit_info.retry_after) if limit_info.retry_after else "1",
            },
        )

    # Check concurrency limit
    if not rate_limiter.check_concurrency(identifier, endpoint):
        # Increment Prometheus metric
        api_rate_limited_total.labels(endpoint=endpoint, reason="concurrency").inc()

        logger.warning(
            "Concurrency limit exceeded",
            extra_fields={
                "identifier": identifier,
                "endpoint": endpoint,
                "limit": CONCURRENCY_LIMITS.get(endpoint),
            },
        )

        raise HTTPException(
            status_code=429, detail="Too many concurrent requests", headers={"Retry-After": "5"}
        )
