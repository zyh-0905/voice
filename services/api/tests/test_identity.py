"""身份提供商抽象:本地账号注入、OIDC 校验(JWKS/签名/iss/aud/exp)与 CLI。"""
import json
import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import admin, identity
from app.identity import LocalAccountProvider, OidcProvider, get_identity_provider
from support.client import make_client

ISSUER = "https://idp.example.com"
AUDIENCE = "voicelens-web"


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _token(private_key, **overrides) -> str:
    claims = {
        "sub": "sso-user-1", "iss": ISSUER, "aud": AUDIENCE,
        "exp": int(time.time()) + 300, "email": "alice@corp.example",
        "name": "Alice", "role": "ANALYST",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def _provider(public_key) -> OidcProvider:
    return OidcProvider(issuer=ISSUER, audience=AUDIENCE, jwks_url="https://idp.example.com/jwks",
                        key_resolver=lambda _token: public_key)


def test_local_provider_authenticates_demo_account():
    provider = LocalAccountProvider()
    user = provider.authenticate("demo", "demo")
    assert user is not None and user["role"] == "ANALYST"


def test_local_provider_rejects_wrong_password_and_unknown_user():
    provider = LocalAccountProvider()
    assert provider.authenticate("demo", "wrong") is None
    assert provider.authenticate("ghost", "demo") is None


def test_local_accounts_env_overrides_demo(monkeypatch):
    custom = {"alice": {"id": "u-1", "email": "a@corp.example", "name": "Alice", "role": "VIEWER",
                        "password_hash": identity.hash_password("s3cret")}}
    monkeypatch.setenv("LOCAL_ACCOUNTS", json.dumps(custom))
    provider = LocalAccountProvider()
    assert provider.authenticate("alice", "s3cret")["role"] == "VIEWER"
    assert provider.authenticate("demo", "demo") is None  # 演示账号被覆盖


def test_invalid_local_accounts_json_fails_fast(monkeypatch):
    monkeypatch.setenv("LOCAL_ACCOUNTS", "not-json")
    with pytest.raises(RuntimeError, match="LOCAL_ACCOUNTS"):
        LocalAccountProvider()


def test_oidc_verifies_valid_assertion(rsa_keypair):
    private_key, public_key = rsa_keypair
    user = _provider(public_key).verify_assertion(_token(private_key))
    assert user == {"id": "sso-user-1", "email": "alice@corp.example", "name": "Alice", "role": "ANALYST"}


def test_oidc_rejects_wrong_issuer(rsa_keypair):
    private_key, public_key = rsa_keypair
    assert _provider(public_key).verify_assertion(_token(private_key, iss="https://evil.example.com")) is None


def test_oidc_rejects_wrong_audience(rsa_keypair):
    private_key, public_key = rsa_keypair
    assert _provider(public_key).verify_assertion(_token(private_key, aud="other-app")) is None


def test_oidc_rejects_expired_token(rsa_keypair):
    private_key, public_key = rsa_keypair
    assert _provider(public_key).verify_assertion(_token(private_key, exp=int(time.time()) - 10)) is None


def test_oidc_rejects_signature_from_another_key(rsa_keypair):
    _private_key, public_key = rsa_keypair
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert _provider(public_key).verify_assertion(_token(other)) is None


def test_oidc_rejects_missing_required_claim(rsa_keypair):
    private_key, public_key = rsa_keypair
    token = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300},
                       private_key, algorithm="RS256")
    assert _provider(public_key).verify_assertion(token) is None


def test_oidc_defaults_role_for_unknown_claim(rsa_keypair):
    private_key, public_key = rsa_keypair
    user = _provider(public_key).verify_assertion(_token(private_key, role="superuser"))
    assert user["role"] == "SUPERUSER"  # 角色由 IdP 断言,下游按 ANALYST/VIEWER 判定权限


def test_oidc_provider_does_not_accept_form_password(rsa_keypair):
    _private_key, public_key = rsa_keypair
    assert _provider(public_key).authenticate("demo", "demo") is None


def test_get_identity_provider_requires_oidc_config(monkeypatch):
    monkeypatch.setenv("IDENTITY_PROVIDER", "oidc")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    with pytest.raises(RuntimeError, match="OIDC_ISSUER"):
        get_identity_provider()


def test_get_identity_provider_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("IDENTITY_PROVIDER", "saml")
    with pytest.raises(RuntimeError, match="unsupported"):
        get_identity_provider()


# —— 端点行为 ——

def test_auth_config_reports_local_mode(monkeypatch):
    monkeypatch.delenv("IDENTITY_PROVIDER", raising=False)
    client = make_client()
    assert client.get('/api/v1/auth/config').json() == {"mode": "local"}


def test_assertion_endpoint_rejects_in_local_mode(monkeypatch):
    monkeypatch.delenv("IDENTITY_PROVIDER", raising=False)
    client = make_client()
    response = client.post('/api/v1/auth/token', json={"assertion": "whatever"})
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'assertion_not_supported'


def test_assertion_endpoint_issues_session_in_oidc_mode(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("IDENTITY_PROVIDER", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://idp.example.com/jwks")

    class StubProvider(OidcProvider):
        def _signing_key(self, token):
            return public_key

    monkeypatch.setattr(identity, "OidcProvider", StubProvider)
    client = make_client()
    response = client.post('/api/v1/auth/token', json={"assertion": _token(private_key)})
    assert response.status_code == 200
    assert response.json()['user']['id'] == 'sso-user-1'
    assert 'vl_session=' in response.headers.get('set-cookie', '')


def test_form_login_asks_for_sso_in_oidc_mode(monkeypatch):
    monkeypatch.setenv("IDENTITY_PROVIDER", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://idp.example.com/jwks")
    client = make_client()
    response = client.post('/api/v1/auth/login', json={"username": "demo", "password": "demo"})
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'use_sso'


# —— 管理员 CLI ——

def test_admin_create_user_outputs_mergeable_json(capsys):
    code = admin.main(["create-user", "--username", "alice", "--password", "s3cret",
                       "--role", "ANALYST", "--name", "Alice"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["alice"]["role"] == "ANALYST"
    assert payload["alice"]["password_hash"].startswith("$argon2id$")


def test_admin_create_user_rejects_bad_role(capsys):
    assert admin.main(["create-user", "--username", "bob", "--password", "x", "--role", "ADMIN"]) == 2


def test_admin_hash_password_matches_verifier(capsys):
    admin.main(["hash-password", "--password", "pw-1"])
    digest = capsys.readouterr().out.strip()
    assert identity.verify_password(digest, "pw-1")
    assert not identity.verify_password(digest, "pw-2")


def test_admin_list_accounts_hides_hashes(monkeypatch, capsys):
    monkeypatch.setenv("LOCAL_ACCOUNTS", json.dumps(
        {"alice": {"id": "u-1", "role": "VIEWER", "name": "Alice", "password_hash": "$argon2id$secret"}}))
    assert admin.main(["list-accounts"]) == 0
    out = capsys.readouterr().out
    assert "alice" in out and "VIEWER" in out
    assert "argon2" not in out
