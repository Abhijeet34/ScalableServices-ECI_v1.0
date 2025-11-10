from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.infrastructure.db import get_db
from app.application.service import InventoryService
from app.application.schemas import InventoryCreate, InventoryRead
from app.domain.models import Inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])

@router.get("/", response_model=list[InventoryRead])
def list_inventory(db: Session = Depends(get_db)):
    return InventoryService(db).list()

@router.post("/", response_model=InventoryRead, status_code=201)
def create_inventory(payload: InventoryCreate, db: Session = Depends(get_db)):
    return InventoryService(db).create(payload)

@router.put("/{inventory_id}", response_model=InventoryRead)
def update_inventory(inventory_id: int, payload: InventoryCreate, db: Session = Depends(get_db)):
    inventory = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    inventory.product_id = payload.product_id
    inventory.warehouse = payload.warehouse
    inventory.on_hand = payload.on_hand
    inventory.reserved = payload.reserved
    db.commit()
    db.refresh(inventory)
    return inventory
