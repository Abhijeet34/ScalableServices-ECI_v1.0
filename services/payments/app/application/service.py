from sqlalchemy.orm import Session
from app.domain.models import Payment
from .schemas import PaymentCreate

class PaymentService:
    def __init__(self, db: Session):
        self.db = db

    def list(self):
        return self.db.query(Payment).all()

    def create(self, data: PaymentCreate):
        obj = Payment(**data.dict())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
