from sqlalchemy.orm import Session
from app.domain.models import Product
from .schemas import ProductCreate
import random
import string

class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_sku(self) -> str:
        """Generate a unique SKU in format: SKU#### (sequential)"""
        # Get the highest existing SKU number
        latest_product = self.db.query(Product).filter(
            Product.sku.like('SKU%')
        ).order_by(Product.sku.desc()).first()
        
        if latest_product and latest_product.sku:
            # Extract the number from SKU format (e.g., SKU0001 -> 1)
            try:
                last_num = int(latest_product.sku.replace('SKU', ''))
                next_num = last_num + 1
            except (ValueError, AttributeError):
                # Fallback if SKU format is unexpected
                next_num = 1
        else:
            next_num = 1
        
        # Format as SKU#### with zero-padding
        return f"SKU{next_num:04d}"

    def list(self):
        return self.db.query(Product).all()

    def create(self, data: ProductCreate):
        # Auto-generate SKU if not provided
        product_data = data.dict()
        if not product_data.get('sku'):
            product_data['sku'] = self._generate_sku()
        
        obj = Product(**product_data)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
