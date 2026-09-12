"""阶段三 Cookie + CSRF:会话 Cookie、预登录 CSRF、写接口校验与 Origin 限制。"""
import pytest

from app import auth
from app.auth import InMemoryTokenStore, reset_token_store
from support.client import make_client


@pytest.fixture
def client():
    reset_token_store(InMemoryTokenStore())
    auth._fail_events.clear()
    c = make_client()
    yield c
    reset_token_store(None)


def _csrf(client, origin: str | None = None) -> dict:
    headers = {}
    if origin:
        headers['Origin'] = origin
    response = client.get('/api/v1/auth/csrf', headers=headers)
    return {**headers, 'X-CSRF-Token': response.json()['csrf_token']}


def test_login_sets_httponly_session_cookie(client):
    response = client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    assert response.status_code == 200
    cookie = response.headers.get('set-cookie', '')
    assert 'vl_session=' in cookie
    assert 'HttpOnly' in cookie
    assert 'SameSite=lax' in cookie.replace('samesite', 'SameSite')
    assert 'Path=/' in cookie


def test_session_cookie_authenticates_without_bearer(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    # 不带 Authorization 头,仅凭 Cookie
    me = client.get('/api/v1/auth/me')
    assert me.status_code == 200
    assert me.json()['id'] == 'demo-user'


def test_logout_clears_session_cookie(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    logout = client.post('/api/v1/auth/logout', headers=_csrf(client))
    assert logout.status_code == 204
    assert 'vl_session=' in logout.headers.get('set-cookie', '')
    # 会话 Cookie 已清除:后续请求不再视为已登录
    assert client.get('/api/v1/auth/me').status_code == 401


def test_cookie_write_without_csrf_token_is_rejected(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    # 有会话 Cookie 但没有 CSRF 头 → 拒绝
    response = client.post('/api/v1/projects/demo-project/tasks/drafts', json={'title': '未授权写入'})
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'csrf_failed'


def test_cookie_write_with_matching_csrf_token_succeeds(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    headers = _csrf(client)
    response = client.post('/api/v1/projects/demo-project/tasks/drafts', json={'title': '带令牌写入'}, headers=headers)
    assert response.status_code == 201


def test_csrf_mismatch_is_rejected(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    headers = _csrf(client)
    headers['X-CSRF-Token'] = 'forged-token'
    response = client.post('/api/v1/projects/demo-project/tasks/drafts', json={'title': 'x'}, headers=headers)
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'csrf_failed'


def test_disallowed_origin_is_rejected(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    headers = _csrf(client)
    headers['Origin'] = 'https://evil.example.com'
    response = client.post('/api/v1/projects/demo-project/tasks/drafts', json={'title': 'x'}, headers=headers)
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'origin_not_allowed'


def test_allowed_origin_passes(client):
    client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    headers = _csrf(client, origin='http://localhost:8080')
    response = client.post('/api/v1/projects/demo-project/tasks/drafts', json={'title': 'x'}, headers=headers)
    assert response.status_code == 201


def test_bearer_client_is_exempt_from_csrf(client):
    login = client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'})
    token = login.json()['access_token']
    client.cookies.clear()  # 纯 Bearer 客户端不携带 Cookie
    response = client.post('/api/v1/projects/demo-project/tasks/drafts', json={'title': 'API 客户端写入'},
                           headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 201


def test_idle_expiry_invalidates_session():
    store = InMemoryTokenStore()
    session = {'id': 'u', 'role': 'ANALYST', 'projects': [], 'exp': 9_999_999_999, 'idle_exp': 0}
    token = store.issue(session)
    assert store.get(token) is None  # 空闲过期


def test_idle_window_slides_on_access():
    store = InMemoryTokenStore()
    import time
    session = {'id': 'u', 'role': 'ANALYST', 'projects': [], 'exp': time.time() + 3600,
               'idle_exp': time.time() + 1}
    token = store.issue(session)
    assert store.get(token) is not None
    first_idle = store._tokens[token]['idle_exp']  # noqa: SLF001
    time.sleep(0.01)
    store.get(token)
    assert store._tokens[token]['idle_exp'] >= first_idle  # noqa: SLF001
