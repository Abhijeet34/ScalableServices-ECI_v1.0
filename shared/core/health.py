"""
Implements health checks as per:
- RFC Draft: Health Check Response Format for HTTP APIs
- Kubernetes health probe standards
- AWS ELB health check requirements
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from typing import Dict, Any, Optional
import os
import time
import redis
from datetime import datetime
from enum import Enum
import psutil
import asyncio
import logging

logger = logging.getLogger(__name__)

class HealthStatus(str, Enum):
    """Health status values following industry standards"""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"

class ServiceHealth:
    """
    Service health management following best practices from:
    - Google SRE principles
    - AWS health check patterns
    - Netflix Hystrix circuit breaker patterns
    """
    
    def __init__(self, service_name: str, version: str = "1.0.0"):
        self.service_name = service_name
        self.version = version
        self.start_time = time.time()
        self.checks_performed = 0
        self.last_check_time = None
        
    def create_health_router(self) -> APIRouter:
        """Create health check router with industry-standard endpoints"""
        router = APIRouter(tags=["health"])
        
        @router.get("/health", status_code=status.HTTP_200_OK)
        async def health_check() -> Dict[str, Any]:
            """
            Basic liveness probe - lightweight check
            Used by Kubernetes liveness probe and load balancers
            """
            return {
                "status": HealthStatus.PASS,
                "service": self.service_name,
                "version": self.version,
                "releaseId": os.getenv("RELEASE_ID", "unknown"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        @router.get("/health/live", status_code=status.HTTP_200_OK)
        async def liveness() -> Dict[str, Any]:
            """Kubernetes liveness probe endpoint"""
            return {"status": "alive"}
        
        @router.get("/health/ready")
        async def readiness() -> JSONResponse:
            """
            Readiness probe - comprehensive health check
            Checks all dependencies and returns detailed status
            """
            checks = await self._perform_readiness_checks()
            
            # Determine overall status
            overall_status = self._calculate_overall_status(checks)
            status_code = status.HTTP_200_OK if overall_status == HealthStatus.PASS else status.HTTP_503_SERVICE_UNAVAILABLE
            
            response = {
                "status": overall_status,
                "version": self.version,
                "releaseId": os.getenv("RELEASE_ID", "unknown"),
                "notes": [],
                "output": "",
                "checks": checks,
                "links": {},
                "serviceId": self.service_name,
                "description": f"{self.service_name} microservice",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            return JSONResponse(status_code=status_code, content=response)
        
        @router.get("/health/startup")
        async def startup() -> Dict[str, Any]:
            """
            Kubernetes startup probe endpoint
            Used during initial container startup
            """
            checks = await self._perform_startup_checks()
            status_val = self._calculate_overall_status(checks)
            
            if status_val != HealthStatus.PASS:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "starting", "checks": checks}
                )
            
            return {"status": "started", "checks": checks}
        
        @router.get("/metrics")
        async def metrics() -> Dict[str, Any]:
            """
            Prometheus-compatible metrics endpoint
            Following OpenMetrics specification
            """
            memory = psutil.Process().memory_info()
            cpu_percent = psutil.Process().cpu_percent()
            
            return {
                "service": self.service_name,
                "version": self.version,
                "uptime_seconds": time.time() - self.start_time,
                "checks_performed": self.checks_performed,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "system": {
                    "memory_rss_bytes": memory.rss,
                    "memory_vms_bytes": memory.vms,
                    "cpu_percent": cpu_percent,
                    "num_threads": psutil.Process().num_threads()
                }
            }
        
        return router
    
    async def _perform_readiness_checks(self) -> Dict[str, Dict[str, Any]]:
        """Perform comprehensive readiness checks"""
        self.checks_performed += 1
        self.last_check_time = time.time()
        
        checks = {}
        
        # Database check
        checks["database:connectivity"] = await self._check_database()
        
        # Redis check (if configured)
        if os.getenv("REDIS_URL"):
            checks["cache:connectivity"] = await self._check_redis()
        
        # Disk space check
        checks["storage:disk_space"] = self._check_disk_space()
        
        # Memory check
        checks["system:memory"] = self._check_memory()
        
        return checks
    
    async def _perform_startup_checks(self) -> Dict[str, Dict[str, Any]]:
        """Perform startup-specific checks"""
        checks = {}
        
        # Check database migrations
        checks["database:migrations"] = await self._check_migrations()
        
        # Check required environment variables
        checks["config:environment"] = self._check_environment()
        
        return checks
    
    async def _check_database(self) -> Dict[str, Any]:
        """Check database connectivity with timeout"""
        try:
            start_time = time.time()
            db_url = self._get_database_url()
            
            engine = create_engine(db_url, pool_pre_ping=True)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            response_time = (time.time() - start_time) * 1000
            
            return {
                "status": HealthStatus.PASS,
                "componentType": "datastore",
                "observedValue": f"{response_time:.2f}ms",
                "observedUnit": "ms",
                "time": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": HealthStatus.FAIL,
                "componentType": "datastore",
                "output": str(e),
                "time": datetime.utcnow().isoformat() + "Z"
            }
    
    async def _check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity"""
        try:
            start_time = time.time()
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            
            r = redis.from_url(redis_url, socket_connect_timeout=1)
            r.ping()
            
            response_time = (time.time() - start_time) * 1000
            
            return {
                "status": HealthStatus.PASS,
                "componentType": "cache",
                "observedValue": f"{response_time:.2f}ms",
                "observedUnit": "ms",
                "time": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            # Redis failure is usually not critical
            return {
                "status": HealthStatus.WARN,
                "componentType": "cache",
                "output": str(e),
                "time": datetime.utcnow().isoformat() + "Z"
            }
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """Check available disk space"""
        try:
            disk = psutil.disk_usage('/')
            free_gb = disk.free / (1024 ** 3)
            
            if free_gb < 1:
                status_val = HealthStatus.FAIL
            elif free_gb < 5:
                status_val = HealthStatus.WARN
            else:
                status_val = HealthStatus.PASS
            
            return {
                "status": status_val,
                "componentType": "system",
                "observedValue": f"{free_gb:.2f}",
                "observedUnit": "GB",
                "time": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            return {
                "status": HealthStatus.WARN,
                "componentType": "system",
                "output": str(e),
                "time": datetime.utcnow().isoformat() + "Z"
            }
    
    def _check_memory(self) -> Dict[str, Any]:
        """Check available memory"""
        try:
            memory = psutil.virtual_memory()
            available_mb = memory.available / (1024 ** 2)
            
            if available_mb < 100:
                status_val = HealthStatus.FAIL
            elif available_mb < 500:
                status_val = HealthStatus.WARN
            else:
                status_val = HealthStatus.PASS
            
            return {
                "status": status_val,
                "componentType": "system",
                "observedValue": f"{available_mb:.2f}",
                "observedUnit": "MB",
                "time": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            return {
                "status": HealthStatus.WARN,
                "componentType": "system",
                "output": str(e),
                "time": datetime.utcnow().isoformat() + "Z"
            }
    
    async def _check_migrations(self) -> Dict[str, Any]:
        """Check if database migrations are up to date"""
        try:
            db_url = self._get_database_url()
            engine = create_engine(db_url)
            
            with engine.connect() as conn:
                # Check if alembic_version table exists
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'alembic_version'
                    )
                """))
                exists = result.scalar()
                
                if exists:
                    return {
                        "status": HealthStatus.PASS,
                        "componentType": "datastore",
                        "time": datetime.utcnow().isoformat() + "Z"
                    }
                else:
                    return {
                        "status": HealthStatus.WARN,
                        "componentType": "datastore",
                        "output": "Migrations table not found",
                        "time": datetime.utcnow().isoformat() + "Z"
                    }
        except Exception as e:
            return {
                "status": HealthStatus.FAIL,
                "componentType": "datastore",
                "output": str(e),
                "time": datetime.utcnow().isoformat() + "Z"
            }
    
    def _check_environment(self) -> Dict[str, Any]:
        """Check required environment variables"""
        required_vars = [
            "POSTGRES_HOST",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD"
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            return {
                "status": HealthStatus.FAIL,
                "componentType": "configuration",
                "output": f"Missing environment variables: {', '.join(missing)}",
                "time": datetime.utcnow().isoformat() + "Z"
            }
        
        return {
            "status": HealthStatus.PASS,
            "componentType": "configuration",
            "time": datetime.utcnow().isoformat() + "Z"
        }
    
    def _get_database_url(self) -> str:
        """Get database URL from environment"""
        return (
            f"postgresql+psycopg2://"
            f"{os.getenv('POSTGRES_USER', 'eci')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'eci')}@"
            f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'eci')}"
        )
    
    def _calculate_overall_status(self, checks: Dict[str, Dict[str, Any]]) -> HealthStatus:
        """Calculate overall health status based on individual checks"""
        if not checks:
            return HealthStatus.PASS
        
        statuses = [check.get("status", HealthStatus.PASS) for check in checks.values()]
        
        if HealthStatus.FAIL in statuses:
            return HealthStatus.FAIL
        elif HealthStatus.WARN in statuses:
            return HealthStatus.WARN
        else:
            return HealthStatus.PASS