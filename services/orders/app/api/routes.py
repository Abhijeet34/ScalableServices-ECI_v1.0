from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.infrastructure.db import get_db
from app.application.service import OrderService
from app.application.schemas import OrderCreate, OrderRead, OrderUpdate
from app.domain.models import Order

router = APIRouter(prefix="/orders", tags=["orders"])

@router.get("/", response_model=list[OrderRead])
def list_orders(db: Session = Depends(get_db)):
    """List all orders (fast, without metadata enrichment)."""
    return OrderService(db).list()

@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """Get a specific order."""
    order = OrderService(db).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.post("/", response_model=OrderRead, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    return OrderService(db).create(payload)

@router.put("/{order_id}", response_model=OrderRead)
def update_order(order_id: int, payload: OrderUpdate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Only block changes to payment-related fields if payment is finalized
    if order.payment_status in ['COMPLETED', 'FAILED']:
        touching_payment_fields = any([
            payload.payment_status is not None,
            payload.payment_id is not None,
            payload.receipt_id is not None,
        ])
        if touching_payment_fields:
            raise HTTPException(
                status_code=403,
                detail="Cannot modify payment fields after payment has been completed or failed"
            )
    
    order = OrderService(db).update(order_id, payload)
    return order

@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Block deletion if payment is already completed or failed
    if order.payment_status in ['COMPLETED', 'FAILED']:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete order after payment has been completed or failed"
        )
    
    db.delete(order)
    db.commit()
    return None
