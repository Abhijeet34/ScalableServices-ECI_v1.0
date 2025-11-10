from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('address_street', sa.String(length=500), nullable=True),
        sa.Column('address_city', sa.String(length=100), nullable=True),
        sa.Column('address_state', sa.String(length=100), nullable=True),
        sa.Column('address_zip', sa.String(length=20), nullable=True),
        sa.Column('address_country', sa.String(length=100), nullable=True, server_default='USA')
    )

def downgrade():
    op.drop_table('customers')
