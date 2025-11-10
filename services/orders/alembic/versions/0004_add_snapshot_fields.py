"""add_snapshot_fields_for_historical_tracking

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-02

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add customer snapshot fields to orders table
    op.add_column('orders', sa.Column('customer_name_snapshot', sa.String(200), nullable=True))
    op.add_column('orders', sa.Column('customer_email_snapshot', sa.String(255), nullable=True))
    op.add_column('orders', sa.Column('customer_phone_snapshot', sa.String(50), nullable=True))
    
    # Add product snapshot fields to order_items table
    op.add_column('order_items', sa.Column('product_name_snapshot', sa.String(200), nullable=True))
    op.add_column('order_items', sa.Column('product_category_snapshot', sa.String(100), nullable=True))


def downgrade() -> None:
    # Remove product snapshot fields from order_items table
    op.drop_column('order_items', 'product_category_snapshot')
    op.drop_column('order_items', 'product_name_snapshot')
    
    # Remove customer snapshot fields from orders table
    op.drop_column('orders', 'customer_phone_snapshot')
    op.drop_column('orders', 'customer_email_snapshot')
    op.drop_column('orders', 'customer_name_snapshot')
