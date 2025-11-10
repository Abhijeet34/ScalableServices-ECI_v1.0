from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'products',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('sku', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('price', sa.Numeric(10,2), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true'))
    )

def downgrade():
    op.drop_table('products')
