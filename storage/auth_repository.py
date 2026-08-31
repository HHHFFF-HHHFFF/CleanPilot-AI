"""用于保存用户登录凭证的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from utils.path_tool import get_abs_path


@dataclass(frozen=True)
class UserCredential:
    user_id: str
    password_hash: str
    role: str
    is_active: bool


class AuthRepository:
    """仅负责凭证数据，不向业务层暴露原始数据库连接。"""

    def __init__(self, database_path: str | Path | None = None):
        self.database_path = Path(database_path or get_abs_path("data/support.db"))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_credentials (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'customer',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )

    def save_credential(
        self,
        user_id: str,
        password_hash: str,
        *,
        role: str = "customer",
        is_active: bool = True,
    ) -> UserCredential:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            user_exists = connection.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if user_exists is None:
                raise ValueError(f"用户不存在：{user_id}")
            connection.execute(
                """
                INSERT INTO user_credentials (
                    user_id, password_hash, role, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
                """,
                (user_id, password_hash, role, int(is_active), now, now),
            )
        credential = self.get_credential(user_id)
        if credential is None:
            raise RuntimeError("用户凭证写入失败")
        return credential

    def get_credential(self, user_id: str) -> UserCredential | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, password_hash, role, is_active
                FROM user_credentials WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["is_active"] = bool(data["is_active"])
        return UserCredential(**data)
