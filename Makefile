# ECI E-Commerce Platform Makefile
# Cross-platform support for Mac, Linux, and Windows (with make)

# Variables
# Check for docker compose command availability
ifeq ($(shell docker compose version 2>/dev/null),)
    COMPOSE = docker-compose
else
    COMPOSE = docker compose
endif

SERVICES = postgres redis customers products inventory orders payments shipments gateway
PYTHON = python3
PROJECT_NAME = eci-platform

# Colors for output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[1;33m
NC = \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

# Detect OS
ifeq ($(OS),Windows_NT)
    DETECTED_OS := Windows
else
    DETECTED_OS := $(shell uname -s)
endif

.PHONY: help
help: ## Show this help message
	@echo "$(GREEN)ECI E-Commerce Platform - Makefile Commands$(NC)"
	@echo ""
	@echo "$(YELLOW)Usage:$(NC)"
	@echo "  make [target]"
	@echo ""
	@echo "$(YELLOW)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

.PHONY: check-docker
check-docker: ## Check if Docker is running
	@docker info > /dev/null 2>&1 || (echo "$(RED)Docker is not running. Please start Docker Desktop.$(NC)" && exit 1)
	@echo "$(GREEN)Docker is running$(NC)"

.PHONY: setup
setup: ## Initial setup - build all images
	@./scripts/platform/manage.sh setup

.PHONY: start
start: ## Start all services (safe path: rebuild + seed + health)
	@./scripts/platform/manage.sh start


.PHONY: stop
stop: ## Stop all services (one-click stop)
	@./scripts/platform/manage.sh stop

.PHONY: restart
restart: ## Restart all services
	@./scripts/platform/manage.sh restart

.PHONY: restart-service
restart-service: ## Restart specific service (use SERVICE=<name>)
	@if [ -z "$(SERVICE)" ]; then echo "$(RED)Please specify SERVICE=<name>$(NC)"; exit 1; fi
	@./scripts/platform/manage.sh restart-service $(SERVICE)

.PHONY: clean
clean: ## Stop and remove all containers, volumes, and images
	@./scripts/platform/manage.sh clean

.PHONY: seed
seed: ## Load seed data into database
	@./scripts/platform/manage.sh seed

.PHONY: logs
logs: ## Show logs from all services
	@./scripts/platform/manage.sh logs

.PHONY: logs-service
logs-service: ## Show logs for specific service (use SERVICE=<name>)
	@if [ -z "$(SERVICE)" ]; then echo "$(RED)Please specify SERVICE=<name>$(NC)"; exit 1; fi
	@./scripts/platform/manage.sh logs $(SERVICE)

.PHONY: status
status: ## Show status of all containers
	@./scripts/platform/manage.sh status

.PHONY: health-check
health-check: ## Check health of all services
	@./scripts/platform/manage.sh health

.PHONY: test
test: ## Run all tests
	@./scripts/platform/manage.sh test

.PHONY: test-api
test-api: ## Test API endpoints (REST)
	@./scripts/tests/test-suite.sh rest

.PHONY: db-shell
db-shell: ## Connect to PostgreSQL shell
	$(COMPOSE) exec postgres psql -U eci -d eci

.PHONY: redis-cli
redis-cli: ## Connect to Redis CLI
	$(COMPOSE) exec redis redis-cli

.PHONY: migrate
migrate: ## Run database migrations for all services
	@./scripts/platform/manage.sh migrate

.PHONY: token
token: ## Get authentication token
	@./scripts/platform/manage.sh token

.PHONY: info
info: ## Show service endpoints and connection info
	@./scripts/platform/manage.sh info


.PHONY: dev
dev: ## Start development environment with seed data
	@./scripts/platform/manage.sh dev

.PHONY: prod
prod: ## Start production environment
	@echo "$(GREEN)Starting production environment...$(NC)"
	COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml $(COMPOSE) up -d
	@echo "$(GREEN)Production environment started$(NC)"

.PHONY: backup
backup: ## Backup database
	@./scripts/platform/manage.sh backup

.PHONY: export-fixtures
export-fixtures: ## Export current DB tables to CSV fixtures (timestamped dir)
	@./scripts/platform/manage.sh export-fixtures

.PHONY: promote-fixtures
promote-fixtures: ## Promote latest exported fixtures into seed data (shows diff, asks to confirm)
	@./scripts/platform/manage.sh promote-fixtures

.PHONY: restore
restore: ## Restore database from backup (use BACKUP_FILE=<path>)
	@if [ -z "$(BACKUP_FILE)" ]; then echo "$(RED)Please specify BACKUP_FILE=<path>$(NC)"; exit 1; fi
	@./scripts/platform/manage.sh restore $(BACKUP_FILE)

.PHONY: lint
lint: ## Run linters on all services
	@echo "$(GREEN)Running linters...$(NC)"
	@for service in customers products inventory orders payments shipments gateway; do \
		echo "$(YELLOW)Linting $$service...$(NC)"; \
		cd $$service && ruff check . || true && cd ..; \
	done

.PHONY: format
format: ## Format code in all services
	@echo "$(GREEN)Formatting code...$(NC)"
	@for service in customers products inventory orders payments shipments gateway; do \
		echo "$(YELLOW)Formatting $$service...$(NC)"; \
		cd $$service && ruff format . || true && cd ..; \
	done

.PHONY: security-scan
security-scan: ## Run security scan on images
	@echo "$(GREEN)Running security scan...$(NC)"
	@for image in $$($(COMPOSE) config --images); do \
		echo "$(YELLOW)Scanning $$image...$(NC)"; \
		docker scout quickview $$image 2>/dev/null || echo "Docker Scout not available"; \
	done

# Development shortcuts
.PHONY: up
up: start ## Alias for start

.PHONY: down
down: stop ## Alias for stop

.PHONY: ps
ps: status ## Alias for status