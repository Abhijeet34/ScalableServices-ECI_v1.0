# QA Testing Guide

## Quick Start

### Docker Compose
```bash
./launcher.sh start
open http://localhost:8008         # Dashboard
open http://localhost:8080/swagger # API Docs
```

### Kubernetes
```bash
../scripts/k8s/deploy-k8s.sh        # Deploy
../scripts/k8s/deploy-k8s.sh status # Get URLs
```

## Testing Methods

### Dashboard Testing
http://localhost:8008
- Login: `admin` / `admin123`
- Click "Test All Services"
- Create test orders

### API Testing
**Swagger**: http://localhost:8080/swagger
- Click "Authorize", use token from launcher output
- Test any endpoint

**GraphQL**: http://localhost:8080/graphql
```graphql
query {
  customers { id name email }
}
```

### Automated Tests
```bash
./launcher.sh test                 # All tests
../scripts/tests/test-suite.sh all # Direct
```

Test categories: `health`, `rest`, `graphql`, `workflow`, `performance`, `load`, `dashboard`, `database`

## Workflows

### Create Order (Dashboard)
1. http://localhost:8008, login as admin
2. Click "Create Test Order"
3. Verify metrics update

### Create Order (API)
1. POST `/customers/` - create customer
2. POST `/products/` - create product
3. POST `/inventory/` - add inventory
4. POST `/orders/` - create order
5. GET `/orders/{id}` - verify

### Performance Testing
```bash
../scripts/tests/test-suite.sh performance # Quick test
../scripts/tests/test-suite.sh load        # 100 concurrent
```

## Expected Results

### Service Health
- Gateway: http://localhost:8080/health (200 OK)
- Dashboard: http://localhost:8008/health (200 OK)

### Response Times
- Health checks: < 100ms
- Queries: < 200ms
- Operations: < 500ms

## Troubleshooting

### Services won't start
```bash
docker ps
./launcher.sh restart
```

### Can't access dashboard
```bash
curl http://localhost:8008/health
docker-compose logs dashboard
```

### Tests failing
```bash
./launcher.sh validate
./launcher.sh stop && ./launcher.sh start
```

## Commands

```bash
./launcher.sh start                 # Start
./launcher.sh stop                  # Stop
./launcher.sh test                  # Test
./launcher.sh status                # Status
docker-compose logs -f [service]    # Logs
../scripts/k8s/deploy-k8s.sh        # Deploy K8s
../scripts/k8s/deploy-k8s.sh status # K8s status
../scripts/k8s/deploy-k8s.sh delete # Delete K8s
```
