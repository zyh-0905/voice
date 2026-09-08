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
    r = client.post('/api/v1/projects/p/datasets', files={'file': ('notes.txt', '鑱旂郴 a@example.com'.encode())}, data={'consent': 'true'})
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
    assert client.get('/api/v1/projects/demo-project').status_code == 200
    assert client.get('/api/v1/projects/demo-project/risks').status_code == 200
    assert client.get('/api/v1/projects/demo-project/tasks').status_code == 200
    assert client.get('/api/v1/projects/demo-project/reviews').status_code == 200
    assert client.get('/api/v1/projects/demo-project/exports/redacted.csv').headers['content-type'].startswith('text/csv')
    review = client.get('/api/v1/projects/demo-project/reviews').json()['items'][0]['id']
    assert client.post(f'/api/v1/projects/demo-project/reviews/{review}/confirm', headers={'x-role':'VIEWER'}).status_code == 403
    assert client.post(f'/api/v1/projects/demo-project/reviews/{review}/confirm', headers={'x-role':'ANALYST'}).status_code == 200

def test_analysis_idempotency():
    r = client.post('/api/v1/projects/p/analyses', json={'dataset_ids':['missing']}, headers={'Idempotency-Key':'k1'})
    assert r.status_code == 404

def test_successful_analysis_idempotency_and_conflict():
    upload = client.post('/api/v1/projects/idempo/datasets', files={'file': ('a.csv', b'email\na@example.com\n')}, data={'consent': 'true'})
    did = upload.json()['id']
    assert client.post(f'/api/v1/projects/idempo/datasets/{did}/validate', json={}).status_code == 202
    headers = {'Idempotency-Key': 'same-key'}
    first = client.post('/api/v1/projects/idempo/analyses', json={'dataset_ids': [did]}, headers=headers)
    second = client.post('/api/v1/projects/idempo/analyses', json={'dataset_ids': [did]}, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()['id'] == second.json()['id']
    conflict = client.post('/api/v1/projects/idempo/analyses', json={'dataset_ids': [did], 'config': {'x': 1}}, headers=headers)
    assert conflict.status_code == 409

def test_auth_login_me_logout():
    bad = client.post('/api/v1/auth/login', json={'username':'demo','password':'wrong'})
    assert bad.status_code == 401
    login = client.post('/api/v1/auth/login', json={'username':'demo','password':'demo'})
    assert login.status_code == 200
    payload = login.json(); assert payload['token_type'] == 'bearer'
    token = payload['access_token']; assert payload['user']['role'] == 'ANALYST'
    me = client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200 and me.json()['id'] == 'demo-user'
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.post('/api/v1/auth/logout', headers={'Authorization': f'Bearer {token}'}).status_code == 204
    assert client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401



