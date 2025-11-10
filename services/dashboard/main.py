"""Monitoring Dashboard with User Roles for ECI Platform"""
import asyncio
import os
import secrets
import json
import time
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum
from io import StringIO
import csv
import logging

import httpx
import jwt
try:
    import bcrypt  # optional; used if passwords are provided as bcrypt hashes
except Exception:
    bcrypt = None
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status, Query, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse as StarletteStreamingResponse
from sqlalchemy import create_engine, text

app = FastAPI(title="ECI Monitoring Dashboard")

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "eci")
POSTGRES_USER = os.getenv("POSTGRES_USER", "eci")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "eci")

# Database engine (will be initialized with retry logic)
engine = None

def wait_for_database(max_retries=30, retry_delay=2):
    """Wait for database to be ready with exponential backoff"""
    global engine
    
    db_url = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Attempting to connect to database (attempt {attempt}/{max_retries})...")
            test_engine = create_engine(db_url, pool_pre_ping=True)
            
            # Test the connection
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            # If successful, set the global engine
            engine = test_engine
            logger.info("✓ Database connection established successfully")
            return True
            
        except Exception as e:
            if attempt < max_retries:
                wait_time = min(retry_delay * attempt, 30)  # Cap at 30 seconds
                logger.warning(f"Database not ready: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"✗ Failed to connect to database after {max_retries} attempts: {e}")
                raise
    
    return False

@app.on_event("startup")
async def startup_event():
    """Run migrations and setup on application startup"""
    logger.info("Starting ECI Dashboard...")
    
    # Wait for database to be ready
    try:
        wait_for_database()
    except Exception as e:
        logger.error(f"✗ Cannot start dashboard: Database unavailable - {e}")
        raise
    
    # Run migrations
    try:
        logger.info("Running database migrations...")
        with engine.begin() as conn:
            # Check if activity_logs table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'activity_logs'
                );
            """))
            table_exists = result.scalar()
            
            if not table_exists:
                logger.info("Creating activity_logs table...")
                
                # Create table
                conn.execute(text("""
                    CREATE TABLE activity_logs (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        event_type VARCHAR(50) NOT NULL,
                        entity_type VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(100),
                        user_id VARCHAR(100),
                        description TEXT,
                        metadata JSONB,
                        ip_address INET,
                        user_agent TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                
                # Create indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp DESC);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_event_type ON activity_logs(event_type);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_type ON activity_logs(entity_type);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_id ON activity_logs(entity_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs(user_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_metadata ON activity_logs USING gin(metadata);"))
                
                # Create view
                conn.execute(text("""
                    CREATE OR REPLACE VIEW recent_activity AS
                    SELECT * FROM activity_logs
                    WHERE timestamp >= NOW() - INTERVAL '7 days'
                    ORDER BY timestamp DESC;
                """))
                
                # Transaction will be committed automatically on exit
                logger.info("✓ activity_logs table created successfully")
            else:
                logger.info("✓ activity_logs table already exists")
        
        logger.info("✓ Database migrations completed")
    except Exception as e:
        logger.error(f"✗ Failed to run migrations: {e}")
        logger.warning("Dashboard will continue but logs feature may not work")

# Security
security = HTTPBasic()

# User roles
class UserRole(str, Enum):
    ADMIN = "admin"
    GUEST = "guest"

# User database (configurable via env; defaults for dev)
DEFAULT_USERS = {
    "admin": {"password": "admin123", "role": UserRole.ADMIN, "name": "Administrator"},
    "guest": {"password": "guest123", "role": UserRole.GUEST, "name": "Guest User"},
}

DASHBOARD_USERS_JSON = os.getenv("DASHBOARD_USERS_JSON", "").strip()
DASHBOARD_USERS_FILE = os.getenv("DASHBOARD_USERS_FILE", "").strip()

def _load_users() -> Dict:
    data = None
    if DASHBOARD_USERS_FILE:
        try:
            with open(DASHBOARD_USERS_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = None
    if data is None and DASHBOARD_USERS_JSON:
        try:
            data = json.loads(DASHBOARD_USERS_JSON)
        except Exception:
            data = None
    return data if isinstance(data, dict) else DEFAULT_USERS

USERS = _load_users()

# Store active websocket connections with user info
active_connections: Dict[WebSocket, Dict] = {}

# Configuration for service monitoring (env-driven with safe defaults)
DEFAULT_SERVICES = {
    "customers": "http://customers:8000",
    "products": "http://products:8000",
    "inventory": "http://inventory:8000",
    "orders": "http://orders:8000",
    "payments": "http://payments:8000",
    "shipments": "http://shipments:8000",
    "gateway": "http://gateway:8000",
}

def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default

# Build services map from JSON or individual envs, fallback to defaults
SERVICES_JSON = os.getenv("DASHBOARD_SERVICES_JSON", "").strip()
if SERVICES_JSON:
    try:
        SERVICES = json.loads(SERVICES_JSON)
    except Exception:
        SERVICES = DEFAULT_SERVICES.copy()
else:
    SERVICES = {
        "customers": os.getenv("CUSTOMERS_SERVICE_URL", DEFAULT_SERVICES["customers"]),
        "products": os.getenv("PRODUCTS_SERVICE_URL", DEFAULT_SERVICES["products"]),
        "inventory": os.getenv("INVENTORY_SERVICE_URL", DEFAULT_SERVICES["inventory"]),
        "orders": os.getenv("ORDERS_SERVICE_URL", DEFAULT_SERVICES["orders"]),
        "payments": os.getenv("PAYMENTS_SERVICE_URL", DEFAULT_SERVICES["payments"]),
        "shipments": os.getenv("SHIPMENTS_SERVICE_URL", DEFAULT_SERVICES["shipments"]),
        "gateway": os.getenv("GATEWAY_SERVICE_URL", DEFAULT_SERVICES["gateway"]),
    }

HTTP_TIMEOUT_SEC = _float_env("DASHBOARD_HTTP_TIMEOUT_SEC", 3.0)
POLL_INTERVAL_SEC = max(0.5, _float_env("DASHBOARD_POLL_INTERVAL_SEC", 2.0))
BACKOFF_FACTOR = _float_env("DASHBOARD_BACKOFF_FACTOR", 2.0)
BACKOFF_MAX_SEC = max(POLL_INTERVAL_SEC, _float_env("DASHBOARD_BACKOFF_MAX_SEC", 30.0))
BACKOFF_JITTER_MS = int(_float_env("DASHBOARD_BACKOFF_JITTER_MS", 250.0))

# Per-service backoff state
SERVICE_STATE: Dict[str, Dict] = {
    name: {
        "last_status": None,
        "last_response_time_ms": None,
        "last_version": None,
        "last_releaseId": None,
        "backoff_sec": POLL_INTERVAL_SEC,
        "next_check_at": 0.0,
    }
    for name in SERVICES.keys()
}

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

def authenticate_user(credentials: HTTPBasicCredentials) -> Dict:
    """Authenticate user and return user info (supports bcrypt hashes)."""
    user = USERS.get(credentials.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    stored_pw = str(user.get("password", ""))
    provided = credentials.password or ""
    ok = False
    # bcrypt hash detection
    if stored_pw.startswith("$2a$") or stored_pw.startswith("$2b$") or stored_pw.startswith("$2y$"):
        if bcrypt is None:
            # bcrypt not available; deny
            ok = False
        else:
            try:
                ok = bcrypt.checkpw(provided.encode("utf-8"), stored_pw.encode("utf-8"))
            except Exception:
                ok = False
    else:
        ok = secrets.compare_digest(provided, stored_pw)

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return {
        "username": credentials.username,
        "role": user["role"],
        "name": user.get("name", credentials.username)
    }

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> Dict:
    """Get current authenticated user"""
    return authenticate_user(credentials)

def create_jwt_token(username: str, role: str) -> str:
    """Create JWT token for API gateway"""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def fetch_metrics(user_role: str = UserRole.GUEST) -> Dict:
    """Fetch metrics from all services based on user role"""
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
        "totals": {
            "orders_placed_total": 0,
            "payments_failed_total": 0,
            "inventory_reserve_latency_ms": 0,
            "stockouts_total": 0,
        }
    }

    # Query database directly for totals
    try:
        with engine.connect() as conn:
            # Get total orders
            result = conn.execute(text("SELECT COUNT(*) FROM orders"))
            metrics["totals"]["orders_placed_total"] = result.scalar() or 0
            
            # Get failed payments
            result = conn.execute(text("SELECT COUNT(*) FROM payments WHERE status = 'FAILED'"))
            metrics["totals"]["payments_failed_total"] = result.scalar() or 0
            
            # Get stockouts (inventory with on_hand <= 0)
            result = conn.execute(text("SELECT COUNT(*) FROM inventory WHERE on_hand <= 0"))
            metrics["totals"]["stockouts_total"] = result.scalar() or 0
    except Exception as e:
        print(f"Error fetching database metrics: {e}")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        now = time.monotonic()
        # Check each service with per-service backoff
        for service, url in SERVICES.items():
            state = SERVICE_STATE.setdefault(service, {
                "last_status": None,
                "last_response_time_ms": None,
                "last_version": None,
                "last_releaseId": None,
                "backoff_sec": POLL_INTERVAL_SEC,
                "next_check_at": 0.0,
            })

            # Skip if backoff window not elapsed; reuse last known state
            if now < state["next_check_at"]:
                metrics["services"][service] = {
                    "status": state["last_status"] or "unknown",
                    "response_time_ms": state["last_response_time_ms"],
                    "version": state.get("last_version"),
                    "releaseId": state.get("last_releaseId"),
                }
                continue

            try:
                # Check health endpoint consistently for all services (including gateway)
                health_endpoint = "/health"
                health_resp = await client.get(f"{url}{health_endpoint}")
                status_ok = (health_resp.status_code == 200)
                resp_ms = int(health_resp.elapsed.total_seconds() * 1000)
                version_val = None
                try:
                    data_json = health_resp.json()
                    if isinstance(data_json, dict):
                        version_val = data_json.get("version")
                        release_id = data_json.get("releaseId")
                    else:
                        release_id = None
                except Exception:
                    version_val = None
                    release_id = None
                metrics["services"][service] = {
                    "status": "healthy" if status_ok else "unhealthy",
                    "response_time_ms": resp_ms,
                    "version": version_val,
                    "releaseId": release_id,
                }
                # Update state: reset backoff on healthy, mild delay on unhealthy
                if status_ok:
                    state["backoff_sec"] = POLL_INTERVAL_SEC
                else:
                    state["backoff_sec"] = min(BACKOFF_MAX_SEC, max(POLL_INTERVAL_SEC, state["backoff_sec"] * BACKOFF_FACTOR))
                jitter = (random.randint(-BACKOFF_JITTER_MS, BACKOFF_JITTER_MS) / 1000.0)
                state["next_check_at"] = now + max(0.5, state["backoff_sec"] + jitter)
                state["last_status"] = metrics["services"][service]["status"]
                state["last_response_time_ms"] = resp_ms
                state["last_version"] = version_val
                state["last_releaseId"] = release_id

            except httpx.ConnectError:
                state["backoff_sec"] = min(BACKOFF_MAX_SEC, max(POLL_INTERVAL_SEC, state["backoff_sec"] * BACKOFF_FACTOR))
                jitter = (random.randint(-BACKOFF_JITTER_MS, BACKOFF_JITTER_MS) / 1000.0)
                state["next_check_at"] = now + max(0.5, state["backoff_sec"] + jitter)
                metrics["services"][service] = {
                    "status": "error",
                    "error": "Connection failed",
                }
                state["last_status"] = "error"
                state["last_response_time_ms"] = None
                state["last_version"] = None
                state["last_releaseId"] = None
            except httpx.TimeoutException:
                state["backoff_sec"] = min(BACKOFF_MAX_SEC, max(POLL_INTERVAL_SEC, state["backoff_sec"] * BACKOFF_FACTOR))
                jitter = (random.randint(-BACKOFF_JITTER_MS, BACKOFF_JITTER_MS) / 1000.0)
                state["next_check_at"] = now + max(0.5, state["backoff_sec"] + jitter)
                metrics["services"][service] = {
                    "status": "error",
                    "error": "Timeout",
                }
                state["last_status"] = "error"
                state["last_response_time_ms"] = None
                state["last_version"] = None
            except Exception as e:
                state["backoff_sec"] = min(BACKOFF_MAX_SEC, max(POLL_INTERVAL_SEC, state["backoff_sec"] * BACKOFF_FACTOR))
                jitter = (random.randint(-BACKOFF_JITTER_MS, BACKOFF_JITTER_MS) / 1000.0)
                state["next_check_at"] = now + max(0.5, state["backoff_sec"] + jitter)
                metrics["services"][service] = {
                    "status": "error",
                    "error": str(e)[:50],
                }
                state["last_status"] = "error"
                state["last_response_time_ms"] = None
                state["last_version"] = None

    return metrics

@app.post("/api/create_order")
async def create_order(user: Dict = Depends(get_current_user)):
    """Create a new order (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Create a real order through the orders service
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Create order via orders service
            order_data = {
                "customer_id": 1,  # Default test customer
                "items": [
                    {
                        "product_id": 1,
                        "sku": "PROD-001",
                        "quantity": 1,
                        "unit_price": 29.99
                    }
                ]
            }
            
            response = await client.post(
                f"{SERVICES['orders']}/orders/",
                json=order_data
            )
            
            if response.status_code in [200, 201]:
                order = response.json()
                return {
                    "success": True,
                    "message": "Order created successfully",
                    "order_id": order.get("id", "unknown")
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to create order: {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error creating order: {str(e)}"
            }

@app.get("/api/test_services")
async def test_services(user: Dict = Depends(get_current_user)):
    """Test all services health"""
    healthy_count = 0
    total_count = len(SERVICES)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        for service, url in SERVICES.items():
            try:
                resp = await client.get(f"{url}/health")
                if resp.status_code == 200:
                    healthy_count += 1
            except Exception:
                # Ignore connectivity errors during test sweep
                pass

    return {
        "healthy": healthy_count,
        "total": total_count,
        "message": f"Health Check: {healthy_count}/{total_count} services healthy"
    }

@app.post("/api/reset_metrics")
async def reset_metrics(user: Dict = Depends(get_current_user)):
    """Reset metrics (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    # In a real system, this would reset counters in monitoring system
    return {"success": True, "message": "Metrics reset successfully"}

@app.get("/api/user_info")
async def user_info(user: Dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "username": user["username"],
        "role": user["role"],
        "name": user["name"]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()

    # Get user credentials from query params or headers
    user_role = UserRole.GUEST  # Default to guest
    active_connections[websocket] = {"role": user_role}

    try:
        while True:
            # Send metrics every 2 seconds
            metrics = await fetch_metrics(user_role)
            await websocket.send_json(metrics)
            await asyncio.sleep(POLL_INTERVAL_SEC)
    except WebSocketDisconnect:
        del active_connections[websocket]

@app.websocket("/ws/logs")
async def logs_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live activity log streaming"""
    await websocket.accept()
    
    # Track last sent log ID to avoid duplicates
    last_log_id = 0
    
    try:
        while True:
            # Fetch new logs since last check
            try:
                with engine.connect() as conn:
                    result = conn.execute(
                        text("""
                            SELECT id, timestamp, event_type, entity_type, entity_id, 
                                   user_id, description, metadata
                            FROM activity_logs 
                            WHERE id > :last_id
                            ORDER BY id ASC
                            LIMIT 50
                        """),
                        {"last_id": last_log_id}
                    )
                    
                    new_logs = []
                    for row in result:
                        new_logs.append({
                            "id": row.id,
                            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                            "event_type": row.event_type,
                            "entity_type": row.entity_type,
                            "entity_id": row.entity_id,
                            "user_id": row.user_id,
                            "description": row.description,
                            "metadata": json.loads(row.metadata) if row.metadata else None
                        })
                        last_log_id = max(last_log_id, row.id)
                    
                    # Send new logs if any
                    if new_logs:
                        await websocket.send_json({
                            "type": "logs",
                            "data": new_logs,
                            "count": len(new_logs)
                        })
            except Exception as e:
                print(f"Error fetching logs for WebSocket: {e}")
            
            # Wait before next poll
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print("Logs WebSocket disconnected")

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "dashboard"}

# API endpoints for dashboard operations
@app.get("/api/customers")
async def get_customers(user: Dict = Depends(get_current_user)):
    """Get all customers from database"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM customers ORDER BY id DESC"))
            customers = []
            for row in result:
                customers.append({
                    "id": row.id,
                    "name": row.name,
                    "email": row.email,
                    "phone": row.phone,
                    "address_street": row.address_street,
                    "address_city": row.address_city,
                    "address_state": row.address_state,
                    "address_zip": row.address_zip,
                    "address_country": row.address_country
                })
            return customers
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return []

@app.post("/api/customers")
async def create_customer(customer_data: dict, user: Dict = Depends(get_current_user)):
    """Create new customer (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(f"{SERVICES['customers']}/customers/", json=customer_data)
            if response.status_code == 201:
                add_activity("CREATE", "customer", str(response.json().get('id')), user['username'])
                return {"success": True, "data": response.json()}
            
            # Log detailed error
            error_detail = f"HTTP {response.status_code}"
            try:
                error_body = response.json()
                error_detail = f"HTTP {response.status_code}: {error_body}"
                print(f"Customer creation failed: {error_detail}")
            except Exception:
                print(f"Customer creation failed: HTTP {response.status_code} - {response.text}")
                error_detail = f"HTTP {response.status_code}: {response.text}"
            
            return {"success": False, "error": error_detail}
        except Exception as e:
            print(f"Customer creation exception: {str(e)}")
            return {"success": False, "error": str(e)}

@app.get("/api/products")
async def get_products(user: Dict = Depends(get_current_user)):
    """Get all products with inventory data from database"""
    try:
        with engine.connect() as conn:
            # Fetch products with inventory
            result = conn.execute(text("""
                SELECT p.*, 
                       COALESCE(i.on_hand, 0) - COALESCE(i.reserved, 0) as stock_quantity
                FROM products p
                LEFT JOIN inventory i ON p.id = i.product_id
                ORDER BY p.id DESC
            """))
            
            products = []
            for row in result:
                products.append({
                    "id": row.id,
                    "name": row.name,
                    "sku": row.sku,
                    "price": float(row.price) if row.price else 0.0,
                    "description": row.description,
                    "category": row.category,
                    "image_url": "",  # No image_url column in database
                    "seller_name": row.seller_name,
                    "seller_location": row.seller_location,
                    "seller_member_since": str(row.seller_member_since) if row.seller_member_since else None,
                    "seller_response_time": row.seller_response_time,
                    "seller_shipping_policy": row.seller_shipping_policy,
                    "seller_return_policy": row.seller_return_policy,
                    "seller_badge": row.seller_badge,
                    "stock_quantity": max(0, int(row.stock_quantity)) if row.stock_quantity else 0
                })
            return products
    except Exception as e:
        print(f"Error fetching products: {e}")
        return []

@app.post("/api/products")
async def create_product(product_data: dict, user: Dict = Depends(get_current_user)):
    """Create new product with inventory (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Extract stock_quantity before sending to products service
            stock_quantity = product_data.pop('stock_quantity', 0)
            
            # Create product
            response = await client.post(f"{SERVICES['products']}/products/", json=product_data)
            if response.status_code == 201:
                product = response.json()
                product_id = product.get('id')
                
                # Create inventory entry if stock_quantity provided
                if stock_quantity and product_id:
                    inventory_data = {
                        "product_id": product_id,
                        "warehouse": "MAIN",
                        "on_hand": int(stock_quantity),
                        "reserved": 0
                    }
                    try:
                        inv_resp = await client.post(f"{SERVICES['inventory']}/inventory/", json=inventory_data)
                        if inv_resp.status_code != 201:
                            try:
                                error_detail = inv_resp.json()
                                print(f"Warning: Failed to create inventory for product {product_id}: {inv_resp.status_code} - {error_detail}")
                            except Exception:
                                print(f"Warning: Failed to create inventory for product {product_id}: HTTP {inv_resp.status_code}")
                    except Exception as inv_error:
                        print(f"Warning: Inventory creation failed: {inv_error}")
                
                add_activity("CREATE", "product", str(product_id), user['username'])
                return {"success": True, "data": product}
            
            # Handle error responses
            error_detail = "Unknown error"
            try:
                error_json = response.json()
                error_detail = error_json.get('detail', str(error_json))
            except Exception:
                error_detail = f"HTTP {response.status_code}"
            
            return {"success": False, "error": error_detail}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.get("/api/orders")
async def get_orders(user: Dict = Depends(get_current_user)):
    """Get all orders with enriched customer and product data"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Fetch orders
            orders_resp = await client.get(f"{SERVICES['orders']}/orders/")
            if orders_resp.status_code != 200:
                return []
            
            orders = orders_resp.json()
            
            # Fetch customers and products for enrichment
            customers_resp = await client.get(f"{SERVICES['customers']}/customers/")
            products_resp = await client.get(f"{SERVICES['products']}/products/")
            
            customers = {c['id']: c for c in customers_resp.json()} if customers_resp.status_code == 200 else {}
            products = {p['id']: p for p in products_resp.json()} if products_resp.status_code == 200 else {}
            
            # Enrich orders with customer and product details
            for order in orders:
                customer = customers.get(order['customer_id'], {})
                order['customer_name'] = customer.get('name', f"Customer #{order['customer_id']}")
                order['customer_email'] = customer.get('email', 'N/A')
                
                # Enrich order items with product details, seller info, and images
                if 'items' in order:
                    for item in order['items']:
                        product = products.get(item['product_id'], {})
                        item['product_name'] = product.get('name', f"Product #{item['product_id']}")
                        item['product_sku'] = product.get('sku', item.get('sku', 'N/A'))
                        item['product_image'] = product.get('image_url', '')
                        # Add seller information from product
                        item['seller_name'] = product.get('seller_name', '')
                        item['seller_location'] = product.get('seller_location', '')
            
            return orders
        except Exception as e:
            print(f"Error fetching orders: {e}")
            return []

@app.post("/api/orders")
async def create_order_integrated(order_data: dict, user: Dict = Depends(get_current_user)):
    """Create new order with full integration (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(f"{SERVICES['orders']}/orders/", json=order_data)
            if response.status_code == 201:
                order = response.json()
                add_activity("CREATE", "order", str(order.get('id')), user['username'], 
                           f"Created order for customer #{order_data['customer_id']}")
                return {"success": True, "data": order}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.put("/api/orders/{order_id}/status")
async def update_order_status(order_id: int, status_data: dict, user: Dict = Depends(get_current_user)):
    """Update order status (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Update the order status through orders service
            response = await client.put(
                f"{SERVICES['orders']}/orders/{order_id}",
                json=status_data
            )
            
            if response.status_code == 200:
                order_status = status_data.get('order_status')
                
                # Handle shipment based on order status
                try:
                    print(f"DEBUG: Order status changed to {order_status} for order #{order_id}")
                    # Get all shipments to check if one exists for this order
                    shipments_resp = await client.get(f"{SERVICES['shipments']}/shipments/")
                    shipments = shipments_resp.json() if shipments_resp.status_code == 200 else []
                    order_shipment = next((s for s in shipments if s['order_id'] == order_id), None)
                    print(f"DEBUG: Found existing shipment: {order_shipment is not None}")
                    
                    # If order is being marked as SHIPPED
                    if order_status == 'SHIPPED':
                        # Fetch order details to verify payment status
                        order_resp = await client.get(f"{SERVICES['orders']}/orders/{order_id}")
                        if order_resp.status_code == 200:
                            order = order_resp.json()
                            payment_status = order.get('payment_status', 'UNKNOWN')
                            
                            # Rule: Only create/update shipment if payment is COMPLETED
                            if payment_status != 'COMPLETED':
                                print(f"Warning: Cannot ship order #{order_id} - payment not completed (status: {payment_status})")
                            elif not order_shipment:
                                print(f"DEBUG: Creating shipment for order #{order_id}")
                                customer_id = order.get('customer_id')
                                
                                # Fetch customer for shipping address
                                customer_resp = await client.get(f"{SERVICES['customers']}/customers/")
                                customer = None
                                if customer_resp.status_code == 200:
                                    customers = customer_resp.json()
                                    customer = next((c for c in customers if c['id'] == customer_id), None)
                                
                                # Build shipping address
                                if customer and customer.get('address_street'):
                                    shipping_address = {
                                        "street": customer.get('address_street', ''),
                                        "city": customer.get('address_city', ''),
                                        "state": customer.get('address_state', ''),
                                        "zip_code": customer.get('address_zip', ''),
                                        "country": customer.get('address_country', 'USA')
                                    }
                                else:
                                    shipping_address = {
                                        "street": "Address Not Provided",
                                        "city": "N/A",
                                        "state": "N/A",
                                        "zip_code": "00000",
                                        "country": "USA"
                                    }
                                
                                # Create shipment with IN_TRANSIT status
                                now = datetime.utcnow()
                                shipment_data = {
                                    "order_id": order_id,
                                    "customer_id": customer_id,
                                    "items": order.get('items', []),
                                    "shipping_address": shipping_address,
                                    "status": "IN_TRANSIT",
                                    "carrier": "Standard Delivery",
                                    "tracking_no": f"TRK{order_id}{int(now.timestamp())}",
                                    "shipped_at": now.isoformat(),
                                    "delivered_at": None  # Will be set when order is marked as DELIVERED
                                }
                                
                                print(f"DEBUG: Shipment data: {shipment_data}")
                                shipment_resp = await client.post(
                                    f"{SERVICES['shipments']}/shipments/",
                                    json=shipment_data
                                )
                                
                                print(f"DEBUG: Shipment creation response: {shipment_resp.status_code}")
                                if shipment_resp.status_code != 201:
                                    print(f"DEBUG: Shipment error: {shipment_resp.text}")
                                
                                if shipment_resp.status_code == 201:
                                    shipment = shipment_resp.json()
                                    print(f"DEBUG: Shipment created successfully: {shipment.get('id')}")
                                    add_activity("CREATE", "shipment", str(shipment.get('id')), user['username'], 
                                               f"Shipment created for order #{order_id}")
                            else:
                                # Shipment exists (likely created at payment approval with PENDING): move it to IN_TRANSIT
                                print(f"DEBUG: Updating existing shipment #{order_shipment['id']} to IN_TRANSIT for order #{order_id}")
                                now = datetime.utcnow()
                                update_payload = {
                                    "status": "IN_TRANSIT"
                                }
                                # Backfill tracking/shipped_at if missing/blank
                                if not order_shipment.get('tracking_no'):
                                    update_payload["tracking_no"] = f"TRK{order_id}{int(now.timestamp())}"
                                if not order_shipment.get('carrier'):
                                    update_payload["carrier"] = "Standard Delivery"
                                if not order_shipment.get('shipped_at'):
                                    update_payload["shipped_at"] = now.isoformat()
                                
                                await client.put(
                                    f"{SERVICES['shipments']}/shipments/{order_shipment['id']}",
                                    json=update_payload
                                )
                                add_activity("UPDATE", "shipment", str(order_shipment['id']), user['username'], 
                                           f"Shipment moved to IN_TRANSIT for order #{order_id}")
                    
                    # If order is being marked as DELIVERED, update shipment to DELIVERED
                    elif order_status == 'DELIVERED' and order_shipment:
                        # Verify that the shipment was actually shipped first (IN_TRANSIT or PENDING)
                        if order_shipment.get('status') in ['IN_TRANSIT', 'PENDING']:
                            delivery_time = datetime.utcnow()
                            await client.put(
                                f"{SERVICES['shipments']}/shipments/{order_shipment['id']}",
                                json={
                                    "status": "DELIVERED",
                                    "delivered_at": delivery_time.isoformat()
                                }
                            )
                            add_activity("UPDATE", "shipment", str(order_shipment['id']), user['username'], 
                                       f"Shipment delivered for order #{order_id}")
                        else:
                            print(f"Warning: Cannot deliver shipment #{order_shipment['id']} - current status: {order_shipment.get('status')}")
                    
                    # If order is being marked as UNDELIVERED (failed delivery), update shipment to CANCELLED
                    elif order_status == 'UNDELIVERED' and order_shipment:
                        # Mark shipment as CANCELLED for undelivered orders
                        await client.put(
                            f"{SERVICES['shipments']}/shipments/{order_shipment['id']}",
                            json={"status": "CANCELLED"}
                        )
                        add_activity("UPDATE", "shipment", str(order_shipment['id']), user['username'], 
                                   f"Shipment cancelled (undelivered) for order #{order_id}")
                    
                    # If order is being cancelled, update shipment to CANCELLED
                    elif order_status == 'CANCELLED' and order_shipment:
                        await client.put(
                            f"{SERVICES['shipments']}/shipments/{order_shipment['id']}",
                            json={"status": "CANCELLED"}
                        )
                        add_activity("UPDATE", "shipment", str(order_shipment['id']), user['username'], 
                                   f"Shipment cancelled for order #{order_id}")
                        
                except Exception as shipment_error:
                    print(f"Warning: Shipment operation failed: {shipment_error}")
                
                add_activity("UPDATE", "order", str(order_id), user['username'], 
                           f"Updated order status to {order_status}")
                return {"success": True, "message": "Order status updated", "data": response.json()}
            else:
                return {"success": False, "error": f"Failed to update order: HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.post("/api/orders/{order_id}/payment")
async def process_payment(order_id: int, payment_action: dict, user: Dict = Depends(get_current_user)):
    """Process payment approval/decline (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    action = payment_action.get('action')  # 'approve' or 'decline'
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Mock payment processing
            if action == 'approve':
                payment_status = 'COMPLETED'
                order_status = 'PROCESSING'
                message = f"Payment approved for order #{order_id}"
                
                # Fetch order details to get customer and items
                order_resp = await client.get(f"{SERVICES['orders']}/orders/{order_id}")
                if order_resp.status_code == 200:
                    order = order_resp.json()
                    customer_id = order.get('customer_id')
                    
                    # Get payment and receipt IDs from request
                    payment_id = payment_action.get('payment_id')
                    receipt_id = payment_action.get('receipt_id')
                    
                    # Update order status and payment status with transaction IDs
                    update_data = {
                        "order_status": order_status,
                        "payment_status": payment_status
                    }
                    if payment_id:
                        update_data["payment_id"] = payment_id
                    if receipt_id:
                        update_data["receipt_id"] = receipt_id
                    
                    update_resp = await client.put(
                        f"{SERVICES['orders']}/orders/{order_id}",
                        json=update_data
                    )
                    
                    if update_resp.status_code != 200:
                        print(f"Warning: Failed to update order status: HTTP {update_resp.status_code}")
                    
                    # Fetch customer to get shipping address
                    customer_resp = await client.get(f"{SERVICES['customers']}/customers/")
                    customer = None
                    if customer_resp.status_code == 200:
                        customers = customer_resp.json()
                        customer = next((c for c in customers if c['id'] == customer_id), None)
                    
                    # Use customer address or fallback to default
                    if customer and customer.get('address_street'):
                        shipping_address = {
                            "street": customer.get('address_street', ''),
                            "city": customer.get('address_city', ''),
                            "state": customer.get('address_state', ''),
                            "zip_code": customer.get('address_zip', ''),
                            "country": customer.get('address_country', 'USA')
                        }
                    else:
                        # Fallback address if customer has no address on file
                        shipping_address = {
                            "street": "Address Not Provided",
                            "city": "N/A",
                            "state": "N/A",
                            "zip_code": "00000",
                            "country": "USA"
                        }
                    
                    # Create shipment for approved payment
                    shipment_data = {
                        "order_id": order_id,
                        "customer_id": customer_id,
                        "items": order.get('items', []),
                        "shipping_address": shipping_address,
                        "status": "PENDING"
                    }
                    
                    shipment_resp = await client.post(
                        f"{SERVICES['shipments']}/shipments/",
                        json=shipment_data
                    )
                    
                    if shipment_resp.status_code == 201:
                        shipment = shipment_resp.json()
                        add_activity("CREATE", "shipment", str(shipment.get('id')), user['username'], 
                                   f"Shipment created for order #{order_id}")
                        message += f" | Shipment #{shipment.get('id')} created"
            else:
                payment_status = 'FAILED'
                order_status = 'CANCELLED'
                message = f"Payment declined for order #{order_id}"
                
                # Update order status to cancelled
                update_resp = await client.put(
                    f"{SERVICES['orders']}/orders/{order_id}",
                    json={
                        "order_status": order_status,
                        "payment_status": payment_status
                    }
                )
                
                if update_resp.status_code != 200:
                    print(f"Warning: Failed to update order status: HTTP {update_resp.status_code}")
            
            add_activity("PAYMENT", "order", str(order_id), user['username'], message)
            
            return {
                "success": True,
                "message": message,
                "payment_status": payment_status,
                "order_status": order_status
            }
        except Exception as e:
            add_activity("PAYMENT", "order", str(order_id), user['username'], f"Payment error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

# DELETE operations
@app.put("/api/customers/{customer_id}")
async def update_customer(customer_id: int, customer_data: dict, user: Dict = Depends(get_current_user)):
    """Update customer (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.put(f"{SERVICES['customers']}/customers/{customer_id}", json=customer_data)
            if response.status_code == 200:
                add_activity("UPDATE", "customer", str(customer_id), user['username'])
                return {"success": True, "data": response.json()}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.delete("/api/customers/{customer_id}")
async def delete_customer(customer_id: int, user: Dict = Depends(get_current_user)):
    """Delete customer (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.delete(f"{SERVICES['customers']}/customers/{customer_id}")
            if response.status_code in [200, 204]:
                add_activity("DELETE", "customer", str(customer_id), user['username'])
                return {"success": True, "message": f"Customer #{customer_id} deleted"}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.put("/api/products/{product_id}")
async def update_product(product_id: int, product_data: dict, user: Dict = Depends(get_current_user)):
    """Update product with inventory (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Extract stock_quantity before sending to products service
            stock_quantity = product_data.pop('stock_quantity', None)
            
            # Update product
            response = await client.put(f"{SERVICES['products']}/products/{product_id}", json=product_data)
            if response.status_code == 200:
                # Update inventory if stock_quantity was provided
                if stock_quantity is not None:
                    # Get existing inventory for this product
                    inv_resp = await client.get(f"{SERVICES['inventory']}/inventory/")
                    if inv_resp.status_code == 200:
                        inventories = inv_resp.json()
                        existing_inv = next((inv for inv in inventories if inv['product_id'] == product_id), None)
                        
                        if existing_inv:
                            # Update existing inventory
                            inv_update_data = {
                                "product_id": product_id,
                                "warehouse": existing_inv['warehouse'],
                                "on_hand": int(stock_quantity),
                                "reserved": existing_inv.get('reserved', 0)
                            }
                            await client.put(f"{SERVICES['inventory']}/inventory/{existing_inv['id']}", json=inv_update_data)
                        else:
                            # Create new inventory if doesn't exist
                            inv_data = {
                                "product_id": product_id,
                                "warehouse": "MAIN",
                                "on_hand": int(stock_quantity),
                                "reserved": 0
                            }
                            await client.post(f"{SERVICES['inventory']}/inventory/", json=inv_data)
                
                add_activity("UPDATE", "product", str(product_id), user['username'])
                return {"success": True, "data": response.json()}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.delete("/api/products/{product_id}")
async def delete_product(product_id: int, user: Dict = Depends(get_current_user)):
    """Delete product (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.delete(f"{SERVICES['products']}/products/{product_id}")
            if response.status_code in [200, 204]:
                add_activity("DELETE", "product", str(product_id), user['username'])
                return {"success": True, "message": f"Product #{product_id} deleted"}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.delete("/api/orders/{order_id}")
async def delete_order(order_id: int, user: Dict = Depends(get_current_user)):
    """Delete/cancel order (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.delete(f"{SERVICES['orders']}/orders/{order_id}")
            if response.status_code in [200, 204]:
                add_activity("DELETE", "order", str(order_id), user['username'])
                return {"success": True, "message": f"Order #{order_id} cancelled"}
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Store recent activity for real-time feed (in-memory buffer for WebSocket)
recent_activity = []

def add_activity(action: str, entity_type: str, entity_id: str, user: str, details: str = None, metadata: Dict = None):
    """Add activity to recent feed and persist to database"""
    activity = {
        "timestamp": datetime.utcnow().isoformat() + "Z",  # Add Z to mark as UTC
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user": user,
        "details": details
    }
    recent_activity.insert(0, activity)
    # Keep only last 50 activities in memory
    if len(recent_activity) > 50:
        recent_activity.pop()
    
    # Persist to database
    try:
        with engine.begin() as conn:
            metadata_json = json.dumps(metadata) if metadata else None
            conn.execute(
                text("""
                    INSERT INTO activity_logs 
                    (event_type, entity_type, entity_id, user_id, description, metadata) 
                    VALUES (:event_type, :entity_type, :entity_id, :user_id, :description, :metadata)
                """),
                {
                    "event_type": action,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "user_id": user,
                    "description": details,
                    "metadata": metadata_json
                }
            )
            # Transaction will auto-commit on successful exit
    except Exception as e:
        print(f"Error persisting activity log: {e}")

@app.get("/api/activity")
async def get_activity(user: Dict = Depends(get_current_user)):
    """Get recent activity feed (in-memory)"""
    return recent_activity[-20:]  # Return last 20 activities

@app.get("/api/logs")
async def get_logs(
    user: Dict = Depends(get_current_user),
    event_type: Optional[str] = Query(None, description="Filter by event type (CREATE, UPDATE, DELETE, PAYMENT)"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (order, customer, product, etc.)"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    search: Optional[str] = Query(None, description="Search in description"),
    limit: int = Query(100, description="Number of logs to return", le=1000),
    offset: int = Query(0, description="Offset for pagination")
):
    """Fetch activity logs with filters and pagination"""
    try:
        with engine.connect() as conn:
            # Build dynamic query
            where_clauses = []
            params = {}
            
            if event_type:
                where_clauses.append("event_type = :event_type")
                params["event_type"] = event_type
            
            if entity_type:
                where_clauses.append("entity_type = :entity_type")
                params["entity_type"] = entity_type
            
            if entity_id:
                where_clauses.append("entity_id = :entity_id")
                params["entity_id"] = entity_id
            
            if user_id:
                where_clauses.append("user_id = :user_id")
                params["user_id"] = user_id
            
            if start_date:
                where_clauses.append("timestamp >= :start_date")
                params["start_date"] = start_date
            
            if end_date:
                where_clauses.append("timestamp <= :end_date")
                params["end_date"] = end_date
            
            if search:
                where_clauses.append("description ILIKE :search")
                params["search"] = f"%{search}%"
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM activity_logs WHERE {where_sql}"
            total_result = conn.execute(text(count_query), params)
            total = total_result.scalar() or 0
            
            # Get logs
            params["limit"] = limit
            params["offset"] = offset
            query = f"""
                SELECT id, timestamp, event_type, entity_type, entity_id, 
                       user_id, description, metadata, ip_address, user_agent
                FROM activity_logs 
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT :limit OFFSET :offset
            """
            result = conn.execute(text(query), params)
            
            logs = []
            for row in result:
                log_entry = {
                    "id": row.id,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "event_type": row.event_type,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "user_id": row.user_id,
                    "description": row.description,
                    "metadata": json.loads(row.metadata) if row.metadata else None,
                    "ip_address": str(row.ip_address) if row.ip_address else None,
                    "user_agent": row.user_agent
                }
                logs.append(log_entry)
            
            return {
                "logs": logs,
                "total": total,
                "limit": limit,
                "offset": offset
            }
    except Exception as e:
        print(f"Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching logs: {str(e)}")

@app.get("/api/logs/export")
async def export_logs(
    user: Dict = Depends(get_current_user),
    format: str = Query("csv", description="Export format: csv or json"),
    event_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """Export activity logs as CSV or JSON"""
    # Admin only for exports
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        with engine.connect() as conn:
            # Build query with filters
            where_clauses = []
            params = {}
            
            if event_type:
                where_clauses.append("event_type = :event_type")
                params["event_type"] = event_type
            
            if entity_type:
                where_clauses.append("entity_type = :entity_type")
                params["entity_type"] = entity_type
            
            if entity_id:
                where_clauses.append("entity_id = :entity_id")
                params["entity_id"] = entity_id
            
            if user_id:
                where_clauses.append("user_id = :user_id")
                params["user_id"] = user_id
            
            if start_date:
                where_clauses.append("timestamp >= :start_date")
                params["start_date"] = start_date
            
            if end_date:
                where_clauses.append("timestamp <= :end_date")
                params["end_date"] = end_date
            
            if search:
                where_clauses.append("description ILIKE :search")
                params["search"] = f"%{search}%"
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            query = f"""
                SELECT id, timestamp, event_type, entity_type, entity_id, 
                       user_id, description, metadata, ip_address
                FROM activity_logs 
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT 10000
            """
            result = conn.execute(text(query), params)
            
            rows = []
            for row in result:
                rows.append({
                    "id": row.id,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else "",
                    "event_type": row.event_type,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "user_id": row.user_id,
                    "description": row.description or "",
                    "metadata": row.metadata or "",
                    "ip_address": str(row.ip_address) if row.ip_address else ""
                })
            
            if format == "csv":
                # Generate CSV
                output = StringIO()
                if rows:
                    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                
                csv_content = output.getvalue()
                return Response(
                    content=csv_content,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename=activity_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
                    }
                )
            else:
                # Return JSON
                return Response(
                    content=json.dumps({"logs": rows, "exported_at": datetime.utcnow().isoformat()}, indent=2),
                    media_type="application/json",
                    headers={
                        "Content-Disposition": f"attachment; filename=activity_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
                    }
                )
    except Exception as e:
        print(f"Error exporting logs: {e}")
        raise HTTPException(status_code=500, detail=f"Error exporting logs: {str(e)}")

@app.get("/api/logs/stats")
async def get_log_stats(user: Dict = Depends(get_current_user)):
    """Get activity log statistics"""
    try:
        with engine.connect() as conn:
            # Event type breakdown
            event_stats = conn.execute(text("""
                SELECT event_type, COUNT(*) as count 
                FROM activity_logs 
                GROUP BY event_type
                ORDER BY count DESC
            """))
            
            # Entity type breakdown
            entity_stats = conn.execute(text("""
                SELECT entity_type, COUNT(*) as count 
                FROM activity_logs 
                GROUP BY entity_type
                ORDER BY count DESC
            """))
            
            # Recent activity (last 24 hours)
            recent_count = conn.execute(text("""
                SELECT COUNT(*) FROM activity_logs 
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
            """)).scalar()
            
            # Total logs
            total_count = conn.execute(text("""
                SELECT COUNT(*) FROM activity_logs
            """)).scalar()
            
            return {
                "total_logs": total_count or 0,
                "recent_24h": recent_count or 0,
                "by_event_type": {row.event_type: row.count for row in event_stats},
                "by_entity_type": {row.entity_type: row.count for row in entity_stats}
            }
    except Exception as e:
        print(f"Error fetching log stats: {e}")
        return {
            "total_logs": 0,
            "recent_24h": 0,
            "by_event_type": {},
            "by_entity_type": {}
        }

@app.delete("/api/logs/clear")
async def clear_logs(user: Dict = Depends(get_current_user)):
    """Clear all activity logs (Admin only)"""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        with engine.begin() as conn:
            # Count logs before deletion
            count_result = conn.execute(text("SELECT COUNT(*) FROM activity_logs"))
            deleted_count = count_result.scalar() or 0
            
            # Delete all logs
            conn.execute(text("DELETE FROM activity_logs"))
            # Transaction will auto-commit on successful exit
            
            logger.info(f"Admin {user['username']} cleared {deleted_count} activity logs")
            
            return {
                "success": True,
                "deleted_count": deleted_count,
                "message": f"Successfully cleared {deleted_count} log entries"
            }
    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing logs: {str(e)}")

@app.get("/api/admin_notifications")
async def get_admin_notifications(user: Dict = Depends(get_current_user)):
    """Get admin notification counts for pending actions"""
    if user["role"] != UserRole.ADMIN:
        return {
            "pending_payment_approvals": 0,
            "ready_to_ship": 0,
            "in_transit": 0,
            "total_action_items": 0
        }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Fetch orders
            orders_resp = await client.get(f"{SERVICES['orders']}/orders/")
            if orders_resp.status_code != 200:
                return {
                    "pending_payment_approvals": 0,
                    "ready_to_ship": 0,
                    "in_transit": 0,
                    "total_action_items": 0
                }
            
            orders = orders_resp.json()
            
            # Count pending payment approvals (PENDING payment status)
            pending_payments = sum(1 for o in orders if o.get('payment_status') == 'PENDING')
            
            # Count orders ready to ship (COMPLETED payment, PROCESSING order status)
            ready_to_ship = sum(1 for o in orders 
                              if o.get('payment_status') == 'COMPLETED' 
                              and o.get('order_status') == 'PROCESSING')
            
            # Count in-transit orders (COMPLETED payment, SHIPPED order status)
            # These should appear in shipments tab with IN_TRANSIT status
            in_transit = sum(1 for o in orders
                           if o.get('payment_status') == 'COMPLETED'
                           and o.get('order_status') == 'SHIPPED')
            
            total = pending_payments + ready_to_ship + in_transit
            
            return {
                "pending_payment_approvals": pending_payments,
                "ready_to_ship": ready_to_ship,
                "in_transit": in_transit,
                "total_action_items": total
            }
        except Exception as e:
            print(f"Error fetching admin notifications: {e}")
            return {
                "pending_payment_approvals": 0,
                "ready_to_ship": 0,
                "in_transit": 0,
                "total_action_items": 0
            }

@app.get("/api/shipments")
async def get_shipments(user: Dict = Depends(get_current_user)):
    """Get all shipments enriched with order, customer, and product data
    
    Only returns shipments for orders where:
    - Payment status is COMPLETED
    - Order status is SHIPPED, DELIVERED, or CANCELLED (undelivered)
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Fetch shipments
            shipments_resp = await client.get(f"{SERVICES['shipments']}/shipments/")
            if shipments_resp.status_code != 200:
                return []
            
            shipments = shipments_resp.json()
            
            # Fetch orders, customers, and products for enrichment
            orders_resp = await client.get(f"{SERVICES['orders']}/orders/")
            customers_resp = await client.get(f"{SERVICES['customers']}/customers/")
            products_resp = await client.get(f"{SERVICES['products']}/products/")
            
            orders = {o['id']: o for o in orders_resp.json()} if orders_resp.status_code == 200 else {}
            customers = {c['id']: c for c in customers_resp.json()} if customers_resp.status_code == 200 else {}
            products = {p['id']: p for p in products_resp.json()} if products_resp.status_code == 200 else {}
            
            # Filter and enrich shipments based on order workflow rules
            valid_shipments = []
            for shipment in shipments:
                order = orders.get(shipment['order_id'], {})
                payment_status = order.get('payment_status', 'UNKNOWN')
                order_status = order.get('order_status', 'UNKNOWN')
                
                # Rule: Only show shipments for orders with COMPLETED payment
                if payment_status != 'COMPLETED':
                    continue
                
                # Rule: Only show shipments for orders that are SHIPPED, DELIVERED, or CANCELLED
                if order_status not in ['SHIPPED', 'DELIVERED', 'CANCELLED']:
                    continue
                
                # Enrich shipment data
                shipment['order_number'] = order.get('order_number', f"ORD-{shipment['order_id']}")
                shipment['order_total'] = order.get('order_total', 0)
                shipment['order_status'] = order_status
                shipment['payment_status'] = payment_status
                shipment['order_created_at'] = order.get('created_at')
                
                # Add customer info
                customer_id = order.get('customer_id')
                if customer_id:
                    customer = customers.get(customer_id, {})
                    shipment['customer_id'] = customer_id
                    shipment['customer_name'] = customer.get('name', f'Customer #{customer_id}')
                    shipment['customer_email'] = customer.get('email', '')
                    shipment['shipping_address'] = {
                        'street': customer.get('address_street', ''),
                        'city': customer.get('address_city', ''),
                        'state': customer.get('address_state', ''),
                        'zip': customer.get('address_zip', ''),
                        'country': customer.get('address_country', 'USA')
                    }
                
                # Add order items with product details
                shipment['items'] = []
                for item in order.get('items', []):
                    product = products.get(item['product_id'], {})
                    enriched_item = {
                        **item,
                        'product_name': product.get('name', f"Product #{item['product_id']}"),
                        'product_image': product.get('image_url', ''),
                        'seller_name': product.get('seller_name', ''),
                        'seller_location': product.get('seller_location', '')
                    }
                    shipment['items'].append(enriched_item)
                
                valid_shipments.append(shipment)
            
            return valid_shipments
        except Exception as e:
            print(f"Error fetching shipments: {e}")
            return []

@app.get("/api/health_snapshot")
async def health_snapshot(user: Dict = Depends(get_current_user)):
    return await fetch_metrics(user_role=user.get("role", UserRole.GUEST))

@app.get("/")
async def dashboard():
    """Serve the enhanced dashboard HTML"""
    # Read the dashboard HTML template
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'dashboard.html')
    try:
        with open(template_path, 'r') as f:
            content = f.read()
        return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Dashboard template not found</h1>", status_code=404, headers={"Cache-Control": "no-store"})

@app.get("/logs")
async def logs_page():
    """Serve the activity logs HTML page"""
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'logs.html')
    try:
        with open(template_path, 'r') as f:
            content = f.read()
        return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})
    except FileNotFoundError:
        # Fallback to inline HTML if template not found
        return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>ECI Platform - Monitoring Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            color: #2d3748;
            position: relative;
        }
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image:
                repeating-linear-gradient(90deg, transparent, transparent 2px, rgba(30, 60, 114, 0.02) 2px, rgba(30, 60, 114, 0.02) 4px),
                repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(30, 60, 114, 0.02) 2px, rgba(30, 60, 114, 0.02) 4px);
            background-size: 40px 40px;
            pointer-events: none;
            z-index: 0;
        }
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #7e8ba3 100%);
            position: relative;
            overflow: hidden;
        }
        .login-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image:
                linear-gradient(30deg, rgba(255,255,255,.05) 12%, transparent 12.5%, transparent 87%, rgba(255,255,255,.05) 87.5%, rgba(255,255,255,.05)),
                linear-gradient(150deg, rgba(255,255,255,.05) 12%, transparent 12.5%, transparent 87%, rgba(255,255,255,.05) 87.5%, rgba(255,255,255,.05)),
                linear-gradient(30deg, rgba(255,255,255,.05) 12%, transparent 12.5%, transparent 87%, rgba(255,255,255,.05) 87.5%, rgba(255,255,255,.05)),
                linear-gradient(150deg, rgba(255,255,255,.05) 12%, transparent 12.5%, transparent 87%, rgba(255,255,255,.05) 87.5%, rgba(255,255,255,.05));
            background-size: 80px 140px;
            background-position: 0 0, 0 0, 40px 70px, 40px 70px;
            opacity: 0.3;
        }
        .login-card {
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
            position: relative;
            z-index: 1;
        }
        .login-title {
            font-size: 1.875rem;
            font-weight: 700;
            text-align: center;
            margin-bottom: 30px;
            color: #1a202c;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #4a5568;
        }
        .form-input {
            width: 100%;
            padding: 12px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            font-size: 1rem;
            transition: border-color 0.2s;
        }
        .form-input:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn:hover {
            background: #5a67d8;
        }
        .user-hint {
            margin-top: 20px;
            padding: 12px;
            background: #edf2f7;
            border-radius: 6px;
            font-size: 0.875rem;
            color: #4a5568;
        }
        .header {
            background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 15px 0;
            position: sticky;
            top: 0;
            z-index: 100;
            position: relative;
        }
        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .user-badge {
            background: #667eea;
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 600;
        }
        .logout-btn {
            background: #ef4444;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            transition: background 0.2s;
        }
        .logout-btn:hover {
            background: #dc2626;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            position: relative;
            z-index: 1;
        }
        h1 {
            font-size: 1.875rem;
            font-weight: 600;
            color: #1a202c;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .metric-card {
            background: white;
            border-radius: 8px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
            border: 1px solid #e2e8f0;
        }
        .metric-value {
            font-size: 2.5rem;
            font-weight: 700;
            margin: 12px 0;
            color: #2d3748;
        }
        .metric-label {
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
            color: #718096;
            letter-spacing: 0.05em;
        }
        .services-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin-bottom: 30px;
        }
        .service-card {
            background: white;
            border-radius: 6px;
            padding: 16px;
            text-align: center;
            border: 1px solid #e2e8f0;
            transition: all 0.2s;
        }
        .service-card:hover {
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .service-name {
            font-weight: 600;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
            color: #4a5568;
        }
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-left: 4px;
        }
        .status-healthy { 
            background: #48bb78; 
            box-shadow: 0 0 0 0 rgba(72, 187, 120, 0.9);
            animation: breatheGreen 1.5s ease-in-out infinite;
        }
        .status-unhealthy { 
            background: #f56565; 
            box-shadow: 0 0 0 0 rgba(245, 101, 101, 0.9);
            animation: breatheRed 1s ease-in-out infinite;
        }
        .status-error { 
            background: #ed8936; 
            box-shadow: 0 0 0 0 rgba(237, 137, 54, 0.9);
            animation: breatheAmber 1.2s ease-in-out infinite;
        }
        @keyframes breatheGreen {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(72, 187, 120, 0.9);
                transform: scale(1);
            }
            50% {
                box-shadow: 0 0 0 10px rgba(72, 187, 120, 0);
                transform: scale(1.1);
            }
        }
        @keyframes breatheRed {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(245, 101, 101, 0.9);
                transform: scale(1);
            }
            50% {
                box-shadow: 0 0 0 10px rgba(245, 101, 101, 0);
                transform: scale(1.1);
            }
        }
        @keyframes breatheAmber {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(237, 137, 54, 0.9);
                transform: scale(1);
            }
            50% {
                box-shadow: 0 0 0 10px rgba(237, 137, 54, 0);
                transform: scale(1.1);
            }
        }
        .section-title {
            font-size: 1.25rem;
            font-weight: 600;
            color: #2d3748;
            margin: 30px 0 15px;
        }
        .button-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin: 30px 0;
        }
        .action-btn {
            padding: 12px 20px;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-transform: uppercase;
            font-size: 0.875rem;
            letter-spacing: 0.05em;
        }
        .btn-create { background: #48bb78; color: white; }
        .btn-create:hover { background: #38a169; }
        .btn-create:disabled { background: #cbd5e0; cursor: not-allowed; }
        .btn-test { background: #4299e1; color: white; }
        .btn-test:hover { background: #3182ce; }
        .btn-reset { background: #ed8936; color: white; }
        .btn-reset:hover { background: #dd6b20; }
        .btn-reset:disabled { background: #cbd5e0; cursor: not-allowed; }
        .btn-docs { background: #9f7aea; color: white; }
        .btn-docs:hover { background: #805ad5; }
        .response-time {
            font-size: 0.875rem;
            color: #718096;
            margin-top: 4px;
        }
        .timestamp {
            text-align: center;
            color: #718096;
            font-size: 0.875rem;
            margin-top: 20px;
        }
        .dashboard-container { display: none; }
        .error-message {
            color: #e53e3e;
            font-size: 0.875rem;
            margin-top: 10px;
            text-align: center;
        }
        .success-message {
            color: #38a169;
            font-size: 0.875rem;
            margin-top: 10px;
            text-align: center;
        }
    </style>
</head>
<body>
    <!-- Login Screen -->
    <div id="loginContainer" class="login-container">
        <div class="login-card">
            <h2 class="login-title">ECI Platform Login</h2>
            <form id="loginForm">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" id="username" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" id="password" class="form-input" required>
                </div>
                <button type="submit" class="btn">Login</button>
            </form>
            <div id="loginError" class="error-message"></div>
            <div class="user-hint">
                <strong>Test Users:</strong><br>
                • Admin: admin / admin123 (Full access)<br>
                • Guest: guest / guest123 (Read-only)
            </div>
        </div>
    </div>

    <!-- Dashboard -->
    <div id="dashboardContainer" class="dashboard-container">
        <div class="header">
            <div class="header-content">
                <h1>ECI Platform - Monitoring Dashboard</h1>
                <div class="user-info">
                    <span>Welcome, <strong id="userName"></strong></span>
                    <span class="user-badge" id="userRole"></span>
                    <button class="logout-btn" onclick="logout()">Logout</button>
                </div>
            </div>
        </div>

        <div class="container">
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Total Orders</div>
                    <div class="metric-value" id="totalOrders">0</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Failed Payments</div>
                    <div class="metric-value" id="failedPayments">0</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Latency</div>
                    <div class="metric-value" id="avgLatency">0<span style="font-size: 1rem;">ms</span></div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Stockouts</div>
                    <div class="metric-value" id="stockouts">0</div>
                </div>
            </div>

            <h2 class="section-title">Service Health Monitor</h2>
            <div class="services-grid" id="servicesGrid">
                <!-- Services will be populated here -->
            </div>

            <h2 class="section-title">Control Panel</h2>
            <div class="button-grid">
                <button class="action-btn btn-create" id="createOrderBtn" onclick="createOrder()">Create Order</button>
                <button class="action-btn btn-test" onclick="testServices()">Test Services</button>
                <button class="action-btn btn-reset" id="resetMetricsBtn" onclick="resetMetrics()">Reset Metrics</button>
                <button class="action-btn btn-docs" onclick="openAPIDocs()">API Docs</button>
            </div>
            <div id="actionMessage"></div>

            <div class="timestamp">Last updated: <span id="timestamp">-</span></div>
        </div>
    </div>

    <script>
        let ws = null;
        let authCredentials = null;
        let currentUser = null;

        // Login functionality
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            authCredentials = btoa(`${username}:${password}`);

            try {
                const response = await fetch('/api/user_info', {
                    headers: {
                        'Authorization': `Basic ${authCredentials}`
                    }
                });

                if (response.ok) {
                    currentUser = await response.json();
                    showDashboard();
                } else {
                    document.getElementById('loginError').textContent = 'Invalid username or password';
                }
            } catch (error) {
                document.getElementById('loginError').textContent = 'Login failed. Please try again.';
            }
        });

        function showDashboard() {
            document.getElementById('loginContainer').style.display = 'none';
            document.getElementById('dashboardContainer').style.display = 'block';

            // Update user info
            document.getElementById('userName').textContent = currentUser.name;
            document.getElementById('userRole').textContent = currentUser.role.toUpperCase();

            // Enable/disable buttons based on role
            const createOrderBtn = document.getElementById('createOrderBtn');
            const resetMetricsBtn = document.getElementById('resetMetricsBtn');

            if (currentUser.role === 'guest') {
                createOrderBtn.disabled = true;
                resetMetricsBtn.disabled = true;
            } else {
                createOrderBtn.disabled = false;
                resetMetricsBtn.disabled = false;
            }

            // Start WebSocket connection
            connectWebSocket();
        }

        function logout() {
            authCredentials = null;
            currentUser = null;
            if (ws) {
                ws.close();
            }
            document.getElementById('loginContainer').style.display = 'flex';
            document.getElementById('dashboardContainer').style.display = 'none';
            document.getElementById('loginForm').reset();
            document.getElementById('loginError').textContent = '';
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                setTimeout(connectWebSocket, 5000);
            };

            ws.onclose = () => {
                setTimeout(connectWebSocket, 5000);
            };
        }

        function updateDashboard(data) {
            // Update metrics
            document.getElementById('totalOrders').textContent = data.totals.orders_placed_total || 0;
            document.getElementById('failedPayments').textContent = data.totals.payments_failed_total || 0;
            document.getElementById('avgLatency').innerHTML =
                `${data.totals.inventory_reserve_latency_ms || 0}<span style="font-size: 1rem;">ms</span>`;
            document.getElementById('stockouts').textContent = data.totals.stockouts_total || 0;

            // Update services
            const servicesGrid = document.getElementById('servicesGrid');
            servicesGrid.innerHTML = '';

            for (const [name, info] of Object.entries(data.services)) {
                const card = document.createElement('div');
                card.className = 'service-card';

                let statusClass = 'status-healthy';
                if (info.status === 'unhealthy') statusClass = 'status-unhealthy';
                else if (info.status === 'error') statusClass = 'status-error';

                card.innerHTML = `
                    <div class="service-name">
                        ${name}
                        <span class="status-indicator ${statusClass}"></span>
                    </div>
                    <div class="response-time">
                        ${info.response_time_ms !== undefined ? info.response_time_ms + 'ms' : info.error || 'N/A'}
                    </div>
                `;
                servicesGrid.appendChild(card);
            }

            // Update timestamp
            const date = new Date(data.timestamp);
            document.getElementById('timestamp').textContent =
                date.toLocaleTimeString('en-US', { hour12: true });
        }

        async function createOrder() {
            if (currentUser.role !== 'admin') {
                showMessage('Only administrators can create orders', 'error');
                return;
            }

            try {
                const response = await fetch('/api/create_order', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Basic ${authCredentials}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        customer_id: 1,
                        products: [
                            { product_id: 1, quantity: 2, price: 29.99 }
                        ]
                    })
                });

                const result = await response.json();
                if (result.success) {
                    const msg = result.message || 'Order created successfully!';
                    if (result.order_id) {
                        showMessage(`${msg} - ID: ${result.order_id}`, 'success');
                    } else {
                        showMessage(msg, 'success');
                    }
                } else {
                    showMessage(result.error || result.detail || 'Failed to create order', 'error');
                }
            } catch (error) {
                showMessage('Error creating order: ' + error.message, 'error');
            }
        }

        async function testServices() {
            try {
                const response = await fetch('/api/test_services', {
                    headers: {
                        'Authorization': `Basic ${authCredentials}`
                    }
                });

                const result = await response.json();
                showMessage(result.message, result.healthy === result.total ? 'success' : 'error');
            } catch (error) {
                showMessage('Error testing services', 'error');
            }
        }

        async function resetMetrics() {
            if (currentUser.role !== 'admin') {
                showMessage('Only administrators can reset metrics', 'error');
                return;
            }

            try {
                const response = await fetch('/api/reset_metrics', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Basic ${authCredentials}`
                    }
                });

                const result = await response.json();
                showMessage(result.message, 'success');
            } catch (error) {
                showMessage('Error resetting metrics', 'error');
            }
        }

        function openAPIDocs() {
            window.open('http://localhost:8080/swagger', '_blank');
        }

        function showMessage(message, type) {
            const messageDiv = document.getElementById('actionMessage');
            messageDiv.className = type === 'error' ? 'error-message' : 'success-message';
            messageDiv.textContent = message;
            setTimeout(() => {
                messageDiv.textContent = '';
            }, 3000);
        }
    </script>
</body>
</html>
    """)