"""管理员 CLI:生成本地账号(Argon2id 哈希),供 LOCAL_ACCOUNTS 注入。

用法:
  python -m services.api.app.admin hash-password --password <pw>
  python -m services.api.app.admin create-user --username alice --role ANALYST \\
      --name "Alice" --email alice@corp.example --password <pw>
  python -m services.api.app.admin list-accounts

create-user 输出 JSON 片段;把它合并进 LOCAL_ACCOUNTS 环境变量即可启用。
首版不提供公开注册:账号创建、停用与角色分配均经此 CLI 完成(停用 = 从
LOCAL_ACCOUNTS 中移除该条并重启服务)。
"""
from __future__ import annotations

import argparse
import json
import sys

from .identity import hash_password, load_local_accounts

ROLES = ("ANALYST", "VIEWER")


def _cmd_hash_password(args: argparse.Namespace) -> int:
    print(hash_password(args.password))
    return 0


def _cmd_create_user(args: argparse.Namespace) -> int:
    role = args.role.upper()
    if role not in ROLES:
        print(f"role must be one of {', '.join(ROLES)}", file=sys.stderr)
        return 2
    record = {
        "id": args.user_id or f"user-{args.username}",
        "email": args.email or f"{args.username}@example.invalid",
        "name": args.name or args.username,
        "role": role,
        "password_hash": hash_password(args.password),
    }
    print(json.dumps({args.username: record}, ensure_ascii=False, indent=2))
    return 0


def _cmd_list_accounts(_args: argparse.Namespace) -> int:
    accounts = load_local_accounts()
    for username, record in sorted(accounts.items()):
        # 只输出元信息,不打印密码哈希
        print(f"{username}\t{record.get('role', '?')}\t{record.get('id', '?')}\t{record.get('name', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voicelens-admin", description="本地账号管理")
    sub = parser.add_subparsers(dest="command", required=True)

    p_hash = sub.add_parser("hash-password", help="生成 Argon2id 哈希")
    p_hash.add_argument("--password", required=True)
    p_hash.set_defaults(func=_cmd_hash_password)

    p_create = sub.add_parser("create-user", help="生成账号 JSON 片段")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--password", required=True)
    p_create.add_argument("--role", default="ANALYST")
    p_create.add_argument("--name")
    p_create.add_argument("--email")
    p_create.add_argument("--user-id")
    p_create.set_defaults(func=_cmd_create_user)

    p_list = sub.add_parser("list-accounts", help="列出现行生效的账号")
    p_list.set_defaults(func=_cmd_list_accounts)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
