# Scripts Directory

## tests/test-suite.sh
Comprehensive testing suite
```bash
tests/test-suite.sh           # Interactive menu
tests/test-suite.sh all       # Run all tests
tests/test-suite.sh <test>    # Specific test
```
Tests: health, rest, graphql, workflow, crud, performance, load, stress, dashboard, database, security

## tests/crud-test.sh
CRUD operations testing
```bash
tests/crud-test.sh              # All CRUD tests
tests/crud-test.sh -i           # Interactive
tests/crud-test.sh -v customers # Verbose
tests/crud-test.sh -q all       # Quick test
```

## k8s/deploy-k8s.sh
Kubernetes deployment (k3d)
```bash
k8s/deploy-k8s.sh        # Deploy
k8s/deploy-k8s.sh status # Check status
k8s/deploy-k8s.sh delete # Remove
```
Auto-installs kubectl and k3d

## platform/manage.sh
Platform management
```bash
platform/manage.sh <command>
```
Commands: start, stop, restart, status, logs, seed, backup, restore

## bin/install-deps.sh
Dependency management
```bash
bin/install-deps.sh         # Check/install
bin/install-deps.sh status  # Show status
bin/install-deps.sh clear   # Clear cache
bin/install-deps.sh refresh # Force refresh
```

## Note
Use `../launcher.sh` for normal operations. Use these scripts directly for advanced control.
