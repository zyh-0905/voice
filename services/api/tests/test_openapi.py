from fastapi.testclient import TestClient

from app.main import app


def test_openapi_contract_lists_core_routes():
    document = TestClient(app).get('/openapi.json')
    assert document.status_code == 200
    paths = document.json()['paths']
    expected = {
        '/api/v1/health',
        '/api/v1/health/ready',
        '/api/v1/projects',
        '/api/v1/projects/{project_id}/members',
        '/api/v1/projects/{project_id}/settings',
        '/api/v1/projects/{project_id}/datasets',
        '/api/v1/projects/{project_id}/datasets/{dataset_id}',
        '/api/v1/projects/{project_id}/analyses',
        '/api/v1/projects/{project_id}/reviews/{review_id}/confirm',
        '/api/v1/projects/{project_id}/exports/redacted.csv',
    }
    assert expected <= paths.keys()
    assert paths['/api/v1/projects/{project_id}/datasets']['post']['responses']['201']
    assert paths['/api/v1/projects/{project_id}/analyses']['post']['responses']['202']


def test_openapi_has_no_direct_dataset_delete():
    """数据集删除只走 POST /deletions(7.5:确认名+OWNER+幂等+tombstone+级联)。

    曾经存在的 DELETE /datasets/{id} 只删数据集行本身:feedback/分块/风险候选/
    证据全残留,不写 tombstone,权限还只是 analyst。它是规格外的第二删除路径
    ——旁路一旦回来,这个断言就会红。
    """
    document = TestClient(app).get('/openapi.json')
    methods = document.json()['paths']['/api/v1/projects/{project_id}/datasets/{dataset_id}']
    assert 'delete' not in methods
    assert 'get' in methods
