from alembic import op
import sqlalchemy as sa

revision = '0002_add_fk_product_id'
down_revision = '0001_init'
branch_labels = None
depends_on = None

def upgrade():
    op.create_foreign_key(
        'fk_inventory_product_id_products',
        source_table='inventory',
        referent_table='products',
        local_cols=['product_id'],
        remote_cols=['id'],
        ondelete='RESTRICT'
    )

def downgrade():
    op.drop_constraint('fk_inventory_product_id_products', 'inventory', type_='foreignkey')