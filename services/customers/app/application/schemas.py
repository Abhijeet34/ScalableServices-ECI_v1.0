from pydantic import BaseModel
from typing import Optional

class CustomerCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    # Shipping Address - Required for order fulfillment
    address_street: str
    address_city: str
    address_state: str
    address_zip: str
    address_country: str = 'USA'

class CustomerRead(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_state: Optional[str] = None
    address_zip: Optional[str] = None
    address_country: Optional[str] = None

    class Config:
        from_attributes = True
