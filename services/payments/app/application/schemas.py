from pydantic import BaseModel

class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    method: str
    status: str
    reference: str

class PaymentRead(BaseModel):
    id: int
    order_id: int
    amount: float
    method: str
    status: str
    reference: str
    class Config:
        orm_mode = True
