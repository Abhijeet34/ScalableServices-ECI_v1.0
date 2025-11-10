"""Shared core utilities for microservices.

Provides common health check and logging functionality across all services.
"""

from .health import ServiceHealth, HealthStatus
from .logging_config import (
    setup_logging,
    get_logger,
    RequestLoggingMiddleware,
    set_request_context,
    generate_request_id,
    LoggerAdapter,
)

__all__ = [
    # Health checks
    "ServiceHealth",
    "HealthStatus",
    # Logging
    "setup_logging",
    "get_logger",
    "RequestLoggingMiddleware",
    "set_request_context",
    "generate_request_id",
    "LoggerAdapter",
]
