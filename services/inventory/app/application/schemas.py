from pydantic import BaseModel

class InventoryCreate(BaseModel):
    product_id: int
    warehouse: str
    on_hand: int
    reserved: int = 0

class InventoryRead(BaseModel):
    id: int
    product_id: int
    warehouse: str
    on_hand: int
    reserved: int
    class Config:
        orm_mode = True
