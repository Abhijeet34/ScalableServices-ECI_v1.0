from alembic import op
import sqlalchemy as sa

revision = '0002_add_fk_order_id'
down_revision = '0001_init'
branch_labels = None
depends_on = None

def _wait_for_table(table_name: str, timeout: int = 30):
    from sqlalchemy import text
    bind = op.get_bind()
    for _ in range(timeout):
        exists = bind.execute(text("SELECT to_regclass(:t)"), {"t": table_name}).scalar()
        if exists:
            return True
        import time
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for table '{table_name}' to exist for FK creation")

def upgrade():
    _wait_for_table('orders')
    op.create_foreign_key(
        'fk_shipments_order_id_orders',
        source_table='shipments',
        referent_table='orders',
        local_cols=['order_id'],
        remote_cols=['id'],
        ondelete='RESTRICT'
    )

def downgrade():
    op.drop_constraint('fk_shipments_order_id_orders', 'shipments', type_='foreignkey')