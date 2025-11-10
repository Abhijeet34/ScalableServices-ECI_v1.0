"""add seller fields

Revision ID: 0002
Revises: 0001
Create Date: 2025-11-02 03:36:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001_init'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('seller_name', sa.String(length=200), nullable=True))
    op.add_column('products', sa.Column('seller_location', sa.String(length=100), nullable=True))
    op.add_column('products', sa.Column('seller_member_since', sa.Date(), nullable=True))
    op.add_column('products', sa.Column('seller_response_time', sa.String(length=50), nullable=True))
    op.add_column('products', sa.Column('seller_shipping_policy', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('seller_return_policy', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('seller_badge', sa.String(length=50), nullable=True))
    op.add_column('products', sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column('products', sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))

def downgrade():
    op.drop_column('products', 'updated_at')
    op.drop_column('products', 'created_at')
    op.drop_column('products', 'seller_badge')
    op.drop_column('products', 'seller_return_policy')
    op.drop_column('products', 'seller_shipping_policy')
    op.drop_column('products', 'seller_response_time')
    op.drop_column('products', 'seller_member_since')
    op.drop_column('products', 'seller_location')
    op.drop_column('products', 'seller_name')
    op.drop_column('products', 'description')
