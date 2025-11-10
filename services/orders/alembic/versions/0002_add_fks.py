from alembic import op
import sqlalchemy as sa

revision = '0002_add_fks'
down_revision = '0001_init'
branch_labels = None
depends_on = None

def upgrade():
    # orders.customer_id -> customers.id
    op.create_foreign_key(
        'fk_orders_customer_id_customers',
        source_table='orders',
        referent_table='customers',
        local_cols=['customer_id'],
        remote_cols=['id'],
        ondelete='RESTRICT'
    )
    # order_items.order_id -> orders.id
    op.create_foreign_key(
        'fk_order_items_order_id_orders',
        source_table='order_items',
        referent_table='orders',
        local_cols=['order_id'],
        remote_cols=['id'],
        ondelete='CASCADE'
    )
    # order_items.product_id -> products.id
    op.create_foreign_key(
        'fk_order_items_product_id_products',
        source_table='order_items',
        referent_table='products',
        local_cols=['product_id'],
        remote_cols=['id'],
        ondelete='RESTRICT'
    )

def downgrade():
    op.drop_constraint('fk_order_items_product_id_products', 'order_items', type_='foreignkey')
    op.drop_constraint('fk_order_items_order_id_orders', 'order_items', type_='foreignkey')
    op.drop_constraint('fk_orders_customer_id_customers', 'orders', type_='foreignkey')