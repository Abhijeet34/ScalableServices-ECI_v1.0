"""Gateway service main module."""
from fastapi import FastAPI, Depends, Request, HTTPException, APIRouter, Form
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import httpx
import strawberry
from strawberry.fastapi import GraphQLRouter
from typing import List, Optional, Any, Dict
import json
import os
from cachetools import TTLCache
import redis
from .auth_local import decode_access_token, create_access_token
from .core_settings import get_settings

settings = get_settings()
GATEWAY_VERSION = "1.0.0"

app = FastAPI(title="ECI API Gateway", docs_url="/swagger", redoc_url=None)

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Caching setup
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client: Optional[redis.Redis] = None
local_cache = TTLCache(maxsize=1024, ttl=60)

@app.on_event("startup")
def _init_cache():
    global redis_client
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
    except Exception:
        redis_client = None

SERVICE_MAP = {
    "customers": "http://customers:8000",
    "products": "http://products:8000",
    "inventory": "http://inventory:8000",
    "orders": "http://orders:8000",
    "payments": "http://payments:8000",
    "shipments": "http://shipments:8000",
}

BEARER_PREFIX = "Bearer "

def verify_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith(BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ", 1)[1]
    token_data = decode_access_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token_data

class TokenRequest(BaseModel):
    username: str

@app.get("/health")
async def health_check():
    """Health check endpoint for k8s probes - no auth required."""
    return {
        "status": "healthy",
        "service": "gateway",
        "version": GATEWAY_VERSION,
        "releaseId": os.getenv("RELEASE_ID", "unknown"),
    }

@app.get("/", include_in_schema=False)
async def root():
    """Friendly landing endpoint for the Gateway (no auth)."""
    return {
        "service": "gateway",
        "version": GATEWAY_VERSION,
        "docs": "/swagger",
        "graphql": "/graphql",
        "health": "/health",
    }

@app.post("/auth/token")
async def issue_token(request: Request, username: str = Form(None)):
    # Accept form field, JSON body, or query parameter for flexibility
    if username:
        chosen = username
    else:
        try:
            data = await request.json()
            chosen = data.get("username")
        except Exception:
            chosen = request.query_params.get("username")
    if not chosen:
        raise HTTPException(status_code=422, detail="username is required")
    return {"access_token": create_access_token(chosen), "token_type": "bearer"}

def cache_get(key: str):
    """Retrieve cached value if present."""
    if redis_client:
        try:
            val = redis_client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception:
            pass
    return local_cache.get(key)

def cache_set(key: str, value, ttl: int = 60):
    """Set a cache value with TTL."""
    if redis_client:
        try:
            redis_client.setex(key, ttl, json.dumps(value))
            return
        except Exception:
            pass
    local_cache[key] = value

def cache_delete_pattern(patterns: list[str]):
    """Delete cache entries whose keys start with any of the provided prefixes."""
    for prefix in patterns:
        # Local cache purge
        for key in tuple(local_cache.keys()):  # tuple snapshot
            if key.startswith(prefix):
                local_cache.pop(key, None)
        # Redis purge
        if redis_client:
            try:
                for key in redis_client.scan_iter(match=f"{prefix}*"):
                    redis_client.delete(key)
            except Exception:
                pass

def _build_downstream_url(base: str, service: str, path: str) -> str:
    # Always include the service resource segment expected by the downstream FastAPI app
    # Examples:
    #  /customers/ -> http://customers:8000/customers/
    #  /customers/123 -> http://customers:8000/customers/123
    normalized_path = path.lstrip('/') if path else ''
    if normalized_path:
        return f"{base}/{service}/{normalized_path}"
    return f"{base}/{service}/"

def _invalidate_caches(service: str, base: str, entity_id: int | None = None):
    """Invalidate cache entries for a service.

    If entity_id is provided, perform targeted invalidation for that entity list and detail keys.
    Otherwise, clear all list + gql caches for the service.
    """
    try:
        if entity_id is not None:
            patterns = [
                f"rest:GET:{base}/{service}/{entity_id}",  # detail
            ]
            # Also clear cached list because detail changed might affect list
            patterns.append(f"rest:GET:{base}/{service}/")
            # GraphQL aggregated list
            patterns.append(f"gql:{service}")
            cache_delete_pattern(patterns)
        else:
            cache_delete_pattern([
                f"rest:GET:{base}/{service}/",
                f"gql:{service}"
            ])
    except Exception:
        pass

@app.api_route("/{service}/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"], include_in_schema=False)
async def proxy(service: str, path: str, request: Request, token=Depends(verify_token)):
    base = SERVICE_MAP.get(service)
    if not base:
        raise HTTPException(status_code=404, detail="Unknown service")
    url = _build_downstream_url(base, service, path)
    is_get = request.method == "GET"
    # Build granular cache key (no method except GET since we only cache GET)
    cache_key = f"rest:GET:{url}:{request.query_params}" if is_get else None
    if cache_key:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    # Use longer timeout to allow for snapshot enrichment in orders service
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(request.method, url, headers=headers, content=body)
    if request.method in {"POST","PUT","PATCH","DELETE"} and resp.status_code < 400:
        # Attempt to parse entity id from path for targeted invalidation when path ends with numeric segment
        entity_id = None
        last_segment = path.rstrip('/').split('/')[-1]
        if last_segment.isdigit():
            entity_id = int(last_segment)
        _invalidate_caches(service, base, entity_id=entity_id)
    # Handle 204 No Content responses
    if resp.status_code == 204:
        return None
    content_type = resp.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        data = resp.json()
        if cache_key:
            cache_set(cache_key, data)
        return data
    return resp.text

