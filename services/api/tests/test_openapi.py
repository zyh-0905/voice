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
