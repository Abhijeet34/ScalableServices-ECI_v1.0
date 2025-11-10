-- Activity Logs Table
CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(50) NOT NULL,  -- CREATE, UPDATE, DELETE, PAYMENT, etc.
    entity_type VARCHAR(50) NOT NULL, -- order, customer, product, shipment, payment
    entity_id VARCHAR(100),
    user_id VARCHAR(100),
    description TEXT,
    metadata JSONB,  -- Flexible field for additional context
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_event_type ON activity_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_type ON activity_logs(entity_type);
CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_id ON activity_logs(entity_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_metadata ON activity_logs USING gin(metadata);

-- Create a view for recent activity (last 7 days)
CREATE OR REPLACE VIEW recent_activity AS
SELECT * FROM activity_logs
WHERE timestamp >= NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;
