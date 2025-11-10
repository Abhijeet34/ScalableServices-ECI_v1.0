from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'inventory',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('product_id', sa.Integer, nullable=False, index=True),
        sa.Column('warehouse', sa.String(50), nullable=False),
        sa.Column('on_hand', sa.Integer, nullable=False),
        sa.Column('reserved', sa.Integer, nullable=False, server_default='0')
    )

def downgrade():
    op.drop_table('inventory')
