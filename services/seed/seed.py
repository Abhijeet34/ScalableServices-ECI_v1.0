import csv
from pathlib import Path
from sqlalchemy import create_engine, text
import time
from functools import lru_cache
from pydantic_settings import BaseSettings

MAX_ATTEMPTS = 30
SLEEP_SECONDS = 2

def table_exists(conn, table: str) -> bool:
    res = conn.execute(text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name=:t
        )
    """), {"t": table}).scalar()
    return bool(res)

def get_table_columns(conn, table: str) -> set:
    rows = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t
    """), {"t": table}).fetchall()
    return {r[0] for r in rows}

class Settings(BaseSettings):
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "eci"
    POSTGRES_USER: str = "eci"
    POSTGRES_PASSWORD: str = "eci"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
engine = create_engine(f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")

DATA_DIR = Path("eci_seed_data")

TABLE_FILES = {
    "customers": "eci_customers.csv",
    "products": "eci_products.csv",
    "inventory": "eci_inventory.csv",
    "orders": "eci_orders.csv",
    "order_items": "eci_order_items.csv",
    "payments": "eci_payments.csv",
    "shipments": "eci_shipments.csv",
}

# Simple column rename mapping from CSV -> DB column
COLUMN_RENAMES = {
    "customers": {"customer_id": "id"},
    "products": {"product_id": "id"},
    "inventory": {"inventory_id": "id"},
    "orders": {"order_id": "id"},
    "order_items": {"order_item_id": "id"},
    "payments": {"payment_id": "id"},
    "shipments": {"shipment_id": "id"},
}

# Simple naive loader (assumes tables already exist). For initial run you can rely on service startup migrations (create_all).

def load_table(table: str, file: str):
    path = DATA_DIR / file
    with engine.connect() as conn, open(path, newline="", encoding="utf-8") as f:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        # Wait for table availability
        attempt = 0
        while attempt < MAX_ATTEMPTS and not table_exists(conn, table):
            attempt += 1
            if attempt == 1:
                print(f"Waiting for table '{table}' to exist...")
            time.sleep(SLEEP_SECONDS)
        if not table_exists(conn, table):
            print(f"Table '{table}' not found after waiting; skipping {file}.")
            return
        existing_cols = get_table_columns(conn, table)
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return
        rename_map = COLUMN_RENAMES.get(table, {})
        transformed = []
        for r in rows:
            new_r = {}
            for k, v in r.items():
                target_col = rename_map.get(k, k)
                if target_col in existing_cols:  # drop unknown columns silently
                    new_r[target_col] = v
            transformed.append(new_r)
        # Align columns after transformation (exclude any columns not in table by attempting insert & ignoring errors)
        sample_cols = transformed[0].keys()
        placeholders = ",".join([f":{c}" for c in sample_cols])
        col_list = ",".join(sample_cols)
        stmt = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING")
        for r in transformed:
            try:
                conn.execute(stmt, r)
            except Exception as e:
                print(f"Row insert skipped for table {table}: {e}")
        print(f"Loaded {len(rows)} rows into {table}")

def main():
    for table, file in TABLE_FILES.items():
        load_table(table, file)
    
    # Reset sequences to max ID values
    print("Resetting sequences...")
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        for table in TABLE_FILES.keys():
            try:
                # Reset sequence to max id
                conn.execute(text(f"SELECT setval('{table}_id_seq', (SELECT COALESCE(MAX(id), 1) FROM {table}))"))
                print(f"  Reset {table}_id_seq")
            except Exception as e:
                print(f"  Warning: Could not reset sequence for {table}: {e}")
        print("Analyzing tables for updated statistics...")
        for table in TABLE_FILES.keys():
            try:
                conn.execute(text(f"ANALYZE {table}"))
                print(f"  Analyzed {table}")
            except Exception as e:
                print(f"  Warning: Could not analyze {table}: {e}")
        try:
            conn.execute(text("REINDEX DATABASE eci"))
            print("Reindexed database")
        except Exception as e:
            print(f"Warning: Could not reindex database: {e}")
    print("Sequence reset and stats updated.")

if __name__ == "__main__":
    main()
