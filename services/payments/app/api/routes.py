from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.infrastructure.db import get_db
from app.application.service import PaymentService
from app.application.schemas import PaymentCreate, PaymentRead

router = APIRouter(prefix="/payments", tags=["payments"])

@router.get("/", response_model=list[PaymentRead])
def list_payments(db: Session = Depends(get_db)):
    return PaymentService(db).list()

@router.post("/", response_model=PaymentRead, status_code=201)
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db)):
    return PaymentService(db).create(payload)