#############################
# REST Documentation Models #
#############################

class CustomerCreate(BaseModel):
    name: str
    email: str

class CustomerRead(CustomerCreate):
    id: int

class ProductCreate(BaseModel):
    sku: str
    name: str
    category: str
    price: float
    is_active: bool | None = True

class ProductRead(ProductCreate):
    id: int

class InventoryCreate(BaseModel):
    product_id: int
    warehouse: str
    on_hand: int
    reserved: int = 0

class InventoryRead(InventoryCreate):
    id: int

class OrderItemRead(BaseModel):
    id: int
    product_id: int
    sku: str
    quantity: int
    unit_price: float
    product_name_snapshot: Optional[str] = None
    product_category_snapshot: Optional[str] = None
    # Metadata fields (computed at runtime)
    product_data_status: Optional[str] = None  # "current", "modified", "deleted"
    product_current_name: Optional[str] = None
    product_current_price: Optional[float] = None

class OrderRead(BaseModel):
    id: int
    customer_id: int
    order_status: str
    payment_status: str
    order_total: float
    customer_name_snapshot: Optional[str] = None
    customer_email_snapshot: Optional[str] = None
    customer_phone_snapshot: Optional[str] = None
    items: list[OrderItemRead] = []
    # Metadata fields (computed at runtime)
    customer_data_status: Optional[str] = None  # "current", "modified", "deleted"
    customer_current_name: Optional[str] = None
    customer_current_email: Optional[str] = None

class PaymentRead(BaseModel):
    id: int
    order_id: int
    amount: float
    status: str

class ShipmentRead(BaseModel):
    id: int
    order_id: int
    carrier: str
    status: str
    tracking_no: str
    shipped_at: str | None = None
    delivered_at: str | None = None

#############################
# Helper HTTP functions     #
#############################

async def _forward_get(url: str, token: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

async def _forward_json(method: str, url: str, token: str, payload: dict | None):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, url, json=payload, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

#############################
# Grouped Service Routers    #
#############################

# Customers
customers_router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(verify_token)])

@customers_router.get("/", response_model=list[CustomerRead])
async def get_customers(request: Request, refresh: bool = False):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['customers']}/customers/"
    cache_key = f"rest:GET:{url}:"  # no query params
    if not refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    data = await _forward_get(url, token)
    cache_set(cache_key, data)
    return data

@customers_router.post("/", response_model=CustomerRead, status_code=201)
async def create_customer(payload: CustomerCreate, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['customers']}/customers/"
    result = await _forward_json("POST", url, token, payload.dict())
    _invalidate_caches("customers", SERVICE_MAP['customers'])
    return result

