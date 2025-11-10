from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class OrderItemCreate(BaseModel):
    product_id: int
    sku: str
    quantity: int
    unit_price: float

class OrderCreate(BaseModel):
    customer_id: int
    order_status: str = "PENDING"
    payment_status: str = "PENDING"
    items: list[OrderItemCreate]

class OrderUpdate(BaseModel):
    order_status: Optional[str] = None
    payment_status: Optional[str] = None
    payment_id: Optional[str] = None
    receipt_id: Optional[str] = None

class OrderItemRead(BaseModel):
    id: int
    product_id: int
    sku: str
    quantity: int
    unit_price: float
    product_name_snapshot: Optional[str] = None
    product_category_snapshot: Optional[str] = None
    # Metadata fields (not in DB, computed at runtime)
    product_data_status: Optional[str] = None  # "current", "modified", "deleted"
    product_current_name: Optional[str] = None
    product_current_price: Optional[float] = None
    class Config:
        orm_mode = True

class OrderRead(BaseModel):
    id: int
    order_number: str
    customer_id: int
    order_status: str
    payment_status: str
    order_total: float
    payment_id: Optional[str] = None
    receipt_id: Optional[str] = None
    created_at: datetime
    customer_name_snapshot: Optional[str] = None
    customer_email_snapshot: Optional[str] = None
    customer_phone_snapshot: Optional[str] = None
    items: list[OrderItemRead]
    # Metadata fields (not in DB, computed at runtime)
    customer_data_status: Optional[str] = None  # "current", "modified", "deleted"
    customer_current_name: Optional[str] = None
    customer_current_email: Optional[str] = None
    class Config:
        orm_mode = True
