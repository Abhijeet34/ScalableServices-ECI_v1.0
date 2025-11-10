from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.infrastructure.db import get_db
from app.application.service import CustomerService
from app.application.schemas import CustomerCreate, CustomerRead
from app.domain.models import Customer

router = APIRouter(prefix="/customers", tags=["customers"])

@router.get("/", response_model=list[CustomerRead])
def list_customers(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    name: Optional[str] = Query(None, max_length=100, description="Filter by customer name")
):
    """List customers with optional filtering and pagination"""
    customers = CustomerService(db).list()
    
    # Apply name filter if provided (safe string comparison, no SQL injection)
    if name:
        customers = [c for c in customers if name.lower() in c.name.lower()]
    
    # Apply pagination
    return customers[skip:skip + limit]

@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@router.post("/", response_model=CustomerRead, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    return CustomerService(db).create(payload)

@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: int, payload: CustomerCreate, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.name = payload.name
    customer.email = payload.email
    customer.phone = payload.phone
    customer.address_street = payload.address_street
    customer.address_city = payload.address_city
    customer.address_state = payload.address_state
    customer.address_zip = payload.address_zip
    customer.address_country = payload.address_country
    db.commit()
    db.refresh(customer)
    return customer

@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    db.delete(customer)
    db.commit()
    return None
