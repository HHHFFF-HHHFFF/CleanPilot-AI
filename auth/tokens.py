"""使用 PyJWT 签发和验证 HS256 短期访问令牌。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import jwt


class TokenError(ValueError):
    """访问令牌无效、过期或不符合当前服务约束。"""


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    role: str
    expires_at: int


def create_access_token(
    *,
    user_id: str,
    role: str,
    secret: str,
    expires_in_seconds: int,
    issuer: str,
    audience: str,
    now: int | None = None,
) -> str:
    issued_at = int(time.time() if now is None else now)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": issued_at,
        "exp": issued_at + expires_in_seconds,
        "iss": issuer,
        "aud": audience,
        "jti": uuid.uuid4().hex,
        "token_type": "access",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(
    token: str,
    *,
    secret: str,
    issuer: str,
    audience: str,
    now: int | None = None,
) -> TokenClaims:
    options = {
        "require": ["sub", "role", "iat", "exp", "iss", "aud", "token_type"],
    }
    if now is not None:
        options["verify_exp"] = False
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("访问令牌已过期") from None
    except jwt.InvalidTokenError:
        raise TokenError("访问令牌无效") from None

    current_time = int(time.time() if now is None else now)
    if payload["token_type"] != "access":
        raise TokenError("访问令牌类型无效")
    if not isinstance(payload["exp"], int) or payload["exp"] <= current_time:
        raise TokenError("访问令牌已过期")
    if not isinstance(payload["sub"], str) or not payload["sub"]:
        raise TokenError("访问令牌用户无效")
    if not isinstance(payload["role"], str) or not payload["role"]:
        raise TokenError("访问令牌角色无效")

    return TokenClaims(
        user_id=payload["sub"],
        role=payload["role"],
        expires_at=payload["exp"],
    )
