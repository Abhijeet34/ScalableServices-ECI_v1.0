# Dashboard Guide

## Access
- URL: http://localhost:8008
- Start platform: `./launcher.sh start`

## User Credentials

**Admin** (full access)
- Username: `admin`
- Password: `admin123`
- Can create orders, reset metrics

**Guest** (read-only)
- Username: `guest`
- Password: `guest123`
- Can view metrics, test services

## Features

### Real-Time Metrics
Updates every 2 seconds:
- Total Orders
- Failed Payments
- Average Latency (ms)
- Stockouts

### Service Health
7 monitored services: Customers, Products, Inventory, Orders, Payments, Shipments, Gateway

**Status Indicators**:
- Green: healthy (200 OK)
- Red: unhealthy/unreachable
- Orange: timeout/error

### Control Panel
- **Create Order**: Demo order (admin only)
- **Test Services**: Health check all services
- **Reset Metrics**: Reset counters (admin only)
- **API Docs**: Opens Swagger UI (http://localhost:8080/swagger)

## API Token

Get token for Swagger:
```bash
curl -X POST http://localhost:8080/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser"
```

Use `access_token` value in Swagger's Authorize dialog.

## Troubleshooting

### Login fails
Verify username/password (case-sensitive)

### Services unhealthy
```bash
docker ps
docker-compose restart
docker logs scalableservices-<service-name>-1
```

### Gateway shows red
```bash
curl -I http://localhost:8080/swagger
```
Expect 307 or 200 response

### API Docs won't load
```bash
docker ps | grep gateway
```
Ensure port 8080 not blocked

## Security (Production)

1. Change default credentials in `services/dashboard/main.py`
2. Use environment variables for secrets
3. Replace HTTP Basic Auth with OAuth2
4. Enable HTTPS/TLS
5. Update JWT_SECRET to cryptographically secure value
