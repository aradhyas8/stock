# Multi-Bagger Research System
# Cross-platform task runner using Make

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
RESET := \033[0m

# Project variables
PROJECT_NAME := multi-bagger-research
PYTHON_VERSION := 3.10
SOURCE_DIR := src
TEST_DIR := tests

# Check if uv is installed
UV_EXISTS := $(shell command -v uv 2> /dev/null)

.PHONY: help
help: ## Show this help message
	@echo "$(BLUE)Multi-Bagger Research System$(RESET)"
	@echo "=============================="
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make setup          # First-time setup"
	@echo "  make check          # Run linting and tests"  
	@echo "  make run-monthly    # Execute monthly pipeline"
	@echo ""

.PHONY: install-uv
install-uv: ## Install uv package manager if not present
ifndef UV_EXISTS
	@echo "$(YELLOW)Installing uv package manager...$(RESET)"
ifeq ($(OS),Windows_NT)
	@powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
else
	@curl -LsSf https://astral.sh/uv/install.sh | sh
endif
	@echo "$(GREEN)uv installed successfully$(RESET)"
else
	@echo "$(GREEN)uv is already installed$(RESET)"
endif

.PHONY: setup
setup: install-uv ## Complete project setup (install deps, create config, init db)
	@echo "$(BLUE)Setting up Multi-Bagger Research System...$(RESET)"
	@uv sync --dev
	@if [ ! -f config.yml ]; then \
		echo "$(YELLOW)Creating config.yml from template...$(RESET)"; \
		cp config.example.yml config.yml; \
	fi
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env from template...$(RESET)"; \
		cp .env.example .env; \
	fi
	@echo "$(GREEN)✅ Setup complete!$(RESET)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(RESET)"
	@echo "1. Edit config.yml for your preferences"
	@echo "2. Add API keys to .env file"  
	@echo "3. Run 'make check' to verify installation"

.PHONY: clean
clean: ## Remove build artifacts and caches
	@echo "$(YELLOW)Cleaning build artifacts...$(RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf build/ dist/ .coverage htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/ 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup complete$(RESET)"

.PHONY: format
format: ## Format code using black and ruff
	@echo "$(BLUE)Formatting code...$(RESET)"
	@uv run black $(SOURCE_DIR) $(TEST_DIR)
	@uv run ruff --fix $(SOURCE_DIR) $(TEST_DIR)
	@echo "$(GREEN)✅ Code formatted$(RESET)"

.PHONY: lint
lint: ## Run linting with ruff and mypy
	@echo "$(BLUE)Running linters...$(RESET)"
	@uv run ruff check $(SOURCE_DIR) $(TEST_DIR)
	@uv run mypy $(SOURCE_DIR)
	@echo "$(GREEN)✅ Linting passed$(RESET)"

.PHONY: test
test: ## Run tests with pytest
	@echo "$(BLUE)Running tests...$(RESET)"
	@uv run pytest $(TEST_DIR) -v --tb=short
	@echo "$(GREEN)✅ Tests passed$(RESET)"

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(RESET)"
	@uv run pytest $(TEST_DIR) --cov=$(SOURCE_DIR) --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)✅ Tests with coverage complete$(RESET)"
	@echo "Coverage report: htmlcov/index.html"

.PHONY: check
check: lint test ## Run all quality checks (lint + test)
	@echo "$(GREEN)✅ All checks passed!$(RESET)"

.PHONY: run-monthly
run-monthly: ## Execute monthly multi-bagger pipeline
	@echo "$(BLUE)🚀 Starting Monthly Multi-Bagger Hunt...$(RESET)"
	@echo ""
	@mkdir -p snapshots/$(shell date +%Y-%m)/reports snapshots/$(shell date +%Y-%m)/logs
	@uv run python -m multibagger.cli.main monthly --output-dir snapshots/$(shell date +%Y-%m)
	@echo ""
	@echo "$(GREEN)✅ Monthly run complete$(RESET)"
	@echo "Results saved to: snapshots/$(shell date +%Y-%m)/"

