"""Simple Postgres readiness check script."""
import time
import psycopg2
import os

DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "eci")
DB_USER = os.getenv("POSTGRES_USER", "eci")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "eci")

def wait(max_attempts: int = 30, delay: float = 1.0):
    for attempt in range(1, max_attempts + 1):
        try:
            conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
            conn.close()
            print(f"Database ready after {attempt} attempt(s).")
            return True
        except Exception as e:
            print(f"DB not ready (attempt {attempt}): {e}")
            time.sleep(delay)
    raise SystemExit("Database not ready after max attempts")

if __name__ == "__main__":
    wait()