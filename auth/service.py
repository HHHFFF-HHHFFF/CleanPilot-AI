"""组合凭证仓储、密码校验和访问令牌的认证服务。"""

from __future__ import annotations

from dataclasses import dataclass

from auth.passwords import hash_password, verify_password
from auth.tokens import TokenClaims, create_access_token, decode_access_token
from storage.auth_repository import AuthRepository


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    token_expire_seconds: int = 3600
    issuer: str = "cleaning-support-api"
    audience: str = "cleaning-support-web"

    def __post_init__(self):
        if len(self.jwt_secret) < 32:
            raise ValueError("APP_JWT_SECRET 长度至少为 32 位")
        if self.token_expire_seconds <= 0:
            raise ValueError("访问令牌有效期必须大于 0")


class AuthenticationError(ValueError):
    """登录信息错误或账户不可用。"""


class AuthService:
    def __init__(self, repository: AuthRepository, settings: AuthSettings):
        self.repository = repository
        self.settings = settings

    def set_password(self, user_id: str, password: str, *, role: str = "customer") -> None:
        self.repository.save_credential(user_id, hash_password(password), role=role)

    def login(self, user_id: str, password: str) -> tuple[str, int]:
        credential = self.repository.get_credential(user_id)
        if (
            credential is None
            or not credential.is_active
            or not verify_password(password, credential.password_hash)
        ):
            raise AuthenticationError("用户标识或密码错误")
        token = create_access_token(
            user_id=credential.user_id,
            role=credential.role,
            secret=self.settings.jwt_secret,
            expires_in_seconds=self.settings.token_expire_seconds,
            issuer=self.settings.issuer,
            audience=self.settings.audience,
        )
        return token, self.settings.token_expire_seconds

    def verify_token(self, token: str) -> TokenClaims:
        return decode_access_token(
            token,
            secret=self.settings.jwt_secret,
            issuer=self.settings.issuer,
            audience=self.settings.audience,
        )
