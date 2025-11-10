from sqlalchemy.orm import Session
from app.domain.models import Customer
from .schemas import CustomerCreate

class CustomerService:
    def __init__(self, db: Session):
        self.db = db

    def list(self):
        return self.db.query(Customer).all()

    def create(self, data: CustomerCreate):
        obj = Customer(
            name=data.name, 
            email=data.email, 
            phone=data.phone,
            address_street=data.address_street,
            address_city=data.address_city,
            address_state=data.address_state,
            address_zip=data.address_zip,
            address_country=data.address_country
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
