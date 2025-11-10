# ECI E-Commerce Platform

Microservices platform demonstrating scalable architecture with FastAPI, Docker, and Kubernetes.

## Quick Start

```bash
# Start all services
./launcher.sh

# Select option 1 from menu
```

First run takes 3-5 minutes (Docker setup). Subsequent runs: 30-60 seconds.

## Architecture

### Services

| Service   | Port     | Purpose                                |
|-----------|----------|----------------------------------------|
| Gateway   | 8080     | API Gateway with JWT auth and caching  |
| Dashboard | 8008     | Real-time monitoring UI                |
| Customers | Internal | Customer management                    |
| Products  | Internal | Product catalog                        |
| Inventory | Internal | Stock management                       |
| Orders    | Internal | Order processing                       |
| Payments  | Internal | Payment handling                       |
| Shipments | Internal | Delivery tracking                      |

### Infrastructure

- **Database**: PostgreSQL 16
- **Cache**: Redis 7
- **Container**: Docker / Docker Compose
- **Orchestration**: Kubernetes (k3d)

## Commands

```bash
./launcher.sh               # Interactive menu
./launcher.sh start         # Start all services
./launcher.sh stop          # Stop all services
./launcher.sh restart       # Restart services
./launcher.sh status        # Check status
./launcher.sh test          # Run tests
```

## API Access

- Dashboard: http://localhost:8008
- REST API: http://localhost:8080/swagger
- GraphQL: http://localhost:8080/graphql
- Health: http://localhost:8080/health

## Testing

```bash
# Interactive test menu
./launcher.sh test

# Direct test commands
scripts/tests/test-suite.sh all         # Run all tests
scripts/tests/test-suite.sh health      # Health checks
scripts/tests/test-suite.sh rest        # REST APIs
scripts/tests/test-suite.sh graphql     # GraphQL
scripts/tests/test-suite.sh workflow    # Order workflow
scripts/tests/test-suite.sh performance # Performance tests
scripts/tests/test-suite.sh load        # Load testing
```


## Kubernetes Deployment

```bash
# Deploy to k3d cluster
scripts/k8s/deploy-k8s.sh

# Check status
scripts/k8s/deploy-k8s.sh status

# Remove cluster
scripts/k8s/deploy-k8s.sh delete
```

Access after deployment:
- Gateway: http://localhost:30080
- Dashboard: http://localhost:30008

## System Requirements

- RAM: 4GB minimum (8GB recommended)
- Disk: 20GB free space
- OS: macOS, Linux, Windows (WSL2)
- Docker or Docker Desktop

## Documentation

- [Quick Start Guide](docs/QUICK_START.md) - Setup and basic usage
- [Developer Guide](docs/DEVELOPER_GUIDE.md) - Development workflow
- [QA Testing Guide](docs/QA_GUIDE.md) - Testing procedures
- [Dashboard Guide](docs/DASHBOARD_GUIDE.md) - Monitoring features
- [Kubernetes Guide](k8s/README.md) - K8s deployment

## Project Structure

```
project/
├── services/         # Microservices
├── scripts/          # Automation scripts
├── k8s/              # Kubernetes configs
├── docs/             # Documentation
└── launcher.sh       # Main entry point
```
