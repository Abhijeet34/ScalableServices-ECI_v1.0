from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
APP_PATH = os.path.join(PROJECT_ROOT, 'app')
for p in (PROJECT_ROOT, APP_PATH):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    from app.domain.models import Base  # type: ignore
except ModuleNotFoundError as e:
    raise RuntimeError(f"Failed to import models for Alembic: {e}. sys.path={sys.path}")
target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, version_table='alembic_version_payments')
        with context.begin_transaction():
            context.run_migrations()
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
