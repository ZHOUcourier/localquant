.PHONY: dev dev-backend dev-frontend install install-backend install-frontend clean

# 安装所有依赖
install: install-backend install-frontend

install-backend:
	uv sync

install-frontend:
	cd frontend && npm install

# 开发模式
dev: dev-backend dev-frontend

dev-backend:
	uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

# 清理
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist
	rm -rf .venv

# 帮助
help:
	@echo "可用命令:"
	@echo "  make install        - 安装所有依赖"
	@echo "  make dev            - 启动开发模式（前后端）"
	@echo "  make dev-backend    - 仅启动后端"
	@echo "  make dev-frontend   - 仅启动前端"
	@echo "  make clean          - 清理缓存"
