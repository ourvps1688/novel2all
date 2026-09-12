# novel2all Makefile
# 统一开发命令入口

PYTHON ?= python
UV ?= uv

.PHONY: help install dev test lint format typecheck clean build run-docs ci-status ci-watch ci-watch-stop

help:
	@echo "novel2all 开发命令："
	@echo ""
	@echo "=== 项目 ==="
	@echo "  make install       安装依赖（uv）"
	@echo "  make dev           安装开发依赖"
	@echo "  make test          跑测试"
	@echo "  make test-cov      跑测试 + 覆盖率"
	@echo "  make lint          ruff check"
	@echo "  make format        ruff format"
	@echo "  make typecheck     mypy"
	@echo "  make clean         清理构建产物"
	@echo "  make build         构建 sdist + wheel"
	@echo "  make serve         启动 Web UI"
	@echo "  make cli           启动 CLI（version）"
	@echo ""
	@echo "=== CI 集成 ==="
	@echo "  make ci-status     一次性查 GitHub Actions 状态"
	@echo "  make ci-watch      启动后台守护进程（写到 .novel2all/ci-status.json）"
	@echo "  make ci-watch-stop 停守护进程"

install:
	$(UV) sync

dev:
	$(UV) sync --all-extras --dev

test:
	$(PYTHON) -m pytest tests/ -v

test-cov:
	$(PYTHON) -m pytest tests/ --cov=src/novel2all --cov-report=term-missing --cov-report=html

lint:
	$(PYTHON) -m ruff check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/

typecheck:
	$(PYTHON) -m mypy src/novel2all --strict --ignore-missing-imports

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
	$(PYTHON) -m build

serve:
	PYTHONPATH=src $(PYTHON) -m novel2all.cli.main web

cli:
	PYTHONPATH=src $(PYTHON) -m novel2all.cli.main version

# ===== CI 集成 =====
ci-status:
	$(PYTHON) scripts/ci_status.py

ci-watch:
	$(PYTHON) scripts/ci_watch.py

ci-watch-stop:
	@if [ -f .ci_watch.pid ]; then \
	  kill `cat .ci_watch.pid` && rm .ci_watch.pid && echo "已停"; \
	else \
	  echo "无守护进程在跑"; \
	fi

# 验证 GitHub Actions workflows 能在本地跑（模拟 workflow）
verify-ci:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) typecheck