# Products
products_router = APIRouter(prefix="/products", tags=["products"], dependencies=[Depends(verify_token)])

@products_router.get("/", response_model=list[ProductRead])
async def get_products(request: Request, refresh: bool = False):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['products']}/products/"
    cache_key = f"rest:GET:{url}:"
    if not refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    data = await _forward_get(url, token)
    cache_set(cache_key, data)
    return data

@products_router.post("/", response_model=ProductRead, status_code=201)
async def create_product(payload: ProductCreate, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['products']}/products/"
    result = await _forward_json("POST", url, token, payload.dict())
    _invalidate_caches("products", SERVICE_MAP['products'])
    return result

# Inventory
inventory_router = APIRouter(prefix="/inventory", tags=["inventory"], dependencies=[Depends(verify_token)])

@inventory_router.get("/", response_model=list[InventoryRead])
async def get_inventory(request: Request, refresh: bool = False):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['inventory']}/inventory/"
    cache_key = f"rest:GET:{url}:"
    if not refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    data = await _forward_get(url, token)
    cache_set(cache_key, data)
    return data

@inventory_router.post("/", response_model=InventoryRead, status_code=201)
async def create_inventory(payload: InventoryCreate, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['inventory']}/inventory/"
    result = await _forward_json("POST", url, token, payload.dict())
    _invalidate_caches("inventory", SERVICE_MAP['inventory'])
    return result

@inventory_router.put("/{item_id}", response_model=InventoryRead)
async def update_inventory(item_id: int, payload: InventoryCreate, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['inventory']}/inventory/{item_id}"
    result = await _forward_json("PUT", url, token, payload.dict())
    _invalidate_caches("inventory", SERVICE_MAP['inventory'])
    return result

@inventory_router.delete("/{item_id}", status_code=204)
async def delete_inventory(item_id: int, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{SERVICE_MAP['inventory']}/inventory/{item_id}"
        resp = await client.delete(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    _invalidate_caches("inventory", SERVICE_MAP['inventory'])
    return None

# Orders
orders_router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(verify_token)])

@orders_router.get("/", response_model=list[OrderRead])
async def get_orders(request: Request, refresh: bool = False):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['orders']}/orders/"
    cache_key = f"rest:GET:{url}:"
    if not refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    data = await _forward_get(url, token)
    cache_set(cache_key, data)
    return data

@orders_router.post("/", response_model=OrderRead, status_code=201)
async def create_order(payload: dict, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['orders']}/orders/"
    result = await _forward_json("POST", url, token, payload)
    _invalidate_caches("orders", SERVICE_MAP['orders'])
    return result

@orders_router.put("/{order_id}", response_model=OrderRead)
async def update_order(order_id: int, payload: dict, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['orders']}/orders/{order_id}"
    result = await _forward_json("PUT", url, token, payload)
    _invalidate_caches("orders", SERVICE_MAP['orders'])
    return result

@orders_router.delete("/{order_id}", status_code=204)
async def delete_order(order_id: int, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{SERVICE_MAP['orders']}/orders/{order_id}"
        resp = await client.delete(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    _invalidate_caches("orders", SERVICE_MAP['orders'])
    return None

# Payments
payments_router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(verify_token)])

@payments_router.get("/", response_model=list[PaymentRead])
async def get_payments(request: Request, refresh: bool = False):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['payments']}/payments/"
    cache_key = f"rest:GET:{url}:"
    if not refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    data = await _forward_get(url, token)
    cache_set(cache_key, data)
    return data

@payments_router.post("/", response_model=PaymentRead, status_code=201)
async def create_payment(payload: dict, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['payments']}/payments/"
    result = await _forward_json("POST", url, token, payload)
    _invalidate_caches("payments", SERVICE_MAP['payments'])
    return result

@payments_router.put("/{payment_id}", response_model=PaymentRead)
async def update_payment(payment_id: int, payload: dict, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['payments']}/payments/{payment_id}"
    result = await _forward_json("PUT", url, token, payload)
    _invalidate_caches("payments", SERVICE_MAP['payments'])
    return result

