"""FastAPI 服务运行配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@dataclass(frozen=True)
class ApiSettings:
    jwt_secret: str
    token_expire_seconds: int = 3600
    jwt_issuer: str = "cleaning-support-api"
    jwt_audience: str = "cleaning-support-web"
    cors_origins: list[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    demo_password: str | None = None

    @classmethod
    def from_env(cls) -> "ApiSettings":
        jwt_secret = os.getenv("APP_JWT_SECRET", "")
        if len(jwt_secret) < 32:
            raise RuntimeError("请设置至少 32 位的 APP_JWT_SECRET 后再启动 API")
        expire_seconds = int(os.getenv("APP_JWT_EXPIRE_SECONDS", "3600"))
        cors_origins = [
            origin.strip()
            for origin in os.getenv(
                "APP_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)
            ).split(",")
            if origin.strip()
        ]
        return cls(
            jwt_secret=jwt_secret,
            token_expire_seconds=expire_seconds,
            cors_origins=cors_origins,
            demo_password=os.getenv("APP_DEMO_PASSWORD") or None,
        )
