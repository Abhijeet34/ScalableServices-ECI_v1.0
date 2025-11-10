from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'shipments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('order_id', sa.Integer, nullable=False),
        sa.Column('carrier', sa.String(50), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('tracking_no', sa.String(50), nullable=False),
        sa.Column('shipped_at', sa.String(30), nullable=False),
        sa.Column('delivered_at', sa.String(30), nullable=True)
    )

def downgrade():
    op.drop_table('shipments')
