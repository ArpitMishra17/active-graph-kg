"""
CORS middleware with environment-based configuration.
Only enables CORS when explicitly configured via environment variables.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app: FastAPI) -> None:
    """
    Add CORS middleware if CORS_ENABLED=true.

    Environment variables:
    - CORS_ENABLED: Set to 'true' to enable CORS (default: false)
    - CORS_ORIGINS: Comma-separated list of allowed origins (default: http://localhost:5173)
    - CORS_CREDENTIALS: Allow credentials (default: true)

    Example:
        export CORS_ENABLED=true
        export CORS_ORIGINS="http://localhost:5173,http://localhost:3000"
    """
    cors_enabled = os.getenv("CORS_ENABLED", "false").lower() == "true"

    if not cors_enabled:
        return

    # Parse origins from environment (default to Vite dev server)
    origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    allowed_origins = [origin.strip() for origin in origins_str.split(",")]

    # Allow credentials (needed for JWT in cookies)
    allow_credentials = os.getenv("CORS_CREDENTIALS", "true").lower() == "true"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
    )

    print(f"CORS enabled for origins: {allowed_origins}")
