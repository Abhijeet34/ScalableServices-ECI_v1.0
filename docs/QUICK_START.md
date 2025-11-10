# Quick Start Guide

## Start Platform

```bash
./launcher.sh start
```

First run: 3-5 minutes. Subsequent runs: 30-60 seconds.

## Launch Options

```bash
./launcher.sh              # Interactive menu
./launcher.sh start        # Direct start
DEBUG=1 ./launcher.sh start # Debug mode
```

## Commands

```bash
./launcher.sh start      # Start services
./launcher.sh stop       # Stop services
./launcher.sh restart    # Restart
./launcher.sh status     # Check status
./launcher.sh logs       # View logs
./launcher.sh test       # Run tests
./launcher.sh clean      # Clean everything
```

## Access

- Dashboard: http://localhost:8008
- REST API: http://localhost:8080/swagger
- GraphQL: http://localhost:8080/graphql
- Database: localhost:5432 (user/pass: eci/eci)
- Redis: localhost:6379

## Requirements

- Docker or Docker Desktop
- 4GB RAM minimum (8GB recommended)
- 10GB free disk space
- macOS, Linux, or Windows (WSL2)

## Troubleshooting

**Slow startup**: Normal on first run (3-5 minutes)

**Database issues**:
```bash
./launcher.sh clean
./launcher.sh start
```

**Debug mode**:
```bash
DEBUG=1 ./launcher.sh start
```

## Next Steps

- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Development workflow
- [QA_GUIDE.md](QA_GUIDE.md) - Testing procedures
- [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) - Monitoring
