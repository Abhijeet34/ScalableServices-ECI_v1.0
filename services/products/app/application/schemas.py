from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class ProductCreate(BaseModel):
    sku: Optional[str] = None
    name: str
    category: str
    price: float
    is_active: bool = True
    description: Optional[str] = None
    # Seller Information - Required for marketplace functionality
    seller_name: str
    seller_location: Optional[str] = None
    seller_member_since: Optional[date] = None
    seller_response_time: str
    seller_shipping_policy: Optional[str] = None
    seller_return_policy: Optional[str] = None
    seller_badge: str

class ProductRead(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    price: float
    is_active: bool
    description: Optional[str] = None
    seller_name: Optional[str] = None
    seller_location: Optional[str] = None
    seller_member_since: Optional[date] = None
    seller_response_time: Optional[str] = None
    seller_shipping_policy: Optional[str] = None
    seller_return_policy: Optional[str] = None
    seller_badge: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
