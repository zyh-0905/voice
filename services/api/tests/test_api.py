from fastapi.testclient import TestClient
from app.main import app, datasets
from app.ingestion import redact_text, parse_csv_text

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
    assert client.post('/api/v1/projects/p/datasets', files={'file':('a.pdf',b'x')}, data={'consent':'true'}).status_code == 422
    assert client.post('/api/v1/projects/p/datasets', files={'file':('a.csv',b'x')}).status_code == 422

def test_txt_upload_and_redaction():
    r = client.post('/api/v1/projects/p/datasets', files={'file': ('notes.txt', '联系 a@example.com'.encode())}, data={'consent': 'true'})
    assert r.status_code == 201
    masked = redact_text('a@example.com 13812345678 ORDER-123456')
    assert '<EMAIL_REDACTED>' in masked['text'] and masked['hits']['phone'] == 1

def test_csv_preview_stats():
    parsed = parse_csv_text('email,phone\na@example.com,13812345678\na@example.com,13812345678\n')
    assert parsed['stats']['total'] == 2
    assert parsed['stats']['duplicate'] == 1
    assert parsed['stats']['redacted'] == 2

def test_domain_endpoints_and_viewer_guard():
    assert client.get('/api/v1/projects').status_code == 200
    assert client.get('/api/v1/projects/demo').status_code == 200
    assert client.get('/api/v1/projects/demo/risks').status_code == 200
    assert client.get('/api/v1/projects/demo/tasks').status_code == 200
    assert client.get('/api/v1/projects/demo/reviews').status_code == 200
    assert client.get('/api/v1/projects/demo/exports/redacted.csv').headers['content-type'].startswith('text/csv')
    review = client.get('/api/v1/projects/demo/reviews').json()['items'][0]['id']
    assert client.post(f'/api/v1/projects/demo/reviews/{review}/confirm', headers={'x-role':'VIEWER'}).status_code == 403
    assert client.post(f'/api/v1/projects/demo/reviews/{review}/confirm', headers={'x-role':'ANALYST'}).status_code == 200

def test_analysis_idempotency():
    r = client.post('/api/v1/projects/p/analyses', json={'dataset_ids':['missing']}, headers={'Idempotency-Key':'k1'})
    assert r.status_code == 404