@payments_router.delete("/{payment_id}", status_code=204)
async def delete_payment(payment_id: int, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{SERVICE_MAP['payments']}/payments/{payment_id}"
        resp = await client.delete(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    _invalidate_caches("payments", SERVICE_MAP['payments'])
    return None

# Shipments
shipments_router = APIRouter(prefix="/shipments", tags=["shipments"], dependencies=[Depends(verify_token)])

@shipments_router.get("/", response_model=list[ShipmentRead])
async def get_shipments(request: Request, refresh: bool = False):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['shipments']}/shipments/"
    cache_key = f"rest:GET:{url}:"
    if not refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    data = await _forward_get(url, token)
    cache_set(cache_key, data)
    return data

@shipments_router.post("/", response_model=ShipmentRead, status_code=201)
async def create_shipment(payload: dict, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['shipments']}/shipments/"
    result = await _forward_json("POST", url, token, payload)
    _invalidate_caches("shipments", SERVICE_MAP['shipments'])
    return result

@shipments_router.put("/{shipment_id}", response_model=ShipmentRead)
async def update_shipment(shipment_id: int, payload: dict, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    url = f"{SERVICE_MAP['shipments']}/shipments/{shipment_id}"
    result = await _forward_json("PUT", url, token, payload)
    _invalidate_caches("shipments", SERVICE_MAP['shipments'])
    return result

@shipments_router.delete("/{shipment_id}", status_code=204)
async def delete_shipment(shipment_id: int, request: Request):
    token = request.headers.get("Authorization", "").replace(BEARER_PREFIX, "")
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{SERVICE_MAP['shipments']}/shipments/{shipment_id}"
        resp = await client.delete(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    _invalidate_caches("shipments", SERVICE_MAP['shipments'])
    return None

app.include_router(customers_router)
app.include_router(products_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(shipments_router)

# GraphQL layer (Queries Only; Mutations intentionally omitted)
# Enhanced with relations, pagination, filtering, and ordering.

#############################
# GraphQL Types & Resolvers  #
#############################

def _gql_build_cache_key(root_field: str, args: Dict[str, Any]) -> str:
    # build deterministic key ignoring None values
    filtered = {k: v for k, v in args.items() if v is not None}
    try:
        return f"gql:{root_field}:{json.dumps(filtered, sort_keys=True)}"
    except Exception:
        return f"gql:{root_field}:{str(filtered)}"

async def _fetch_json(endpoint: str, token: str):
    if not token:
        raise HTTPException(status_code=401, detail="Missing token for downstream fetch")
    header_val = f"Bearer {token}".strip()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(endpoint, headers={"Authorization": header_val})
        resp.raise_for_status()
        return resp.json()

def _apply_filters(sequence: List[dict], filters: Dict[str, Any]) -> List[dict]:
    active = {k: v for k, v in filters.items() if v is not None}
    if not active:
        return sequence

    predicates: List = []
    for k, v in active.items():
        if k.endswith('_contains'):
            field = k[:-9]
            predicates.append(lambda item, f=field, exp=v: exp.lower() in str(item.get(f, '')).lower())
        elif k.startswith('min_'):
            field = k[4:]
            predicates.append(lambda item, f=field, lim=v: (item.get(f) is not None and item.get(f) >= lim))
        elif k.startswith('max_'):
            field = k[4:]
            predicates.append(lambda item, f=field, lim=v: (item.get(f) is not None and item.get(f) <= lim))
        else:
            field = k
            predicates.append(lambda item, f=field, exp=v: item.get(f) == exp)

    return [item for item in sequence if all(pred(item) for pred in predicates)]

def _apply_ordering(sequence: List[dict], order_by: Optional[List[str]]) -> List[dict]:
    if not order_by:
        return sequence
    # Apply multiple ordering keys stable by reversing and sorting each
    for key in reversed(order_by):
        desc = key.startswith('-')
        field = key[1:] if desc else key
        sequence.sort(key=lambda x, f=field: x.get(f), reverse=desc)
    return sequence

def _apply_pagination(sequence: List[dict], skip: int, take: int) -> List[dict]:
    skip = max(skip or 0, 0)
    if take is None or take < 0:
        return sequence[skip:]
    return sequence[skip: skip + take]

def _context_token(info) -> str:
    request: Request = info.context["request"]
    raw = request.headers.get("Authorization", "").strip()
    return raw[len(BEARER_PREFIX):].strip() if raw.startswith(BEARER_PREFIX) else ""

def _context_cache(info) -> Dict[str, Any]:
    return info.context.setdefault("gql_cache", {})

def _load_service_list(info, service: str, token: str) -> List[dict]:
    cache = _context_cache(info)
    key = f"svc:{service}"
    if key in cache:
        return cache[key]
    data = info.context.get("_preloaded", {}).get(service)
    if data is None:
        # fallback fetch now
        data = httpx.get(f"{SERVICE_MAP[service]}/{service}/", headers={"Authorization": f"Bearer {token}"}).json()
    cache[key] = data
    return data

@strawberry.type
class Customer:
    id: int
    name: str
    email: str

@strawberry.type
class Product:
    id: int
    sku: str
    name: str
    category: str
    price: float
    is_active: bool

@strawberry.type
class OrderItem:
    id: int
    product_id: int
    sku: str
    quantity: int
    unit_price: float
    product_name_snapshot: Optional[str] = None
    product_category_snapshot: Optional[str] = None
    product_data_status: Optional[str] = None
    product_current_name: Optional[str] = None
    product_current_price: Optional[float] = None

    @strawberry.field
    def product(self, info) -> Optional[Product]:
        token = _context_token(info)
        products = _load_service_list(info, 'products', token)
        prod_map = {p['id']: p for p in products}
        raw = prod_map.get(self.product_id)
        return Product(**raw) if raw else None

@strawberry.type
class Payment:
    id: int
    order_id: int
    amount: float
    status: str

@strawberry.type
class Shipment:
    id: int
    order_id: int
    carrier: str
    status: str
    tracking_no: str
    shipped_at: Optional[str]
    delivered_at: Optional[str]

@strawberry.type
class Order:
    id: int
    customer_id: int
    order_status: str
    payment_status: str
    order_total: float
    items: List[OrderItem]
    customer_name_snapshot: Optional[str] = None
    customer_email_snapshot: Optional[str] = None
    customer_phone_snapshot: Optional[str] = None
    customer_data_status: Optional[str] = None
    customer_current_name: Optional[str] = None
    customer_current_email: Optional[str] = None

    @strawberry.field
    def customer(self, info) -> Optional[Customer]:
        token = _context_token(info)
        customers = _load_service_list(info, 'customers', token)
        cust_map = {c['id']: c for c in customers}
        raw = cust_map.get(self.customer_id)
        return Customer(**raw) if raw else None

    @strawberry.field
    def payments(self, info) -> List[Payment]:
        token = _context_token(info)
        payments = _load_service_list(info, 'payments', token)
        return [Payment(**p) for p in payments if p.get('order_id') == self.id]

    @strawberry.field
    def shipments(self, info) -> List[Shipment]:
        token = _context_token(info)
        shipments = _load_service_list(info, 'shipments', token)
        return [Shipment(**s) for s in shipments if s.get('order_id') == self.id]

@strawberry.type
class PaymentSummary:
    status: str
    total_amount: float
    count: int

#############################
# Root Query with arguments #
#############################

@strawberry.type
class Query:
    @strawberry.field
    async def customers(self, info, skip: int = 0, take: Optional[int] = 50,
                        name_contains: Optional[str] = None,
                        email_contains: Optional[str] = None,
                        order_by: Optional[List[str]] = None) -> List[Customer]:
        token = _context_token(info)
        args = {"skip": skip, "take": take, "name_contains": name_contains, "email_contains": email_contains, "order_by": order_by}
        cache_key = _gql_build_cache_key("customers", args)
        cached = cache_get(cache_key)
        if cached is not None:
            return [Customer(**c) for c in cached]
        data = await _fetch_json(f"{SERVICE_MAP['customers']}/customers/", token)
        data = _apply_filters(data, {"name_contains": name_contains, "email_contains": email_contains})
        data = _apply_ordering(data, order_by)
        data = _apply_pagination(data, skip, take if take is not None else -1)
        cache_set(cache_key, data)
        return [Customer(**c) for c in data]

    @strawberry.field
    async def products(self, info, skip: int = 0, take: Optional[int] = 50,
                       category: Optional[str] = None,
                       sku_contains: Optional[str] = None,
                       name_contains: Optional[str] = None,
                       min_price: Optional[float] = None,
                       max_price: Optional[float] = None,
                       is_active: Optional[bool] = None,
                       order_by: Optional[List[str]] = None) -> List[Product]:
        token = _context_token(info)
        args = {"skip": skip, "take": take, "category": category, "sku_contains": sku_contains, "name_contains": name_contains,
                "min_price": min_price, "max_price": max_price, "is_active": is_active, "order_by": order_by}
        cache_key = _gql_build_cache_key("products", args)
        cached = cache_get(cache_key)
        if cached is not None:
            return [Product(**p) for p in cached]
        data = await _fetch_json(f"{SERVICE_MAP['products']}/products/", token)
        data = _apply_filters(data, {"category": category, "sku_contains": sku_contains, "name_contains": name_contains,
                                     "min_price": min_price, "max_price": max_price, "is_active": is_active})
        data = _apply_ordering(data, order_by)
        data = _apply_pagination(data, skip, take if take is not None else -1)
        cache_set(cache_key, data)
        return [Product(**p) for p in data]

    @strawberry.field
    async def orders(self, info, skip: int = 0, take: Optional[int] = 50,
                     customer_id: Optional[int] = None,
                     order_status: Optional[str] = None,
                     payment_status: Optional[str] = None,
                     min_total: Optional[float] = None,
                     max_total: Optional[float] = None,
                     order_by: Optional[List[str]] = None) -> List[Order]:
        token = _context_token(info)
        args = {"skip": skip, "take": take, "customer_id": customer_id, "order_status": order_status, "payment_status": payment_status,
                "min_total": min_total, "max_total": max_total, "order_by": order_by}
        cache_key = _gql_build_cache_key("orders", args)
        cached = cache_get(cache_key)
        if cached is not None:
            return [Order(**o, items=[OrderItem(**i) for i in o.get('items', [])]) for o in cached]
        data = await _fetch_json(f"{SERVICE_MAP['orders']}/orders/", token)
        data = _apply_filters(data, {"customer_id": customer_id, "order_status": order_status, "payment_status": payment_status,
                                     "min_order_total": min_total, "max_order_total": max_total})
        # Custom handling for min/max total (fields named order_total)
        if min_total is not None:
            data = [d for d in data if d.get('order_total') is not None and d['order_total'] >= min_total]
        if max_total is not None:
            data = [d for d in data if d.get('order_total') is not None and d['order_total'] <= max_total]
        data = _apply_ordering(data, order_by)
        data = _apply_pagination(data, skip, take if take is not None else -1)
        cache_set(cache_key, data)
        # Build Order objects with all fields including snapshots and metadata
        result = []
        for o in data:
            items = [OrderItem(**i) for i in o.get('items', [])]
            result.append(Order(**{k: v for k, v in o.items() if k != 'items'}, items=items))
        return result

    @strawberry.field
    async def payments(self, info, skip: int = 0, take: Optional[int] = 50,
                       order_id: Optional[int] = None,
                       status: Optional[str] = None,
                       min_amount: Optional[float] = None,
                       max_amount: Optional[float] = None,
                       order_by: Optional[List[str]] = None) -> List[Payment]:
        token = _context_token(info)
        args = {"skip": skip, "take": take, "order_id": order_id, "status": status, "min_amount": min_amount, "max_amount": max_amount, "order_by": order_by}
        cache_key = _gql_build_cache_key("payments", args)
        cached = cache_get(cache_key)
        if cached is not None:
            return [Payment(**p) for p in cached]
        data = await _fetch_json(f"{SERVICE_MAP['payments']}/payments/", token)
        data = _apply_filters(data, {"order_id": order_id, "status": status, "min_amount": min_amount, "max_amount": max_amount})
        if min_amount is not None:
            data = [d for d in data if float(d.get('amount', 0)) >= min_amount]
        if max_amount is not None:
            data = [d for d in data if float(d.get('amount', 0)) <= max_amount]
        data = _apply_ordering(data, order_by)
        data = _apply_pagination(data, skip, take if take is not None else -1)
        cache_set(cache_key, data)
        return [Payment(**p) for p in data]

    @strawberry.field
    async def shipments(self, info, skip: int = 0, take: Optional[int] = 50,
                        order_id: Optional[int] = None,
                        status: Optional[str] = None,
                        carrier: Optional[str] = None,
                        order_by: Optional[List[str]] = None) -> List[Shipment]:
        token = _context_token(info)
        args = {"skip": skip, "take": take, "order_id": order_id, "status": status, "carrier": carrier, "order_by": order_by}
        cache_key = _gql_build_cache_key("shipments", args)
        cached = cache_get(cache_key)
        if cached is not None:
            return [Shipment(**s) for s in cached]
        data = await _fetch_json(f"{SERVICE_MAP['shipments']}/shipments/", token)
        data = _apply_filters(data, {"order_id": order_id, "status": status, "carrier_contains": carrier})
        data = _apply_ordering(data, order_by)
        data = _apply_pagination(data, skip, take if take is not None else -1)
        cache_set(cache_key, data)
        return [Shipment(**s) for s in data]

    @strawberry.field
    async def payments_summary(self, info) -> List[PaymentSummary]:
        token = _context_token(info)
        cache_key = "gql:payments_summary"
        cached = cache_get(cache_key)
        if cached is not None:
            return [PaymentSummary(**p) for p in cached]
        payments = await _fetch_json(f"{SERVICE_MAP['payments']}/payments/", token)
        summary_map: Dict[str, Dict[str, Any]] = {}
        for p in payments:
            st = p['status']
            amt = float(p['amount']) if not isinstance(p['amount'], (int, float)) else p['amount']
            entry = summary_map.setdefault(st, {"status": st, "total_amount": 0.0, "count": 0})
            entry["total_amount"] += amt
            entry["count"] += 1
        summary = list(summary_map.values())
        cache_set(cache_key, summary, ttl=120)
        return [PaymentSummary(**p) for p in summary]

    @strawberry.field
    async def order(self, info, id: int) -> Optional[Order]:
        orders = await self.orders(info, skip=0, take=None)
        for o in orders:
            if o.id == id:
                return o
        return None

    @strawberry.field
    async def customer(self, info, id: int) -> Optional[Customer]:
        customers = await self.customers(info, skip=0, take=None)
        for c in customers:
            if c.id == id:
                return c
        return None

    @strawberry.field
    async def product(self, info, id: int) -> Optional[Product]:
        products = await self.products(info, skip=0, take=None)
        for p in products:
            if p.id == id:
                return p
        return None

schema = strawberry.Schema(query=Query)

def _gql_context_getter(request: Request):
    return {"request": request, "gql_cache": {}}

graphql_app = GraphQLRouter(schema, graphiql=True, context_getter=_gql_context_getter)
app.include_router(graphql_app, prefix="/graphql", include_in_schema=False)

#############################
# OpenAPI Security Metadata #
#############################



def custom_openapi():
    # Local import to avoid module-level import order warnings (E402)
    from fastapi.openapi.utils import get_openapi
    if app.openapi_schema:
        return app.openapi_schema
    # Build schema then filter out paths for hidden routes if any slipped through
    schema_data = get_openapi(
        title=app.title,
        version="1.0.0",
        description="Gateway providing grouped REST CRUD endpoints. Internal proxy & GraphQL routes hidden.",
        routes=[r for r in app.routes if getattr(r, 'include_in_schema', True)],
    )
    # Add bearer auth scheme
    schema_data.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
    }
    # Apply global security requirement
    schema_data["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema_data
    return app.openapi_schema

app.openapi = custom_openapi  # type: ignore
# test change
