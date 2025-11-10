"""Database migrations runner for dashboard service"""
import os
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_engine():
    """Create database engine from environment variables"""
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "eci")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "eci")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "eci")
    
    return create_engine(
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

def run_migrations():
    """Run all database migrations"""
    logger.info("Starting database migrations...")
    
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Migration 1: Create activity_logs table
            logger.info("Running migration: Create activity_logs table")
            
            # Check if table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'activity_logs'
                );
            """))
            table_exists = result.scalar()
            
            if table_exists:
                logger.info("✓ activity_logs table already exists, skipping")
            else:
                logger.info("Creating activity_logs table...")
                
                # Create table
                conn.execute(text("""
                    CREATE TABLE activity_logs (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        event_type VARCHAR(50) NOT NULL,
                        entity_type VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(100),
                        user_id VARCHAR(100),
                        description TEXT,
                        metadata JSONB,
                        ip_address INET,
                        user_agent TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                
                # Create indexes
                logger.info("Creating indexes...")
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp DESC);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_event_type ON activity_logs(event_type);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_type ON activity_logs(entity_type);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_id ON activity_logs(entity_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs(user_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_metadata ON activity_logs USING gin(metadata);"))
                
                # Create view
                logger.info("Creating recent_activity view...")
                conn.execute(text("""
                    CREATE OR REPLACE VIEW recent_activity AS
                    SELECT * FROM activity_logs
                    WHERE timestamp >= NOW() - INTERVAL '7 days'
                    ORDER BY timestamp DESC;
                """))
                
                conn.commit()
                logger.info("✓ activity_logs table created successfully")
            
            logger.info("✓ All migrations completed successfully")
            
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migrations()
