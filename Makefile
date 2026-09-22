.PHONY: install dev lint lint-web lint-server fix test typecheck format commit seed-admin

install: ## 安装前后端依赖与 git hooks
	pnpm install
	cd server && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

dev: ## 前后端一体启动（后端 :8000 + 前端 :5173，前端代理 /api）
	pnpm run dev

start: ## 构建前端并以单端口启动（后端托管 web/dist，:8000）
	pnpm run start

lint: lint-web lint-server ## 全量代码风格与语法校验

lint-web:
	pnpm run lint:web
	pnpm -C web typecheck
	pnpm run format:check

lint-server:
	cd server && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

fix: ## 自动修复可修复问题
	pnpm run lint:web -- --fix
	pnpm run format
	cd server && .venv/bin/ruff check . --fix && .venv/bin/ruff format .

test:
	cd server && .venv/bin/pytest

typecheck:
	pnpm -C web typecheck

format:
	pnpm run format

commit: ## 交互式提交（commitizen + cz-git）
	pnpm run commit

seed-admin: ## 创建首个管理员（可覆盖 USERNAME= EMAIL= PASSWORD=），公开注册默认关闭
	cd server && .venv/bin/python ../scripts/seed_admin.py $(if $(USERNAME),--username "$(USERNAME)") $(if $(EMAIL),--email "$(EMAIL)") $(if $(PASSWORD),--password "$(PASSWORD)") $(if $(DISPLAY_NAME),--display-name "$(DISPLAY_NAME)")
