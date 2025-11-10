"""add_order_number_and_payment_fields

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-02

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002_add_fks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns
    op.add_column('orders', sa.Column('order_number', sa.String(50), nullable=True))
    op.add_column('orders', sa.Column('payment_id', sa.String(100), nullable=True))
    op.add_column('orders', sa.Column('receipt_id', sa.String(100), nullable=True))
    op.add_column('orders', sa.Column('created_at', sa.DateTime(), nullable=True, default=datetime.utcnow))
    
    # Generate order_number for existing records
    op.execute("""
        UPDATE orders 
        SET order_number = 'ORD-2025-' || LPAD(id::text, 5, '0'),
            created_at = NOW()
        WHERE order_number IS NULL
    """)
    
    # Make order_number NOT NULL after populating
    op.alter_column('orders', 'order_number', nullable=False)
    op.alter_column('orders', 'created_at', nullable=False)
    
    # Create unique index on order_number
    op.create_index('idx_orders_order_number', 'orders', ['order_number'], unique=True)


def downgrade() -> None:
    op.drop_index('idx_orders_order_number')
    op.drop_column('orders', 'created_at')
    op.drop_column('orders', 'receipt_id')
    op.drop_column('orders', 'payment_id')
    op.drop_column('orders', 'order_number')