.PHONY: monitor
monitor: ## Run daily monitoring checks
	@echo "$(BLUE)🔍 Running portfolio monitoring...$(RESET)"
	@uv run python -m multibagger.cli.main monitor
	@echo "$(GREEN)✅ Monitoring complete$(RESET)"

.PHONY: universe
universe: ## Generate/refresh stock universe
	@echo "$(BLUE)🌍 Building stock universe...$(RESET)"
	@uv run python -m multibagger.cli.main universe --refresh
	@echo "$(GREEN)✅ Universe updated$(RESET)"

.PHONY: screen
screen: ## Run screening pipeline only
	@echo "$(BLUE)🔬 Running stock screening...$(RESET)"  
	@uv run python -m multibagger.cli.main screen
	@echo "$(GREEN)✅ Screening complete$(RESET)"

.PHONY: install-git-hooks
install-git-hooks: ## Install pre-commit git hooks
	@echo "$(BLUE)Installing git hooks...$(RESET)"
	@uv run pre-commit install
	@echo "$(GREEN)✅ Git hooks installed$(RESET)"

.PHONY: dev-server
dev-server: ## Start development server (if applicable)
	@echo "$(BLUE)Starting development mode...$(RESET)"
	@echo "Development server not implemented yet"

.PHONY: build
build: ## Build distribution packages
	@echo "$(BLUE)Building distribution...$(RESET)"
	@uv build
	@echo "$(GREEN)✅ Build complete$(RESET)"

.PHONY: deps-update
deps-update: ## Update all dependencies
	@echo "$(BLUE)Updating dependencies...$(RESET)"
	@uv lock --upgrade
	@echo "$(GREEN)✅ Dependencies updated$(RESET)"

.PHONY: deps-audit
deps-audit: ## Check for security vulnerabilities
	@echo "$(BLUE)Auditing dependencies...$(RESET)"
	@uv run pip-audit
	@echo "$(GREEN)✅ Security audit complete$(RESET)"

# Development targets
.PHONY: shell
shell: ## Open interactive shell with project environment
	@uv run python

.PHONY: notebook
notebook: ## Start Jupyter notebook (if installed)
	@uv run jupyter notebook

# Deployment targets
.PHONY: cron-install
cron-install: ## Install monthly cron job
	@echo "$(YELLOW)Adding monthly cron job...$(RESET)"
	@echo "0 0 1 * * cd $(PWD) && make run-monthly" | crontab -
	@echo "$(GREEN)✅ Cron job installed (runs 1st of each month at midnight)$(RESET)"

.PHONY: cron-uninstall  
cron-uninstall: ## Remove monthly cron job
	@echo "$(YELLOW)Removing cron job...$(RESET)"
	@crontab -l | grep -v "make run-monthly" | crontab -
	@echo "$(GREEN)✅ Cron job removed$(RESET)"

# Utility targets
.PHONY: logs
logs: ## Show recent application logs
	@tail -f logs/multibagger.log 2>/dev/null || echo "No logs found. Run the application first."

.PHONY: status
status: ## Show system status and health checks
	@echo "$(BLUE)Multi-Bagger Research System Status$(RESET)"
	@echo "=================================="
	@echo "Python: $(shell uv run python --version)"
	@echo "uv: $(shell uv --version)"
	@echo "Environment: $(shell if [ -f .venv/pyvenv.cfg ]; then echo "Active"; else echo "Not found"; fi)"
	@echo "Config: $(shell if [ -f config.yml ]; then echo "✅ Found"; else echo "❌ Missing"; fi)"
	@echo "Database: $(shell if [ -f data/multibagger.db ]; then echo "✅ Found"; else echo "❌ Missing"; fi)"
	@echo ""

# Aliases for common typos
.PHONY: tets test-cov tests
tests: test
tets: test
