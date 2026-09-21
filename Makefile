.PHONY: install dev lint lint-web lint-server fix test typecheck format commit

install: ## 安装前后端依赖与 git hooks
	npm install
	cd server && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

dev: ## 前后端一体启动（后端 :8000 + 前端 :5173，前端代理 /api）
	npm run dev

start: ## 构建前端并以单端口启动（后端托管 web/dist，:8000）
	npm run start

lint: lint-web lint-server ## 全量代码风格与语法校验

lint-web:
	npm run lint:web
	npm run typecheck --workspace=web
	npm run format:check

lint-server:
	cd server && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

fix: ## 自动修复可修复问题
	npm run lint --workspace=web -- --fix
	npm run format
	cd server && .venv/bin/ruff check . --fix && .venv/bin/ruff format .

test:
	cd server && .venv/bin/pytest

typecheck:
	npm run typecheck --workspace=web

format:
	npm run format

commit: ## 交互式提交（commitizen + cz-git）
	npm run commit
