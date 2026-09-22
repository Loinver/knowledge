#!/usr/bin/env python3
"""创建首个管理员账号。

后端默认关闭公开注册（理由见 `docs/adr/0002-account-auth.md`），所以全新部署
必须先跑一次这个脚本才能登录。库里已经有账号时脚本拒绝执行——否则它就是一个
任何人跑一次就能提权的入口。

用法（走 Makefile，它会把工作目录切到 `server/`，保证 SQLite 文件与后端一致）：

.. code-block:: bash

    make seed-admin
    make seed-admin USERNAME=root EMAIL=root@example.org PASSWORD=...

不传口令时随机生成一个并只打印这一次；明文口令不入库、不进日志。
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建知识中台的首个管理员账号")
    parser.add_argument("--username", default="admin", help="登录名，3-32 位字母数字下划线")
    parser.add_argument("--email", default="admin@example.org", help="登录邮箱")
    parser.add_argument(
        "--password",
        default=None,
        help="登录口令；不传则随机生成并打印一次",
    )
    parser.add_argument("--display-name", default=None, help="界面显示名，缺省用登录名")
    return parser.parse_args()


def main() -> int:
    # 先把 server/ 放进 import 路径，再导入应用模块。
    sys.path.insert(0, str(SERVER_DIR))

    from app.core.db import Base, get_engine, session_scope
    from app.core.errors import KGError
    from app.domain import account_service

    args = parse_args()
    generated = args.password is None
    password = args.password or secrets.token_urlsafe(12)

    # 开发态直接用 create_all 建表，与后端启动时的行为一致；
    # 生产走 Alembic 迁移，脚本不替它做决定。
    Base.metadata.create_all(get_engine())

    try:
        with session_scope() as session:
            user = account_service.bootstrap_admin(
                session,
                username=args.username,
                email=args.email,
                password=password,
                display_name=args.display_name,
            )
    except KGError as error:
        if str(error.code) == "KG.ALREADY_EXISTS":
            print(
                "已存在账号，拒绝再建管理员。\n"
                "请用现有管理员登录后在「系统管理 → 用户管理」里建号或提权。",
                file=sys.stderr,
            )
            return 1
        print(f"创建失败：{error.code} {error.params}", file=sys.stderr)
        return 1

    print("管理员已创建：")
    print(f"  登录名：{user.username}")
    print(f"  邮箱：{user.email}")
    if generated:
        print(f"  口令：{password}")
        print("  口令只显示这一次，请立即保存。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
