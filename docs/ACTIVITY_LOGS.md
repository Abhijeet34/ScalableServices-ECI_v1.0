# Activity Logs Feature

## Overview
The Activity Logs feature provides comprehensive audit trail and monitoring capabilities for all system operations. It includes database persistence, real-time streaming, filtering, search, and export functionality.

## Architecture

### Database Schema
Activity logs are stored in PostgreSQL with the following structure:

```sql
activity_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(50) NOT NULL,  -- CREATE, UPDATE, DELETE, PAYMENT
    entity_type VARCHAR(50) NOT NULL, -- order, customer, product, shipment, payment
    entity_id VARCHAR(100),
    user_id VARCHAR(100),
    description TEXT,
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Components

1. **Backend API** (`services/dashboard/main.py`)
   - Log persistence functions
   - REST API endpoints for querying and exporting
   - WebSocket endpoint for live streaming

2. **Frontend UI** (`services/dashboard/templates/logs.html`)
   - Interactive log viewer
   - Filtering and search
   - Real-time updates via WebSocket
   - Export functionality

3. **Database Migration** (`scripts/migrations/001_create_activity_logs.sql`)
   - Table creation
   - Indexes for performance
   - View for recent activity

## Setup

### 1. Run Database Migration

```bash
# Connect to your PostgreSQL database
psql -h postgres -U eci -d eci -f scripts/migrations/001_create_activity_logs.sql
```

Or using Docker:

```bash
docker exec -i postgres psql -U eci -d eci < scripts/migrations/001_create_activity_logs.sql
```

### 2. Restart Dashboard Service

```bash
docker-compose restart dashboard
```

## Usage

### Accessing the Logs Viewer

Navigate to: `http://localhost:9000/logs`

### Features

#### 1. Filtering
- **Event Type**: Filter by CREATE, UPDATE, DELETE, PAYMENT
- **Entity Type**: Filter by order, customer, product, shipment, payment
- **Search**: Full-text search in descriptions
- **Date Range**: Filter logs by start and end dates

#### 2. Live Streaming
- Click "Start Live Stream" to receive real-time log updates
- New logs appear at the top automatically
- Click "Stop Live Stream" to pause updates

#### 3. Export
- **CSV Export**: Download logs as CSV for analysis in Excel/spreadsheets
- **JSON Export**: Download logs as JSON for programmatic processing
- Exports respect current filters

#### 4. Log Details
- Click any log entry to expand and view full details
- Includes metadata, IP address, user agent (when available)
- Timestamp with relative time display

#### 5. Statistics
- Total logs count
- Logs from last 24 hours
- Real-time statistics updates

## API Endpoints

### GET /api/logs
Fetch activity logs with filtering and pagination.

**Query Parameters:**
- `event_type`: Filter by event type
- `entity_type`: Filter by entity type
- `entity_id`: Filter by entity ID
- `user_id`: Filter by user ID
- `start_date`: Start date (ISO format)
- `end_date`: End date (ISO format)
- `search`: Search in description
- `limit`: Number of logs (max 1000, default 100)
- `offset`: Pagination offset

**Example:**
```bash
curl -u admin:admin123 "http://localhost:9000/api/logs?event_type=CREATE&limit=50"
```

**Response:**
```json
{
  "logs": [
    {
      "id": 1,
      "timestamp": "2025-11-05T02:30:00",
      "event_type": "CREATE",
      "entity_type": "order",
      "entity_id": "55",
      "user_id": "admin",
      "description": "Created order for customer #112",
      "metadata": null,
      "ip_address": null,
      "user_agent": null
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

### GET /api/logs/export
Export logs as CSV or JSON.

**Query Parameters:** (same as `/api/logs` plus `format`)
- `format`: csv or json

**Example:**
```bash
curl -u admin:admin123 "http://localhost:9000/api/logs/export?format=csv&event_type=CREATE" -o logs.csv
```

### GET /api/logs/stats
Get log statistics.

**Example:**
```bash
curl -u admin:admin123 "http://localhost:9000/api/logs/stats"
```

**Response:**
```json
{
  "total_logs": 500,
  "recent_24h": 45,
  "by_event_type": {
    "CREATE": 200,
    "UPDATE": 150,
    "DELETE": 50,
    "PAYMENT": 100
  },
  "by_entity_type": {
    "order": 180,
    "customer": 80,
    "product": 120,
    "shipment": 70,
    "payment": 50
  }
}
```

### WebSocket /ws/logs
Real-time log streaming.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:9000/ws/logs');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('New logs:', message.data);
};
```

