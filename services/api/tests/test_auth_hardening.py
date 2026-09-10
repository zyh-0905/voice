"""阶段三 认证加固:Argon2id、限流防枚举、单会话轮换、生产配置检测、SQL 会话持久化。"""
import time

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.auth import InMemoryTokenStore, SqlTokenStore, reset_token_store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    reset_token_store(InMemoryTokenStore())
    auth._fail_events.clear()
    yield
    reset_token_store(None)


def _login(username, password):
    return client.post('/api/v1/auth/login', json={'username': username, 'password': password})


def test_correct_password_logs_in():
    response = _login('demo', 'demo')
    assert response.status_code == 200
    assert response.json()['user']['role'] == 'ANALYST'


def test_wrong_password_rejected_uniformly():
    # 不存在的账号与错误密码返回同一文案,不泄露账号存在性
    missing = _login('no-such-user', 'demo')
    wrong = _login('demo', 'wrong-password')
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()['detail']['code'] == wrong.json()['detail']['code'] == 'invalid_credentials'


def test_login_throttled_after_five_failures():
    for _ in range(5):
        assert _login('demo', 'wrong-password').status_code == 401
    limited = _login('demo', 'demo')  # 即使密码正确也被退避
    assert limited.status_code == 429
    assert limited.json()['detail']['code'] == 'rate_limited'
    assert int(limited.headers.get('Retry-After', '0')) > 0


def test_single_session_rotation():
    first = _login('demo', 'demo').json()['access_token']
    second = _login('demo', 'demo').json()['access_token']
    assert first != second
    # 旧会话被撤销
    assert client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {first}'}).status_code == 401
    assert client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {second}'}).status_code == 200


def test_logout_revokes_session():
    token = _login('demo', 'demo').json()['access_token']
    assert client.post('/api/v1/auth/logout', headers={'Authorization': f'Bearer {token}'}).status_code == 204
    assert client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401


def test_production_settings_fail_fast(monkeypatch):
    from app.settings import validate_production_settings
    monkeypatch.setenv('VOICELENS_ENV', 'production')
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    monkeypatch.setenv('DEDUPE_HMAC_SECRET', 'a-real-random-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://localhost/voicelens')
    monkeypatch.delenv('SESSION_STORE', raising=False)
    with pytest.raises(RuntimeError, match='SESSION_STORE'):
        validate_production_settings()


def test_sql_token_store_survives_store_recreation():
    # 连测试环境的 PostgreSQL:同一 token 在不同 store 实例间有效(重启语义)
    store_a = SqlTokenStore()
    session = {'id': 'sql-user', 'role': 'ANALYST', 'projects': [], 'issued_at': time.time(),
               'exp': time.time() + 3600}
    token = store_a.issue(session)
    store_b = SqlTokenStore()
    loaded = store_b.get(token)
    assert loaded is not None
    assert loaded['id'] == 'sql-user'
    store_b.revoke(token)
    assert store_b.get(token) is None


def test_sql_token_store_rotates_sessions():
    store = SqlTokenStore()
    session = {'id': 'sql-user', 'role': 'ANALYST', 'projects': [], 'issued_at': time.time(),
               'exp': time.time() + 3600}
    first = store.issue(session)
    second = store.issue(session)
    assert store.get(first) is None  # issue 时撤销同用户旧会话
    assert store.get(second) is not None
    store.revoke(second)
