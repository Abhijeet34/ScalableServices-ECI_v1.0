"""
Structured logging configuration
Implements patterns from:
- Google Cloud Logging standards
- AWS CloudWatch structured logging
- Datadog APM logging guidelines
"""

import logging
import sys
import json
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)

class StructuredFormatter(logging.Formatter):
    """
    JSON structured logging formatter following industry standards
    Compatible with:
    - ELK Stack (Elasticsearch, Logstash, Kibana)
    - CloudWatch Insights
    - Datadog Log Management
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""

        # Build base log structure
        log_obj = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._get_service_name(),
            "environment": self._get_environment(),
            "version": self._get_version(),
        }

        # Add trace context if available
        trace_context = self._get_trace_context()
        if trace_context:
            log_obj["trace"] = trace_context

        # Add location information
        log_obj["location"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
            "module": record.module
        }

        # Add exception information if present
        if record.exc_info:
            log_obj["error"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "stacktrace": traceback.format_exception(*record.exc_info)
            }

        # Add custom fields from extra
        if hasattr(record, 'extra_fields'):
            log_obj["custom"] = record.extra_fields

        # Add performance metrics if available
        if hasattr(record, 'duration_ms'):
            log_obj["performance"] = {
                "duration_ms": record.duration_ms
            }

        return json.dumps(log_obj, default=str)

    def _get_service_name(self) -> str:
        """Get service name from environment or default"""
        import os
        return os.getenv('SERVICE_NAME', 'unknown-service')

    def _get_environment(self) -> str:
        """Get environment (dev/staging/prod)"""
        import os
        return os.getenv('ENVIRONMENT', 'development')

    def _get_version(self) -> str:
        """Get service version"""
        import os
        return os.getenv('SERVICE_VERSION', '1.0.0')

    def _get_trace_context(self) -> Optional[Dict[str, Any]]:
        """Get distributed tracing context"""
        request_id = request_id_var.get()
        correlation_id = correlation_id_var.get()
        user_id = user_id_var.get()

        if not any([request_id, correlation_id, user_id]):
            return None

        context = {}
        if request_id:
            context["request_id"] = request_id
        if correlation_id:
            context["correlation_id"] = correlation_id
        if user_id:
            context["user_id"] = user_id

        return context

class PerformanceFilter(logging.Filter):
    """Filter to add performance metrics to log records"""

    def filter(self, record: logging.LogRecord) -> bool:
        # Add performance context if available
        if hasattr(record, 'duration'):
            record.duration_ms = record.duration * 1000
        return True

class SecurityFilter(logging.Filter):
    """Filter to redact sensitive information from logs"""

    SENSITIVE_FIELDS = [
        'password', 'token', 'api_key', 'secret',
        'authorization', 'cookie', 'session'
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact sensitive information from message
        message = record.getMessage()
        for field in self.SENSITIVE_FIELDS:
            if field in message.lower():
                # Simple redaction - in production use more sophisticated methods
                record.msg = record.msg.replace(field, f"{field}=***REDACTED***")

        return True

def setup_logging(
    service_name: str,
    level: str = "INFO",
    enable_console: bool = True,
    enable_file: bool = False,
    log_file: str = None
) -> None:
    """
    Setup structured logging for a microservice

    Args:
        service_name: Name of the microservice
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Enable console output
        enable_file: Enable file output
        log_file: Path to log file
    """
    import os

    # Set service name in environment
    os.environ['SERVICE_NAME'] = service_name

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers = []

    # Create formatter
    formatter = StructuredFormatter()

    # Add console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(PerformanceFilter())
        console_handler.addFilter(SecurityFilter())
        root_logger.addHandler(console_handler)

    # Add file handler
    if enable_file and log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10485760,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(PerformanceFilter())
        file_handler.addFilter(SecurityFilter())
        root_logger.addHandler(file_handler)

    # Configure third-party loggers
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

    # Log startup
    root_logger.info(
        "Logging initialized",
        extra={
            'extra_fields': {
                'service': service_name,
                'level': level,
                'handlers': {
                    'console': enable_console,
                    'file': enable_file
                }
            }
        }
    )

class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter to inject request context into all log messages
    Used for distributed tracing
    """

    def process(self, msg, kwargs):
        # Add trace context to extra fields
        extra = kwargs.get('extra', {})

        request_id = request_id_var.get()
        if request_id:
            extra['request_id'] = request_id

        correlation_id = correlation_id_var.get()
        if correlation_id:
            extra['correlation_id'] = correlation_id

        user_id = user_id_var.get()
        if user_id:
            extra['user_id'] = user_id

        kwargs['extra'] = extra
        return msg, kwargs

def get_logger(name: str) -> LoggerAdapter:
    """
    Get a logger instance with request context support

    Args:
        name: Logger name (usually __name__)

    Returns:
        LoggerAdapter with context injection
    """
    base_logger = logging.getLogger(name)
    return LoggerAdapter(base_logger, {})

def set_request_context(
    request_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> None:
    """
    Set request context for distributed tracing

    Args:
        request_id: Unique request identifier
        correlation_id: Correlation ID for distributed tracing
        user_id: User identifier
    """
    if request_id:
        request_id_var.set(request_id)
    if correlation_id:
        correlation_id_var.set(correlation_id)
    if user_id:
        user_id_var.set(user_id)

def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())

# Middleware for FastAPI

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all requests and responses
    Adds request ID and tracks request duration
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get('X-Request-ID', generate_request_id())
        correlation_id = request.headers.get('X-Correlation-ID')

        # Set context
        set_request_context(
            request_id=request_id,
            correlation_id=correlation_id
        )

        # Log request
        logger = get_logger(__name__)
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                'extra_fields': {
                    'method': request.method,
                    'path': request.url.path,
                    'client_host': request.client.host if request.client else None
                }
            }
        )

        # Process request
        import time
        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Log response
            logger.info(
                f"Request completed: {request.method} {request.url.path}",
                extra={
                    'extra_fields': {
                        'method': request.method,
                        'path': request.url.path,
                        'status_code': response.status_code,
                        'duration_ms': duration * 1000
                    }
                }
            )

            # Add request ID to response headers
            response.headers['X-Request-ID'] = request_id

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                exc_info=True,
                extra={
                    'extra_fields': {
                        'method': request.method,
                        'path': request.url.path,
                        'duration_ms': duration * 1000
                    }
                }
            )
            raise
