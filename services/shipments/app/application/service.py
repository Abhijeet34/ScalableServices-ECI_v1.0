from sqlalchemy.orm import Session
from app.domain.models import Shipment
from .schemas import ShipmentCreate
from fastapi import HTTPException
from datetime import datetime

class ShipmentService:
    def __init__(self, db: Session):
        self.db = db

    def list(self):
        return self.db.query(Shipment).all()

    def create(self, data: ShipmentCreate):
        payload = data.dict(exclude_unset=True)
        # Apply safe defaults for optional fields
        now_iso = datetime.utcnow().isoformat()
        status = payload.get("status") or "PENDING"
        if not payload.get("carrier"):
            payload["carrier"] = "Standard Delivery"
        if not payload.get("tracking_no"):
            # Simple deterministic tracking number
            payload["tracking_no"] = f"TRK{payload['order_id']}{int(datetime.utcnow().timestamp())}"
        if not payload.get("shipped_at"):
            # Ensure DB non-null constraint is satisfied
            payload["shipped_at"] = now_iso
        # delivered_at can remain None until delivered
        payload["status"] = status

        obj = Shipment(**payload)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
    
    def update(self, shipment_id: int, data):
        shipment = self.db.query(Shipment).filter(Shipment.id == shipment_id).first()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")
        
        # Update only provided fields
        update_data = data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(shipment, key, value)
        
        self.db.commit()
        self.db.refresh(shipment)
        return shipment
