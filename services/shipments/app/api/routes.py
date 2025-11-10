from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.infrastructure.db import get_db
from app.application.service import ShipmentService
from app.application.schemas import ShipmentCreate, ShipmentRead
from typing import Optional
from pydantic import BaseModel

class ShipmentUpdate(BaseModel):
    status: Optional[str] = None
    carrier: Optional[str] = None
    tracking_no: Optional[str] = None
    delivered_at: Optional[str] = None

router = APIRouter(prefix="/shipments", tags=["shipments"])

@router.get("/", response_model=list[ShipmentRead])
def list_shipments(db: Session = Depends(get_db)):
    return ShipmentService(db).list()

@router.post("/", response_model=ShipmentRead, status_code=201)
def create_shipment(payload: ShipmentCreate, db: Session = Depends(get_db)):
    return ShipmentService(db).create(payload)

@router.put("/{shipment_id}", response_model=ShipmentRead)
def update_shipment(shipment_id: int, payload: ShipmentUpdate, db: Session = Depends(get_db)):
    return ShipmentService(db).update(shipment_id, payload)
