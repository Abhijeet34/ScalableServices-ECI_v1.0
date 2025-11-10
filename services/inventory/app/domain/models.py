from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, ForeignKey

class Base(DeclarativeBase):
    pass

class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Product ID - no foreign key in microservices architecture
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse: Mapped[str] = mapped_column(String(50))
    on_hand: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
