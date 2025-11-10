from typing import Optional
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String

class Base(DeclarativeBase):
    pass

class Shipment(Base):
    __tablename__ = "shipments"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Link shipment to order (no FK in microservices architecture)
    order_id: Mapped[int] = mapped_column()
    carrier: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))
    tracking_no: Mapped[str] = mapped_column(String(50))
    shipped_at: Mapped[str] = mapped_column(String(30))
    # delivered_at can be null until the shipment is delivered
    delivered_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
