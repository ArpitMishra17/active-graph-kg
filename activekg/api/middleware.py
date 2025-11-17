"""FastAPI middleware helpers for JWT + rate limiting integration.

Provides clean wrappers for adding auth and rate limiting to endpoints.
"""

from __future__ import annotations

import inspect
import os
import uuid
from collections.abc import Callable
from functools import wraps

from fastapi import Depends, HTTPException, Request, Response

from activekg.api.auth import JWT_ENABLED, JWTClaims, get_jwt_claims
from activekg.api.rate_limiter import RATE_LIMIT_ENABLED, get_identifier, rate_limiter
from activekg.common.logger import get_enhanced_logger
from activekg.observability.metrics import access_violations_total

logger = get_enhanced_logger(__name__)


async def apply_rate_limit(
    request: Request,
    response: Response,
    endpoint: str,
    tenant_id: str | None = None,
    check_concurrency: bool = False,
) -> str | None:
    """Apply rate limiting to a request.

    Args:
        request: FastAPI request
        response: FastAPI response (for headers)
        endpoint: Endpoint key (e.g., "ask", "search")
        tenant_id: Optional tenant ID from JWT
        check_concurrency: Whether to check concurrency limits

    Returns:
        Request ID (if concurrency tracking enabled), else None

    Raises:
        HTTPException 429 if rate limit exceeded
    """
    if not RATE_LIMIT_ENABLED:
        return None

    identifier = get_identifier(request, tenant_id)

    # Check rate limit
    limit_info = rate_limiter.check_limit(identifier, endpoint)

    # Add rate limit headers (even if allowed)
    response.headers["X-RateLimit-Limit"] = str(limit_info.limit)
    response.headers["X-RateLimit-Remaining"] = str(limit_info.remaining)
    response.headers["X-RateLimit-Reset"] = str(limit_info.reset_at)

    if not limit_info.allowed:
        logger.warning(
            "Rate limit exceeded",
            extra_fields={
                "identifier": identifier,
                "endpoint": endpoint,
                "limit": limit_info.limit,
            },
        )

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please retry after the specified interval.",
            headers={
                "Retry-After": str(limit_info.retry_after) if limit_info.retry_after else "1",
                "X-RateLimit-Limit": str(limit_info.limit),
                "X-RateLimit-Remaining": str(limit_info.remaining),
                "X-RateLimit-Reset": str(limit_info.reset_at),
            },
        )

    # Check concurrency limit (if requested)
    request_id = None
    if check_concurrency:
        if not rate_limiter.check_concurrency(identifier, endpoint):
            logger.warning(
                "Concurrency limit exceeded",
                extra_fields={"identifier": identifier, "endpoint": endpoint},
            )

            raise HTTPException(
                status_code=429,
                detail="Too many concurrent requests. Please retry after completing existing requests.",
                headers={
                    "Retry-After": "5",
                    "X-RateLimit-Limit": str(limit_info.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(limit_info.reset_at),
                },
            )

        # Mark request as in-flight
        request_id = f"{identifier}:{uuid.uuid4().hex}"
        rate_limiter.mark_request_start(identifier, endpoint, request_id)

    return request_id


def get_tenant_context(
    request: Request, claims: JWTClaims | None = None, allow_override: bool = False
) -> tuple[str | None, str | None, str | None]:
    """Extract tenant context from JWT or request.

    Args:
        request: FastAPI request
        claims: JWT claims (if authenticated)
        allow_override: If True, allow user-supplied tenant_id when JWT disabled

    Returns:
        Tuple of (tenant_id, actor_id, actor_type)

    Security notes:
    - When JWT_ENABLED=true, ALWAYS use claims.tenant_id (trusted)
    - When JWT_ENABLED=false AND allow_override=true, allow request body tenant_id
    - When JWT_ENABLED=false AND allow_override=false, use None (public access)
    """
    if JWT_ENABLED and claims:
        # JWT enabled: use trusted claims
        # Detect cross-tenant attempts via query param (best-effort; body parsing would consume stream)
        try:
            q_tid = request.query_params.get("tenant_id") if request else None
            if q_tid and q_tid != claims.tenant_id:
                access_violations_total.labels(type="cross_tenant_query").inc()
        except Exception:
            pass
        return (claims.tenant_id, claims.actor_id, claims.actor_type)

    # Dev mode: use env-driven tenant (defaults to 'default')
    # Prevents hardcoding and allows test isolation
    dev_tenant = os.getenv("ACTIVEKG_DEV_TENANT", "default")
    return (dev_tenant, "dev_user", "user")


class RateLimitedEndpoint:
    """Decorator for rate-limited endpoints with concurrency control.

    Usage:
        @app.post("/ask")
        @RateLimitedEndpoint("ask", check_concurrency=True)
        async def ask(request: AskRequest, ctx: dict = Depends(...)):
            tenant_id = ctx["tenant_id"]
            request_id = ctx["request_id"]
            ...
    """

    def __init__(self, endpoint: str, check_concurrency: bool = False):
        self.endpoint = endpoint
        self.check_concurrency = check_concurrency

    def __call__(self, func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request, response, claims from kwargs
            request = kwargs.get("request")
            response = kwargs.get("response")
            claims = kwargs.get("claims")

            if not request:
                raise ValueError("RateLimitedEndpoint requires 'request' in kwargs")

            tenant_id = claims.tenant_id if claims else None

            # Apply rate limiting
            request_id = await apply_rate_limit(
                request, response or Response(), self.endpoint, tenant_id, self.check_concurrency
            )

            # Store context for endpoint use
            kwargs["rate_limit_ctx"] = {
                "request_id": request_id,
                "tenant_id": tenant_id,
                "endpoint": self.endpoint,
            }

            try:
                return await func(*args, **kwargs)
            finally:
                # Mark request as complete (for concurrency tracking)
                if request_id and tenant_id:
                    identifier = get_identifier(request, tenant_id)
                    rate_limiter.mark_request_end(identifier, self.endpoint, request_id)

        return wrapper


def with_rate_limit(endpoint: str, check_concurrency: bool = False):
    """Decorator to apply rate limiting to both sync and async endpoints.

    - For async endpoints, delegates to apply_rate_limit and optionally concurrency caps
    - For sync endpoints, sets X-RateLimit headers using rate_limiter.check_limit()

    Expects the wrapped endpoint to accept Request/Response via kwargs as
    `http_request`/`request` and `http_response`/`response`.
    """

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                req = kwargs.get("http_request") or kwargs.get("request")
                resp = kwargs.get("http_response") or kwargs.get("response") or Response()
                claims = kwargs.get("claims")
                tenant_id = claims.tenant_id if (JWT_ENABLED and claims) else None

                request_id = None
                if RATE_LIMIT_ENABLED and req is not None and resp is not None:
                    request_id = await apply_rate_limit(
                        req,
                        resp,
                        endpoint=endpoint,
                        tenant_id=tenant_id,
                        check_concurrency=check_concurrency,
                    )
                try:
                    return await func(*args, **kwargs)
                finally:
                    if request_id and tenant_id:
                        identifier = get_identifier(req, tenant_id)
                        rate_limiter.mark_request_end(identifier, endpoint, request_id)

            return async_wrapper

        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                req = kwargs.get("http_request") or kwargs.get("request")
                resp = kwargs.get("http_response") or kwargs.get("response") or Response()
                claims = kwargs.get("claims")
                tenant_id = claims.tenant_id if (JWT_ENABLED and claims) else None

                if RATE_LIMIT_ENABLED and req is not None and resp is not None:
                    identifier = get_identifier(req, tenant_id)
                    info = rate_limiter.check_limit(identifier, endpoint=endpoint)
                    resp.headers["X-RateLimit-Limit"] = str(info.limit)
                    resp.headers["X-RateLimit-Remaining"] = str(info.remaining)
                    resp.headers["X-RateLimit-Reset"] = str(info.reset_at)
                    if not info.allowed:
                        raise HTTPException(
                            status_code=429,
                            detail="Rate limit exceeded",
                            headers={"Retry-After": str(info.retry_after or 1)},
                        )

                return func(*args, **kwargs)

            return sync_wrapper

    return decorator


def require_rate_limit(endpoint: str, check_concurrency: bool = False):
    """FastAPI dependency to apply rate limiting without altering endpoint signatures.

    Notes:
    - Designed for endpoints with body parameters (POST/DELETE), where decorators can
      interfere with FastAPI's parameter inspection.
    - Does not track concurrency end; use apply_rate_limit directly in async endpoints
      that require concurrency caps.
    """

    async def dep(
        request: Request, response: Response, claims: JWTClaims | None = Depends(get_jwt_claims)
    ) -> None:
        if not RATE_LIMIT_ENABLED:
            return
        tenant_id, _, _ = get_tenant_context(request, claims, allow_override=not JWT_ENABLED)
        identifier = get_identifier(request, tenant_id)
        info = rate_limiter.check_limit(identifier, endpoint=endpoint)
        response.headers["X-RateLimit-Limit"] = str(info.limit)
        response.headers["X-RateLimit-Remaining"] = str(info.remaining)
        response.headers["X-RateLimit-Reset"] = str(info.reset_at)
        if not info.allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(info.retry_after or 1)},
            )

    return dep
