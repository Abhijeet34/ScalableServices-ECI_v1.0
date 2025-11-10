from sqlalchemy.orm import Session
from app.domain.models import Order, OrderItem
from .schemas import OrderCreate, OrderUpdate, OrderRead, OrderItemRead
from datetime import datetime
import random
import httpx
import os
from typing import Optional, List

class OrderService:
    def __init__(self, db: Session):
        self.db = db
        # Service URLs from environment or defaults
        self.customers_url = os.getenv("CUSTOMERS_SERVICE_URL", "http://customers:8000")
        self.products_url = os.getenv("PRODUCTS_SERVICE_URL", "http://products:8000")

    def _generate_order_number(self) -> str:
        """Generate a realistic order number in format ORD-YYYY-NNNNN"""
        year = datetime.now().year
        # Get count of orders this year for sequential numbering
        count = self.db.query(Order).filter(
            Order.order_number.like(f"ORD-{year}-%")
        ).count()
        return f"ORD-{year}-{(count + 1):05d}"

    def list(self):
        return self.db.query(Order).all()
    
    def get(self, order_id: int):
        return self.db.query(Order).filter(Order.id == order_id).first()

    def _fetch_customer(self, customer_id: int) -> Optional[dict]:
        """Fetch customer data from customer service."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.customers_url}/customers/{customer_id}")
                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass
        return None
    
    def _fetch_product(self, product_id: int) -> Optional[dict]:
        """Fetch product data from product service."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.products_url}/products/{product_id}")
                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass
        return None

    def create(self, data: OrderCreate):
        total = sum(i.quantity * i.unit_price for i in data.items)
        order_number = self._generate_order_number()
        
        # Fetch customer snapshot data
        customer_data = self._fetch_customer(data.customer_id)
        
        order = Order(
            order_number=order_number,
            customer_id=data.customer_id,
            order_status=data.order_status,
            payment_status=data.payment_status,
            order_total=total,
            # Store customer snapshot
            customer_name_snapshot=customer_data.get('name') if customer_data else None,
            customer_email_snapshot=customer_data.get('email') if customer_data else None,
            customer_phone_snapshot=customer_data.get('phone') if customer_data else None
        )
        self.db.add(order)
        self.db.flush()  # assign id
        
        for item in data.items:
            # Fetch product snapshot data
            product_data = self._fetch_product(item.product_id)
            
            oi = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                # Store product snapshot
                product_name_snapshot=product_data.get('name') if product_data else None,
                product_category_snapshot=product_data.get('category') if product_data else None
            )
            self.db.add(oi)
        
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def _enrich_order_with_metadata(self, order: Order) -> dict:
        """Enrich order with metadata showing if customer/product data has changed."""
        order_dict = {
            "id": order.id,
            "order_number": order.order_number,
            "customer_id": order.customer_id,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "order_total": float(order.order_total),
            "payment_id": order.payment_id,
            "receipt_id": order.receipt_id,
            "created_at": order.created_at,
            "customer_name_snapshot": order.customer_name_snapshot,
            "customer_email_snapshot": order.customer_email_snapshot,
            "customer_phone_snapshot": order.customer_phone_snapshot,
            "items": []
        }
        
        # Check customer data status
        current_customer = self._fetch_customer(order.customer_id)
        if current_customer is None:
            order_dict["customer_data_status"] = "deleted"
            order_dict["customer_current_name"] = None
            order_dict["customer_current_email"] = None
        elif (current_customer.get('name') != order.customer_name_snapshot or 
              current_customer.get('email') != order.customer_email_snapshot):
            order_dict["customer_data_status"] = "modified"
            order_dict["customer_current_name"] = current_customer.get('name')
            order_dict["customer_current_email"] = current_customer.get('email')
        else:
            order_dict["customer_data_status"] = "current"
            order_dict["customer_current_name"] = current_customer.get('name')
            order_dict["customer_current_email"] = current_customer.get('email')
        
        # Check product data for each item
        for item in order.items:
            item_dict = {
                "id": item.id,
                "product_id": item.product_id,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "product_name_snapshot": item.product_name_snapshot,
                "product_category_snapshot": item.product_category_snapshot
            }
            
            current_product = self._fetch_product(item.product_id)
            if current_product is None:
                item_dict["product_data_status"] = "deleted"
                item_dict["product_current_name"] = None
                item_dict["product_current_price"] = None
            elif (current_product.get('name') != item.product_name_snapshot or
                  float(current_product.get('price', 0)) != float(item.unit_price)):
                item_dict["product_data_status"] = "modified"
                item_dict["product_current_name"] = current_product.get('name')
                item_dict["product_current_price"] = float(current_product.get('price', 0))
            else:
                item_dict["product_data_status"] = "current"
                item_dict["product_current_name"] = current_product.get('name')
                item_dict["product_current_price"] = float(current_product.get('price', 0))
            
            order_dict["items"].append(item_dict)
        
        return order_dict

    def get_with_metadata(self, order_id: int) -> Optional[dict]:
        """Get order with enriched metadata showing data changes."""
        order = self.get(order_id)
        if not order:
            return None
        return self._enrich_order_with_metadata(order)
    
    def list_with_metadata(self) -> List[dict]:
        """List all orders with enriched metadata."""
        orders = self.list()
        return [self._enrich_order_with_metadata(order) for order in orders]

    def update(self, order_id: int, data: OrderUpdate):
        order = self.get(order_id)
        if not order:
            return None
        
        # Update only provided fields
        if data.order_status is not None:
            order.order_status = data.order_status
        if data.payment_status is not None:
            order.payment_status = data.payment_status
        if data.payment_id is not None:
            order.payment_id = data.payment_id
        if data.receipt_id is not None:
            order.receipt_id = data.receipt_id
        
        self.db.commit()
        self.db.refresh(order)
        return order
