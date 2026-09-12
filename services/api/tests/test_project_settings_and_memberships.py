"""W03 项目隔离、成员与设置:工程计划 7.2 契约与 5.2 表结构落地。

覆盖:成员列表按项目隔离、GET/PATCH 设置(OWNER 才可改、乐观锁 409)、
数据集详情外项目 404、POST /projects 创建后调用者为 OWNER。
"""
from app.main import repository
from support.client import make_client

client = make_client()


def _login(username: str, password: str) -> dict:
    """取 Bearer 头:登录后清 Cookie,纯 Bearer 客户端不触发 CSRF 校验。"""
    csrf = client.get('/api/v1/auth/csrf').json()['csrf_token']
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': password},
                           headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200
    client.cookies.clear()
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def _seed_project(project_id: str, members: dict[str, str]) -> None:
    """直接写项目与成员行:本文件关注路由权限,成员写入路径由 POST /projects 用例覆盖。"""
    if repository.get_project(project_id) is None:
        repository.create_project({'id': project_id, 'name': f'用例 {project_id}', 'timezone': 'UTC'})
    for user_id, role in members.items():
        if repository.get_membership(project_id, user_id) is None:
            repository.create_membership({'project_id': project_id, 'user_id': user_id,
                                          'role': role, 'display_name': user_id})


def test_members_are_scoped_to_the_project(monkeypatch):
    """W03:成员列表只含本项目成员,非成员访问其他项目成员列表 404。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    _seed_project('members_own', {'demo-user': 'OWNER', 'member-2': 'VIEWER'})
    _seed_project('members_foreign', {'viewer-user': 'VIEWER'})
    headers = _login('demo', 'demo')

    mine = client.get('/api/v1/projects/members_own/members', headers=headers)
    assert mine.status_code == 200
    items = mine.json()['items']
    assert {item['id'] for item in items} == {'demo-user', 'member-2'}
    assert dict((item['id'], item['role']) for item in items) == {'demo-user': 'OWNER', 'member-2': 'VIEWER'}
    assert all(set(item) == {'id', 'display_name', 'role'} for item in items)
    assert mine.json()['total'] == 2

    foreign = client.get('/api/v1/projects/members_foreign/members', headers=headers)
    assert foreign.status_code == 404
    assert foreign.json()['detail']['code'] == 'project_not_found'


def test_foreign_project_settings_are_not_visible(monkeypatch):
    """W03:未加入项目的设置一律 404,不暴露项目存在性。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    _seed_project('settings_foreign', {'viewer-user': 'VIEWER'})
    headers = _login('demo', 'demo')
    response = client.get('/api/v1/projects/settings_foreign/settings', headers=headers)
    assert response.status_code == 404


def test_settings_get_works_before_any_patch():
    """W03:GET settings 在未 PATCH 前返回派生默认值,且不含密钥/上游地址。"""
    _seed_project('settings_default', {})
    response = client.get('/api/v1/projects/settings_default/settings')
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {'timezone', 'limits', 'rules', 'model_available', 'version'}
    assert payload['timezone'] == 'UTC'
    assert payload['model_available'] is True
    assert payload['version'] == 1

    # settings_json 里即便混入密钥/内部地址(历史或运维写入),出站也只给白名单键
    repository.update_project_settings('settings_default', {
        'api_key': 'sk-do-not-leak', 'upstream_url': 'http://internal-upstream:9000', 'version': 2})
    scrubbed = client.get('/api/v1/projects/settings_default/settings')
    assert set(scrubbed.json()) == {'timezone', 'limits', 'rules', 'model_available', 'version'}
    assert 'sk-do-not-leak' not in scrubbed.text and 'internal-upstream' not in scrubbed.text


def test_owner_patches_settings_and_version_increments(monkeypatch):
    """W03:OWNER 修改设置成功,version 递增并持久化(只影响下次分析)。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    _seed_project('settings_patch', {'demo-user': 'OWNER'})
    headers = _login('demo', 'demo')
    before = client.get('/api/v1/projects/settings_patch/settings', headers=headers).json()

    updated = client.patch('/api/v1/projects/settings_patch/settings', headers=headers, json={
        'expected_version': before['version'],
        'timezone': 'Asia/Shanghai',
        'limits': {'max_feedback_rows': 1000},
        'model_available': False,
    })
    assert updated.status_code == 200
    payload = updated.json()
    assert payload['version'] == before['version'] + 1
    assert payload['timezone'] == 'Asia/Shanghai'
    assert payload['limits'] == {'max_feedback_rows': 1000}
    assert payload['model_available'] is False
    # 未提交的键保留默认值
    assert payload['rules'] == before['rules']

    persisted = client.get('/api/v1/projects/settings_patch/settings', headers=headers).json()
    assert persisted['version'] == before['version'] + 1
    assert persisted['timezone'] == 'Asia/Shanghai'


def test_viewer_cannot_patch_settings(monkeypatch):
    """W03:VIEWER 不是 OWNER,PATCH 设置 403 且内容不变。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    _seed_project('settings_viewer', {'viewer-user': 'VIEWER'})
    headers = _login('viewer', 'viewer')
    response = client.patch('/api/v1/projects/settings_viewer/settings', headers=headers,
                            json={'expected_version': 1, 'timezone': 'UTC'})
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'forbidden'
    stored = client.get('/api/v1/projects/settings_viewer/settings', headers=headers).json()
    assert stored['version'] == 1


