from alembic import op
import sqlalchemy as sa

revision = '0003_make_delivered_at_nullable'
down_revision = '0002_add_fk_order_id'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column(
        'shipments',
        'delivered_at',
        existing_type=sa.String(length=30),
        nullable=True
    )


def downgrade():
    op.alter_column(
        'shipments',
        'delivered_at',
        existing_type=sa.String(length=30),
        nullable=False
    )
