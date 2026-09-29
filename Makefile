.PHONY: install dev start lint lint-web lint-server architecture-check fix test test-web test-server test-e2e typecheck check-api format commit seed-admin

install: ## 安装前后端依赖与 git hooks
	pnpm install
	cd server && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

dev: ## 前后端一体启动（后端 :4000 + 前端 :4010，前端代理 /api）
	pnpm run dev

start: ## 构建前端并以单端口启动（后端托管 web/dist，:4000）
	pnpm run start

lint: lint-web lint-server architecture-check ## 全量代码风格与语法校验

lint-web:
	pnpm run lint:web
	pnpm -C web typecheck
	pnpm run format:check

lint-server:
	cd server && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

architecture-check:
	pnpm run check:architecture

fix: ## 自动修复可修复问题
	pnpm run lint:web --fix
	pnpm run format
	cd server && .venv/bin/ruff check . --fix && .venv/bin/ruff format .

test: test-web test-server

test-web:
	pnpm run test:web

test-server:
	pnpm run test:server

test-e2e: ## 浏览器端 M3 主流程（Playwright，使用隔离临时数据库）
	pnpm test:e2e

typecheck:
	pnpm -C web typecheck

check-api:
	pnpm run check:api

format:
	pnpm run format

commit: ## 交互式提交（commitizen + cz-git）
	pnpm run commit

seed-admin: ## 创建首个管理员（可覆盖 USERNAME= EMAIL= PASSWORD=），公开注册默认关闭
	cd server && .venv/bin/python ../scripts/seed_admin.py $(if $(USERNAME),--username "$(USERNAME)") $(if $(EMAIL),--email "$(EMAIL)") $(if $(PASSWORD),--password "$(PASSWORD)") $(if $(DISPLAY_NAME),--display-name "$(DISPLAY_NAME)")
