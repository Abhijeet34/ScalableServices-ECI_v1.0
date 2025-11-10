from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String

class Base(DeclarativeBase):
    pass

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    # Shipping Address - Required for order fulfillment
    address_street: Mapped[str] = mapped_column(String(500))
    address_city: Mapped[str] = mapped_column(String(100))
    address_state: Mapped[str] = mapped_column(String(100))
    address_zip: Mapped[str] = mapped_column(String(20))
    address_country: Mapped[str] = mapped_column(String(100), default='USA')
