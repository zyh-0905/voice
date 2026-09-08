from fastapi.testclient import TestClient
from app.main import app, datasets

client = TestClient(app)
def test_health():
    assert client.get('/api/v1/health').json()['status'] == 'ok'
def test_upload_validate_analysis():
    r=client.post('/api/v1/projects/p/datasets', files={'file':('a.csv',b'x')}, data={'consent':'true'})
    assert r.status_code == 201
    did=r.json()['id']
    assert client.post(f'/api/v1/projects/p/datasets/{did}/validate',json={}).status_code == 202
    assert client.post('/api/v1/projects/p/analyses',json={'dataset_ids':[did]}).status_code == 202
def test_reject_type_and_consent():
    assert client.post('/api/v1/projects/p/datasets', files={'file':('a.txt',b'x')}, data={'consent':'true'}).status_code == 422
    assert client.post('/api/v1/projects/p/datasets', files={'file':('a.csv',b'x')}).status_code == 422