def test_editor_cannot_patch_settings(monkeypatch):
    """W03:EDITOR 也不是 OWNER,PATCH 设置仍是 403(仅 OWNER 可改)。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    _seed_project('settings_editor', {'viewer-user': 'EDITOR'})
    headers = _login('viewer', 'viewer')
    response = client.patch('/api/v1/projects/settings_editor/settings', headers=headers,
                            json={'expected_version': 1, 'timezone': 'UTC'})
    assert response.status_code == 403
    assert client.get('/api/v1/projects/settings_editor/settings',
                      headers=headers).json()['timezone'] == 'UTC'


def test_stale_expected_version_conflicts(monkeypatch):
    """W03:乐观锁过期 expected_version 返回 409 VERSION_CONFLICT,不覆盖他人修改。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    _seed_project('settings_conflict', {'demo-user': 'OWNER'})
    headers = _login('demo', 'demo')
    first = client.patch('/api/v1/projects/settings_conflict/settings', headers=headers,
                         json={'expected_version': 1, 'timezone': 'Asia/Shanghai'})
    assert first.status_code == 200

    stale = client.patch('/api/v1/projects/settings_conflict/settings', headers=headers,
                         json={'expected_version': 1, 'timezone': 'UTC'})
    assert stale.status_code == 409
    assert stale.json()['detail']['code'] == 'VERSION_CONFLICT'
    stored = client.get('/api/v1/projects/settings_conflict/settings', headers=headers).json()
    assert stored['timezone'] == 'Asia/Shanghai'


def test_dataset_detail_is_project_scoped_and_redacted():
    """7.3:数据集详情外项目/不存在 404;存量行出站同样兜底脱敏。"""
    repository.create_dataset({'id': 'ds_detail_own', 'project_id': 'ds_scope_own', 'name': '批次',
                               'rows': 1, 'version': 1,
                               'preview': {'rows': [{'email': 'person@example.com'}]}})
    response = client.get('/api/v1/projects/ds_scope_own/datasets/ds_detail_own')
    assert response.status_code == 200
    assert 'person@example.com' not in response.text
    assert '<EMAIL_REDACTED>' in response.text
    assert client.get('/api/v1/projects/other-project/datasets/ds_detail_own').status_code == 404
    assert client.get('/api/v1/projects/ds_scope_own/datasets/ds_missing').status_code == 404


def test_create_project_makes_caller_owner():
    """W03:POST /projects 创建项目并把调用者登记为 OWNER 成员。"""
    response = client.post('/api/v1/projects', json={'name': '新分析项目', 'timezone': 'Asia/Shanghai'})
    assert response.status_code == 201
    project = response.json()
    assert project['name'] == '新分析项目'
    assert project['timezone'] == 'Asia/Shanghai'
    membership = repository.get_membership(project['id'], 'demo-user')
    assert membership is not None and membership['role'] == 'OWNER'
    settings = client.get(f"/api/v1/projects/{project['id']}/settings")
    assert settings.status_code == 200 and settings.json()['timezone'] == 'Asia/Shanghai'


def test_create_project_requires_authentication(monkeypatch):
    """W03:公开注册关闭,未登录用户不能创建项目。"""
    monkeypatch.setenv('AUTH_REQUIRED', 'true')
    response = client.post('/api/v1/projects', json={'name': '匿名项目', 'timezone': 'UTC'})
    assert response.status_code == 401


def test_new_project_is_usable_without_relogin():
    """授权必须按实时成员关系判断,不能读登录时的会话快照。

    快照会让创建者被自己刚建的项目挡在门外(404),也会让被吊销的权限活到会话
    过期——计划 10.4 要求删除项目即吊销访问。
    """
    created = client.post('/api/v1/projects', json={'name': '即时可用', 'timezone': 'Asia/Shanghai'})
    assert created.status_code == 201
    project_id = created.json()['id']

    # 同一个会话,不重新登录
    assert client.get(f'/api/v1/projects/{project_id}/settings').status_code == 200
    listed = client.get('/api/v1/projects').json()
    assert project_id in [item['id'] for item in listed['items']]
    members = client.get(f'/api/v1/projects/{project_id}/members').json()
    assert [m['role'] for m in members['items']] == ['OWNER']


def test_revoked_membership_takes_effect_immediately():
    """移除成员关系后,同一会话立即失去该项目访问权(不等会话过期)。

    必须走真实会话:演示旁路(AUTH_REQUIRED=false)按设计短路了项目隔离检查,
    拿它验证吊销语义没有意义。
    """
    from app.main import repository

    csrf = client.get('/api/v1/auth/csrf').json()['csrf_token']
    token = client.post('/api/v1/auth/login', json={'username': 'demo', 'password': 'demo'},
                        headers={'X-CSRF-Token': csrf}).json()['access_token']
    client.cookies.clear()
    auth = {'Authorization': f'Bearer {token}'}

    created = client.post('/api/v1/projects', json={'name': '吊销实验', 'timezone': 'Asia/Shanghai'},
                          headers=auth)
    assert created.status_code == 201
    project_id = created.json()['id']
    assert client.get(f'/api/v1/projects/{project_id}/settings', headers=auth).status_code == 200

    repository.delete_memberships(project_id)

    assert client.get(f'/api/v1/projects/{project_id}/settings', headers=auth).status_code == 404
    listed = client.get('/api/v1/projects', headers=auth).json()
    assert project_id not in [item['id'] for item in listed['items']]
