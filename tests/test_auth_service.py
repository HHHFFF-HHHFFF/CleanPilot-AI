import pytest

from auth.passwords import hash_password, verify_password
from auth.service import AuthService, AuthSettings, AuthenticationError
from auth.tokens import TokenError, create_access_token, decode_access_token
from storage.auth_repository import AuthRepository
from storage.support_repository import SupportRepository


JWT_SECRET = "test-secret-that-is-longer-than-thirty-two-characters"


def create_user_database(tmp_path):
    seed_file = tmp_path / "records.csv"
    seed_file.write_text(
        "user_id,display_name,city,device_id,device_model,purchased_at,warranty_until,month,feature,efficiency,consumables,comparison\n"
        "u-1,测试用户,上海,d-1,S9,2026-01-01,2028-01-01,2026-08,清扫 12 次,95%,滤网 60%,增加 2 次\n",
        encoding="utf-8",
    )
    support_repository = SupportRepository(tmp_path / "support.db")
    support_repository.seed_business_data(seed_file)
    return support_repository


def test_password_hash_does_not_store_plaintext():
    encoded_hash = hash_password("SecurePass123")

    assert "SecurePass123" not in encoded_hash
    assert verify_password("SecurePass123", encoded_hash)
    assert not verify_password("WrongPassword", encoded_hash)


def test_auth_service_rejects_wrong_password_and_issues_valid_token(tmp_path):
    support_repository = create_user_database(tmp_path)
    auth_repository = AuthRepository(support_repository.database_path)
    service = AuthService(auth_repository, AuthSettings(jwt_secret=JWT_SECRET))
    service.set_password("u-1", "SecurePass123")

    with pytest.raises(AuthenticationError, match="用户标识或密码错误"):
        service.login("u-1", "WrongPassword")

    token, expires_in = service.login("u-1", "SecurePass123")
    claims = service.verify_token(token)

    assert expires_in == 3600
    assert claims.user_id == "u-1"
    assert claims.role == "customer"


def test_expired_and_tampered_tokens_are_rejected():
    token = create_access_token(
        user_id="u-1",
        role="customer",
        secret=JWT_SECRET,
        expires_in_seconds=10,
        issuer="issuer",
        audience="audience",
        now=1000,
    )

    with pytest.raises(TokenError, match="已过期"):
        decode_access_token(
            token,
            secret=JWT_SECRET,
            issuer="issuer",
            audience="audience",
            now=1011,
        )

    with pytest.raises(TokenError, match="无效"):
        decode_access_token(
            token + "broken",
            secret=JWT_SECRET,
            issuer="issuer",
            audience="audience",
        )