**Message Format:**
```json
{
  "type": "logs",
  "data": [
    {
      "id": 501,
      "timestamp": "2025-11-05T02:45:00",
      "event_type": "UPDATE",
      "entity_type": "order",
      "entity_id": "55",
      "user_id": "admin",
      "description": "Updated order status to SHIPPED",
      "metadata": {"old_status": "PROCESSING", "new_status": "SHIPPED"}
    }
  ],
  "count": 1
}
```

## Programmatic Logging

### In Dashboard Service

Use the `add_activity()` function:

```python
from main import add_activity

# Basic logging
add_activity(
    action="CREATE",
    entity_type="order",
    entity_id="123",
    user="admin",
    details="Order created successfully"
)

# With metadata
add_activity(
    action="UPDATE",
    entity_type="order",
    entity_id="123",
    user="admin",
    details="Order status updated",
    metadata={
        "old_status": "PENDING",
        "new_status": "PROCESSING",
        "items_count": 3
    }
)
```

### In Other Services

To add logging from other microservices, make HTTP POST requests to the dashboard service:

```python
import httpx

async def log_activity(event_type, entity_type, entity_id, user_id, description):
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://dashboard:9000/api/logs",
            json={
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "user_id": user_id,
                "description": description
            }
        )
```

Note: You'll need to add a POST endpoint to accept logs from other services.

## Performance Considerations

### Indexes
The following indexes are created for optimal query performance:
- `idx_activity_logs_timestamp` - For time-based queries
- `idx_activity_logs_event_type` - For event type filtering
- `idx_activity_logs_entity_type` - For entity type filtering
- `idx_activity_logs_entity_id` - For entity-specific queries
- `idx_activity_logs_user_id` - For user activity tracking
- `idx_activity_logs_metadata` - GIN index for JSON queries

### Data Retention

Consider implementing a data retention policy:

```sql
-- Delete logs older than 90 days
DELETE FROM activity_logs 
WHERE timestamp < NOW() - INTERVAL '90 days';

-- Archive to separate table before deletion
INSERT INTO activity_logs_archive 
SELECT * FROM activity_logs 
WHERE timestamp < NOW() - INTERVAL '90 days';
```

### Monitoring

Monitor log table size:

```sql
SELECT 
    pg_size_pretty(pg_total_relation_size('activity_logs')) as total_size,
    count(*) as total_rows
FROM activity_logs;
```

## Security

### Access Control
- Log viewing requires authentication (admin or guest role)
- Export functionality restricted to admin role only
- Sensitive data should not be logged in plain text

### Audit Trail
The activity logs themselves serve as an immutable audit trail:
- All operations are logged with timestamp
- User attribution for all actions
- Cannot be modified once created (implement with database constraints if needed)

## Troubleshooting

### Logs not appearing
1. Check if the migration was applied:
   ```sql
   SELECT * FROM information_schema.tables WHERE table_name = 'activity_logs';
   ```

2. Verify the dashboard service can write to the database:
   ```bash
   docker logs dashboard | grep "Error persisting activity log"
   ```

### WebSocket connection issues
1. Check browser console for errors
2. Verify WebSocket support in your environment
3. Check firewall/proxy settings

### Performance issues
1. Check index usage:
   ```sql
   EXPLAIN ANALYZE 
   SELECT * FROM activity_logs 
   WHERE event_type = 'CREATE' 
   ORDER BY timestamp DESC 
   LIMIT 100;
   ```

2. Monitor slow queries:
   ```sql
   SELECT * FROM pg_stat_statements 
   WHERE query LIKE '%activity_logs%' 
   ORDER BY mean_exec_time DESC;
   ```

## Future Enhancements

- [ ] Add POST endpoint to accept logs from other services
- [ ] Implement log aggregation and summarization
- [ ] Add alerting based on log patterns
- [ ] Implement log correlation across services
- [ ] Add machine learning for anomaly detection
- [ ] Create dashboards with log analytics
- [ ] Support for log shipping to external systems (Elasticsearch, Splunk)
- [ ] Implement log compression for older entries
- [ ] Add detailed user session tracking
