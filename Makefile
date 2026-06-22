# QwenPaw Development Makefile

.PHONY: help sync app-start app test test-unit test-contract test-integration test-channel test-channel-contract coverage-full check-contracts clean quick test-base-core
.DEFAULT_GOAL := help

# Python path
UV := uv
NPM := npm
PYTHON := python
PYTEST := python -m pytest
CONSOLE_DIR := console
CONSOLE_PACKAGE_DIR := src/qwenpaw/console
UV_SYNC_ARGS ?=
HOST ?=
PORT ?=
APP_ARGS ?=

APP_HOST_ARGS := $(if $(HOST),--host $(HOST),)
APP_PORT_ARGS := $(if $(PORT),--port $(PORT),)
APP_CLI_ARGS := $(filter-out app-start app,$(MAKECMDGOALS))

ifneq (,$(filter app-start app,$(MAKECMDGOALS)))
.PHONY: $(APP_CLI_ARGS)
$(APP_CLI_ARGS):
	@:
endif

help:
	@echo "QwenPaw 常用命令"
	@echo ""
	@echo "  make sync"
	@echo "      重新执行 uv sync、console/npm install、前端构建，并拷贝控制台产物。"
	@echo ""
	@echo "  make app-start"
	@echo "      启动 QwenPaw APP，使用 qwenpaw app 的默认 host/port。"
	@echo ""
	@echo "  make app-start HOST=0.0.0.0 PORT=8088"
	@echo "      指定监听 host 和 port。"
	@echo ""
	@echo "  make app-start APP_ARGS=\"--reload --log-level debug\""
	@echo "      透传其他 qwenpaw app 参数。"
	@echo ""
	@echo "  make app-start app -- --host 0.0.0.0 --port 8088"
	@echo "      CLI 风格参数写法；注意 --host 前需要先写 make 的参数分隔符 --。"
	@echo ""
	@echo "  make test | make test-unit | make test-integration | make quick"
	@echo "      运行测试。"

# Refresh local Python and frontend dependencies, then rebuild bundled console assets.
sync:
	$(UV) sync $(UV_SYNC_ARGS)
	cd $(CONSOLE_DIR) && $(NPM) install
	cd $(CONSOLE_DIR) && $(NPM) run build
	mkdir -p $(CONSOLE_PACKAGE_DIR)
	cp -R $(CONSOLE_DIR)/dist/. $(CONSOLE_PACKAGE_DIR)/

# Start QwenPaw from the uv-managed local environment.
app-start:
	$(UV) run qwenpaw app $(APP_HOST_ARGS) $(APP_PORT_ARGS) $(APP_ARGS) $(APP_CLI_ARGS)

app: app-start

# Run all tests
test:
	$(PYTEST) tests/ -v --tb=short -q

# Unit tests only
test-unit:
	$(PYTEST) tests/unit/ -v --tb=short

# Contract tests (interface compliance)
test-contract:
	$(PYTEST) tests/contract/ -v --tb=short

# Integration tests
test-integration:
	$(PYTEST) tests/integration/ -v --tb=short

# Full coverage (all modules)
coverage-full:
	$(PYTEST) tests/unit/ tests/integration/ -v \
		--cov=src/qwenpaw \
		--cov-report=term-missing \
		--cov-report=html

# Check contract coverage for all channels
check-contracts:
	$(PYTHON) scripts/check_channel_contracts.py

# Clean generated files
clean:
	rm -rf htmlcov/ .pytest_cache/
	rm -f coverage.xml coverage-sa.xml .coverage

# Quick check (fast feedback)
quick:
	$(PYTEST) tests/unit/ -x -q --tb=line

# Channel-specific tests
test-channel:
	@echo "Running Channel unit tests..."
	$(PYTEST) tests/unit/channels/ -v --tb=short

test-channel-contract:
	@echo "Running Channel contract tests..."
	$(PYTEST) tests/contract/channels/ -v --tb=short

# BaseChannel core unit tests (optional, not enforced)
test-base-core:
	$(PYTEST) tests/unit/channels/test_base_core.py -v
