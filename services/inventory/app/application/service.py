from sqlalchemy.orm import Session
from app.domain.models import Inventory
from .schemas import InventoryCreate

class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def list(self):
        return self.db.query(Inventory).all()

    def create(self, data: InventoryCreate):
        obj = Inventory(**data.dict())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
