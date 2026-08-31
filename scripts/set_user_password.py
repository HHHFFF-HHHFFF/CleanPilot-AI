"""为已导入的业务用户设置或重置登录密码。"""

from __future__ import annotations

import argparse
import getpass

from auth.passwords import hash_password
from storage.auth_repository import AuthRepository
from storage.support_repository import SupportRepository
from utils.config_handler import agent_config
from utils.path_tool import get_abs_path


def main() -> None:
    parser = argparse.ArgumentParser(description="为客服系统用户设置登录密码")
    parser.add_argument("user_id", help="业务用户标识")
    parser.add_argument(
        "--role",
        choices=["customer", "admin"],
        default="customer",
        help="账户角色，默认为 customer",
    )
    arguments = parser.parse_args()

    password = getpass.getpass("请输入新密码：")
    confirmed_password = getpass.getpass("请再次输入新密码：")
    if password != confirmed_password:
        raise SystemExit("两次输入的密码不一致")

    support_repository = SupportRepository()
    support_repository.seed_business_data(get_abs_path(agent_config["business_seed_path"]))
    auth_repository = AuthRepository(support_repository.database_path)
    auth_repository.save_credential(
        arguments.user_id,
        hash_password(password),
        role=arguments.role,
    )
    print(f"用户 {arguments.user_id} 的密码已更新，角色为 {arguments.role}")


if __name__ == "__main__":
    main()
