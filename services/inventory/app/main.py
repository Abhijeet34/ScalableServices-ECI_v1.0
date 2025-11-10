"""
Inventory Microservice
Industry-standard implementation with comprehensive monitoring and logging
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import subprocess
import os
import sys
import logging

# Add shared modules to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from shared.core import ServiceHealth, setup_logging, RequestLoggingMiddleware, get_logger
from app.api.routes import router as inventory_router
from app.infrastructure.db import init_models

# Service configuration
SERVICE_NAME = "inventory-service"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
SERVICE_DESCRIPTION = "Inventory management microservice"

# Setup structured logging
setup_logging(
    service_name=SERVICE_NAME,
    level=os.getenv("LOG_LEVEL", "INFO")
)

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info(f"Starting {SERVICE_NAME} version {SERVICE_VERSION}")
    
    # Startup
    try:
        # Run database migrations
        logger.info("Running database migrations")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            logger.warning(f"Migration output: {result.stderr}")
        else:
            logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Migration error: {e}")
    
    # Initialize database models
    try:
        init_models()
        logger.info("Database models initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database models: {e}")
        raise
    
    logger.info(f"{SERVICE_NAME} started successfully")
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {SERVICE_NAME}")

# Create FastAPI application
app = FastAPI(
    title=SERVICE_NAME,
    description=SERVICE_DESCRIPTION,
    version=SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Initialize health checks
health_service = ServiceHealth(SERVICE_NAME, SERVICE_VERSION)
health_router = health_service.create_health_router()
app.include_router(health_router)

# Include business logic routes
app.include_router(inventory_router)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "running",
        "docs": "/api/docs"
    }

@app.get("/info")
async def info():
    """Service information endpoint"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "description": SERVICE_DESCRIPTION,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "endpoints": {
            "health": "/health",
            "ready": "/health/ready",
            "live": "/health/live",
            "metrics": "/metrics",
            "docs": "/api/docs"
        }
    }
