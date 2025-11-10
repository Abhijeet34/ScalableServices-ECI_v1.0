from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.infrastructure.db import get_db
from app.application.service import ProductService
from app.application.schemas import ProductCreate, ProductRead
from app.domain.models import Product

router = APIRouter(prefix="/products", tags=["products"])

@router.get("/", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db)):
    return ProductService(db).list()

@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.post("/", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    return ProductService(db).create(payload)

@router.put("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductCreate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Update all fields from payload
    product.name = payload.name
    product.category = payload.category
    product.price = payload.price
    product.is_active = payload.is_active
    product.description = payload.description
    
    # Update seller information
    product.seller_name = payload.seller_name
    product.seller_response_time = payload.seller_response_time
    product.seller_badge = payload.seller_badge
    
    # Update optional seller fields
    product.seller_location = payload.seller_location
    product.seller_member_since = payload.seller_member_since
    product.seller_shipping_policy = payload.seller_shipping_policy
    product.seller_return_policy = payload.seller_return_policy
    
    # Handle SKU update (might be auto-generated)
    if payload.sku:
        product.sku = payload.sku
    
    db.commit()
    db.refresh(product)
    return product

@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return None
