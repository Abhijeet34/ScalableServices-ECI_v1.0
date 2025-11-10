from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('customer_id', sa.Integer, nullable=False),
        sa.Column('order_status', sa.String(30), nullable=False),
        sa.Column('payment_status', sa.String(30), nullable=False),
        sa.Column('order_total', sa.Numeric(10,2), nullable=False)
    )
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('order_id', sa.Integer, nullable=False),
        sa.Column('product_id', sa.Integer, nullable=False),
        sa.Column('sku', sa.String(50), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('unit_price', sa.Numeric(10,2), nullable=False)
    )

def downgrade():
    op.drop_table('order_items')
    op.drop_table('orders')
