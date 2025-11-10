# Developer Guide

## Setup

```bash
# Clone and start
git clone <repository>
cd scalable-services
./launcher.sh start
```

## Project Structure

```
project/
├── services/         # Microservices
│   ├── gateway/      # API Gateway
│   ├── customers/    # Customer service
│   ├── products/     # Product service
│   ├── inventory/    # Inventory service
│   ├── orders/       # Orders service
│   ├── payments/     # Payments service
│   ├── shipments/    # Shipments service
│   └── dashboard/    # Monitoring UI
├── scripts/          # Automation
├── k8s/              # Kubernetes configs
└── launcher.sh       # Main entry point
```

## Development Workflow

### Hot Reload

Code changes reflect immediately - no rebuild needed.

```bash
# Edit any Python file in services/
# Changes apply automatically in running containers
```

### Run Tests

```bash
./launcher.sh test                    # Interactive menu
scripts/tests/test-suite.sh all       # All tests
scripts/tests/test-suite.sh health    # Specific test
```

### View Logs

```bash
./launcher.sh logs                    # All services
docker compose logs -f gateway        # Specific service
```

### Database Access

```bash
# PostgreSQL
docker compose exec postgres psql -U eci -d eci

# Redis
docker compose exec redis redis-cli
```

## Making Changes

### Add New Endpoint

1. Add route in `services/<service>/app/routes.py`
2. Add handler in `services/<service>/app/handlers.py`
3. Test: `curl http://localhost:8080/<service>/<endpoint>`

### Modify Database Schema

1. Edit model in `services/<service>/app/models.py`
2. Create migration: `docker compose exec <service> alembic revision --autogenerate -m "description"`
3. Apply: `docker compose exec <service> alembic upgrade head`

### Add New Service

1. Copy existing service folder
2. Modify code and dependencies
3. Add to `docker-compose.yml`
4. Register in gateway `services/gateway/app/config.py`

## Testing

### Unit Tests

```bash
docker compose exec <service> pytest tests/
```

### API Testing

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8080/auth/token -d "username=testuser" | jq -r '.access_token')

# Test endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/customers/
```

### Load Testing

```bash
scripts/tests/test-suite.sh load           # 100 requests
scripts/tests/test-suite.sh -l 1000 load   # Custom count
```

## Debugging

### Enable Debug Mode

```bash
DEBUG=1 ./launcher.sh start
```

### Check Service Health

```bash
curl http://localhost:8080/health
curl http://localhost:8080/customers/health
```

### View Container Status

```bash
docker compose ps
docker compose logs <service>
```

## Common Tasks

### Reset Database

```bash
./launcher.sh clean
./launcher.sh start
```

### Update Dependencies

```bash
# Edit services/<service>/requirements.txt
docker compose build <service>
docker compose up -d <service>
```

### Export/Import Data

```bash
# Export
scripts/platform/manage.sh export-fixtures

# Import (promote to seed data)
scripts/platform/manage.sh promote-fixtures
```

## Kubernetes Development

```bash
# Deploy to k3d
scripts/k8s/deploy-k8s.sh

# Check status
scripts/k8s/deploy-k8s.sh status

# View logs
kubectl logs -f deployment/gateway

# Delete cluster
scripts/k8s/deploy-k8s.sh delete
```

## Best Practices

- Test locally before committing
- Use meaningful commit messages
- Follow existing code style
- Update documentation for API changes
- Run full test suite before merging

## Quick Reference

```bash
# Development
./launcher.sh start              # Start platform
./launcher.sh stop               # Stop platform
./launcher.sh restart            # Restart
./launcher.sh logs               # View logs
./launcher.sh test               # Run tests

# Docker Compose
docker compose ps                # List containers
docker compose logs -f <service> # Follow logs
docker compose exec <service> sh # Shell access
docker compose restart <service> # Restart service

# Database
docker compose exec postgres psql -U eci -d eci
docker compose exec redis redis-cli

# Testing
scripts/tests/test-suite.sh all  # All tests
scripts/tests/crud-test.sh -i    # Interactive CRUD
scripts/tests/test-suite.sh load # Load testing
```