from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Numeric, DateTime
from datetime import datetime
from typing import Optional

class Base(DeclarativeBase):
    pass

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # Store customer_id as integer (no FK - microservices pattern)
    customer_id: Mapped[int]
    order_status: Mapped[str] = mapped_column(String(30))
    payment_status: Mapped[str] = mapped_column(String(30))
    order_total: Mapped[float] = mapped_column(Numeric(10,2))
    payment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    receipt_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Customer snapshot data (captured at order creation time)
    customer_name_snapshot: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    customer_email_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_phone_snapshot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    # Store product_id as integer (no FK - microservices pattern)
    product_id: Mapped[int]
    sku: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[int]
    unit_price: Mapped[float] = mapped_column(Numeric(10,2))
    # Product snapshot data (captured at order creation time)
    product_name_snapshot: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    product_category_snapshot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    order: Mapped[Order] = relationship("Order", back_populates="items")
