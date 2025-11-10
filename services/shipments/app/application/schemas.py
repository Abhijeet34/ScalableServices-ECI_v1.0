from pydantic import BaseModel
from typing import Optional

class ShipmentCreate(BaseModel):
    order_id: int
    carrier: Optional[str] = None
    status: Optional[str] = "PENDING"
    tracking_no: Optional[str] = None
    shipped_at: Optional[str] = None
    delivered_at: Optional[str] = None

class ShipmentRead(BaseModel):
    id: int
    order_id: int
    carrier: str
    status: str
    tracking_no: str
    shipped_at: str
    delivered_at: Optional[str] = None
    class Config:
        orm_mode = True
