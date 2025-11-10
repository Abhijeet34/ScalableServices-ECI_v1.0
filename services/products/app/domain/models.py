from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Numeric, Boolean, Text, DateTime, func
from typing import Optional
import datetime

class Base(DeclarativeBase):
    pass

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Numeric(10,2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Seller Information - Required for marketplace functionality
    seller_name: Mapped[str] = mapped_column(String(200))
    seller_location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seller_member_since: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)
    seller_response_time: Mapped[str] = mapped_column(String(50))
    seller_shipping_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_return_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_badge: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
