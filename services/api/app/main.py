from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends, Response
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import uuid4
from .ingestion import parse_csv_text, parse_xlsx_bytes, redact_text
from .repository import get_repository
from .worker import AnalysisWorker
from .middleware import SecurityHeadersMiddleware
from .rate_limit import WriteRateLimitMiddleware
from .auth import router as auth_router, require_user, require_analyst
from .config import dedupe_hmac_secret
from .settings import validate_production_settings
import hashlib
import hmac
import os

validate_production_settings()

app = FastAPI(title='VoiceLens API', version='0.1.0')
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(WriteRateLimitMiddleware)
app.include_router(auth_router)
repository = get_repository()
datasets = repository.datasets
analyses = repository.analyses
worker = AnalysisWorker(analyses)
MAX_BYTES = 50 * 1024 * 1024
_idempotency = {}
outbox_events = []
ALLOWED = {'txt', 'csv', 'xlsx'}
def now(): return datetime.now(timezone.utc).isoformat()
class ValidateRequest(BaseModel):
    expected_version: int | None = None
    mapping: dict | None = None
    sheet_name: str | None = None
    encoding: str | None = None
    timezone: str | None = None
    time_policy: str | None = None
class AnalysisRequest(BaseModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=10)
    config: dict = {}
@app.get('/api/v1/health')
def health(): return {'status':'ok','service':'voicelens-api'}

@app.get('/api/v1/health/ready')
def readiness():
    """Dependency readiness probe.

    Demo mode deliberately reports skipped database/queue checks. In database
    mode a failed connection makes the probe return 503 so orchestrators do
    not route traffic to an instance that cannot persist work.
    """
    from fastapi.responses import JSONResponse
    use_database = os.getenv('USE_DATABASE', '').lower() in ('1', 'true', 'yes')
    use_queue = os.getenv('USE_CELERY', '').lower() in ('1', 'true', 'yes')
    database = {'status': 'configured' if use_database else 'skipped'}
    queue = {'status': 'configured' if use_queue else 'skipped'}
    if use_database:
        try:
            from .db import engine
            with engine.connect() as connection:
                connection.exec_driver_sql('SELECT 1')
            database['status'] = 'reachable'
        except Exception as exc:
            database.update(status='unreachable', error=type(exc).__name__)
            return JSONResponse(status_code=503, content={'status': 'not_ready', 'database': database, 'queue': queue})
    return {'status': 'ready', 'database': database, 'queue': queue}
@app.post('/api/v1/projects/{project_id}/datasets', status_code=201)
async def upload(project_id: str, file: UploadFile = File(...), name: str|None = Form(None), source_namespace: str|None = Form(None), source_kind: str|None = Form(None), consent: bool = Form(False), user: dict = Depends(require_analyst)):
    if not consent: raise HTTPException(422, detail={'code':'consent_required'})
    ext = (file.filename or '').rsplit('.',1)[-1].lower()
    if ext not in ALLOWED: raise HTTPException(422, detail={'code':'unsupported_file_type'})
    data = await file.read()
    if len(data) > MAX_BYTES: raise HTTPException(413, detail={'code':'file_too_large'})
    content_hash = hashlib.sha256(data).hexdigest()
    source_name = name or file.filename or 'upload'
    namespace = source_namespace or ''
    kind = source_kind or ext
    dedupe_secret, demo_fallback = dedupe_hmac_secret()
    event_key = hmac.new(dedupe_secret.encode('utf-8'), '\x1f'.join((project_id, namespace, kind, source_name)).encode('utf-8'), hashlib.sha256).hexdigest()
    for existing in datasets.values():
        existing_key = existing.get('event_key')
        # Legacy rows predate HMAC keys; compare their fields only for migration compatibility.
        is_same_source = existing_key == event_key if existing_key else (existing.get('project_id'), existing.get('source_namespace',''), existing.get('source_kind', existing.get('file_ext','')), existing.get('name')) == (project_id, namespace, kind, source_name)
        if is_same_source:
            if existing.get('content_hash') == content_hash: return JSONResponse(status_code=200, content=existing)
            raise HTTPException(409, detail={'code':'source_conflict'})
    did='ds_'+uuid4().hex[:10]
    try:
        preview = parse_csv_text(data.decode('utf-8')) if ext == 'csv' else parse_xlsx_bytes(data) if ext == 'xlsx' else {'headers': [], 'rows': [], 'stats': {}}
    except UnicodeDecodeError as exc:
        raise HTTPException(422, detail={'code': 'invalid_file', 'message': f'invalid UTF-8 CSV at byte {exc.start}'}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={'code': 'invalid_file', 'message': str(exc)}) from exc
    d={'id':did,'project_id':project_id,'event_key':event_key,'content_hash':content_hash,'rows':preview.get('stats',{}).get('total',0),'status':'uploaded','state':'UPLOADED','hasTime':False,'version':1,'health':{'completeness':0,'piiMasked':True,'timeFieldMissing':0},'preview':preview,'file_ext':ext,'created_at':now()}
    return repository.create_dataset(d)
def _page(page: int, page_size: int):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, detail={'code': 'invalid_pagination'})
    return page, page_size
@app.get('/api/v1/projects/{project_id}/datasets')
def list_datasets(project_id: str, page: int = 1, page_size: int = 20, user: dict = Depends(require_user)):
    page, page_size = _page(page, page_size)
    all_items = [d for d in datasets.values() if d['project_id']==project_id]
    start = (page - 1) * page_size
    return {'items': all_items[start:start + page_size], 'total': len(all_items), 'page': page, 'page_size': page_size}

@app.post('/api/v1/projects/{project_id}/datasets/{dataset_id}/validate', status_code=202)
def validate(project_id: str, dataset_id: str, req: ValidateRequest, user: dict = Depends(require_analyst)):
    d=datasets.get(dataset_id)
    if not d or d['project_id']!=project_id: raise HTTPException(404, detail={'code':'dataset_not_found'})
    if req.expected_version is not None and req.expected_version != d['version']: raise HTTPException(409, detail={'code':'version_conflict'})
    stats = d.get('preview', {}).get('stats', {})
    d.update(state='READY_WITH_WARNINGS' if stats.get('invalid',0) or stats.get('missing_time',0) else 'READY', status='ready', rows=d['rows'], version=d['version']+1)
    total = stats.get('total', 0); d['health'] = {'completeness': round((stats.get('valid',0)/total)*100) if total else 0, 'piiMasked': True, 'timeFieldMissing': stats.get('missing_time',0)}
    d['validation'] = {'health': d['health'], 'errors': [], 'preview': d.get('preview', {})}
    return repository.update_dataset(dataset_id, d)
@app.post('/api/v1/projects/{project_id}/analyses', status_code=202)
def create_analysis(project_id: str, req: AnalysisRequest, idempotency_key: str|None = Header(None), user: dict = Depends(require_analyst)):
    ds=[datasets.get(i) for i in req.dataset_ids]
    if idempotency_key:
        fingerprint = hashlib.sha256((project_id + '|' + '|'.join(req.dataset_ids) + '|' + repr(req.config)).encode()).hexdigest()
        previous = _idempotency.get(idempotency_key)
        if previous and previous[0] != fingerprint: raise HTTPException(409, detail={'code':'idempotency_conflict'})
        if previous: return analyses[previous[1]]
    if any(not d or d['project_id']!=project_id for d in ds): raise HTTPException(404, detail={'code':'dataset_not_found'})
    if sum(d['rows'] for d in ds if d) > 5000: raise HTTPException(422, detail={'code':'feedback_limit_exceeded'})
    if any(d['state'] not in ('READY','READY_WITH_WARNINGS') for d in ds): raise HTTPException(422, detail={'code':'dataset_not_ready'})
    total_rows = sum(d.get('rows', 0) for d in ds)
    if total_rows > 5000: raise HTTPException(422, detail={'code':'analysis_row_limit','max_rows':5000,'rows':total_rows})
    aid='run_'+uuid4().hex[:10]; a={'id':aid,'project_id':project_id,'dataset_ids':req.dataset_ids,'datasets':ds,'status':'queued','stage':'queued','progress':0,'total':total_rows}; repository.create_analysis(a)
    repository.create_outbox_event({'event_key': f'analysis.created:{aid}', 'event_type':'analysis.created', 'payload': {'analysis_id': aid, 'project_id': project_id}})
    outbox_events.append({'event_id': 'evt_'+uuid4().hex[:10], 'event_type': 'analysis.created', 'analysis_id': aid, 'project_id': project_id, 'status': 'pending', 'created_at': now()})
    if idempotency_key: _idempotency[idempotency_key] = (fingerprint, aid)
    if os.getenv('RUN_WORKER_INLINE', '').lower() in ('1', 'true', 'yes'):
        worker.run(aid)
    return analyses[aid]

@app.get('/api/v1/projects/{project_id}/outbox/status')
def outbox_status(project_id: str, user: dict = Depends(require_user)):
    events = [e for e in repository.list_pending_outbox() if e.get('payload', {}).get('project_id') == project_id]
    return {'pending': len(events), 'items': events}
@app.get('/api/v1/projects/{project_id}/analyses')
def list_analyses(project_id: str, page: int = 1, page_size: int = 20, user: dict = Depends(require_user)):
    page, page_size = _page(page, page_size)
    all_items = [a for a in analyses.values() if a['project_id']==project_id]
    start = (page - 1) * page_size
    return {'items': all_items[start:start + page_size], 'total': len(all_items), 'page': page, 'page_size': page_size}
@app.get('/api/v1/projects/{project_id}/analyses/{analysis_id}')
def get_analysis(project_id: str, analysis_id: str, user: dict = Depends(require_user)):
    a=analyses.get(analysis_id)
    if not a or a['project_id'] != project_id: raise HTTPException(404, detail={'code':'analysis_not_found'})
    return a
@app.post('/api/v1/projects/{project_id}/analyses/{analysis_id}/retry')
def retry_analysis(project_id: str, analysis_id: str, user: dict = Depends(require_analyst)):
    a=get_analysis(project_id, analysis_id)
    if a.get('status') not in ('error','cancelled'): raise HTTPException(409, detail={'code':'analysis_not_retryable'})
    worker.retry(analysis_id)
    if os.getenv('USE_CELERY', '').lower() in ('1','true','yes'):
        from .tasks import run_analysis_task
        if getattr(run_analysis_task, 'delay', None): run_analysis_task.delay(analysis_id)
    elif os.getenv('RUN_WORKER_INLINE', '').lower() in ('1','true','yes'): worker.run(analysis_id)
    return analyses[analysis_id]
@app.post('/api/v1/projects/{project_id}/analyses/{analysis_id}/cancel')
def cancel_analysis(project_id: str, analysis_id: str, user: dict = Depends(require_analyst)):
    get_analysis(project_id, analysis_id)
    return worker.cancel(analysis_id)


from fastapi.responses import Response, JSONResponse
import csv
import io
import json

# Domain read models (in-memory demo repository)
projects = {'demo-project': {'id':'demo-project','name':'VoiceLens Demo Project','description':'Synthetic workspace','status':'active'}}
reviews = {}
def _project(pid): return projects.get(pid) or {'id':pid,'name':pid,'description':'Project','status':'active'}
@app.get('/api/v1/projects')
def list_projects(user: dict = Depends(require_user)): return {'items': list(projects.values()), 'total': len(projects)}
@app.get('/api/v1/projects/{project_id}')
def get_project(project_id: str, user: dict = Depends(require_user)):
    if project_id not in projects: raise HTTPException(404, detail={'code':'project_not_found'})
    return projects[project_id]
@app.get('/api/v1/projects/{project_id}/risks')
def list_risks(project_id: str, user: dict = Depends(require_user)): return {'items':[{'id':'risk-001','project_id':project_id,'title':'Missing time field','severity':'high','status':'open','evidence_count':2}], 'total':1}
@app.get('/api/v1/projects/{project_id}/tasks')
def list_tasks(project_id: str, user: dict = Depends(require_user)): return {'items':[{'id':'task-001','project_id':project_id,'title':'Missing time field','owner':'analyst','status':'todo','priority':'high'}], 'total':1}
@app.get('/api/v1/projects/{project_id}/reviews')
def list_reviews(project_id: str, user: dict = Depends(require_user)):
    items=[r for r in reviews.values() if r['project_id']==project_id] or [{'id':'review-001','project_id':project_id,'run_id':None,'status':'pending','finding':'Finding requires review','confirmed_by':None}]
    return {'items':items,'total':len(items)}
@app.post('/api/v1/projects/{project_id}/reviews/{review_id}/confirm')
def confirm_review(project_id: str, review_id: str, user: dict = Depends(require_analyst)):
    r=reviews.setdefault(review_id, {'id':review_id,'project_id':project_id,'run_id':None,'status':'pending','finding':'Finding requires review','confirmed_by':None})
    if r['project_id'] != project_id: raise HTTPException(404, detail={'code':'review_not_found'})
    r.update(status='confirmed', confirmed_by='demo-user', confirmed_at=now()); return r
@app.get('/api/v1/projects/{project_id}/exports/redacted.csv')
def export_redacted(project_id: str, user: dict = Depends(require_user)):
    """Export only the redacted dataset previews belonging to *project_id*.

    The payload intentionally keeps each row in a JSON column.  This avoids
    leaking arbitrary source column names while preserving nested/duplicate
    fields, and applies redaction once more at the export boundary so a
    repository populated by an older parser cannot emit raw PII.
    """
    if project_id not in projects:
        raise HTTPException(404, detail={'code': 'project_not_found'})
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=['dataset_id', 'row_index', 'data'])
    writer.writeheader()
    for dataset in datasets.values():
        if dataset.get('project_id') != project_id:
            continue
        rows = (dataset.get('preview') or {}).get('rows') or []
        for index, row in enumerate(rows):
            clean = {}
            for key, value in (row or {}).items():
                clean[str(key)] = redact_text(str(value))['text']
            writer.writerow({'dataset_id': dataset.get('id', ''), 'row_index': index, 'data': json.dumps(clean, ensure_ascii=False, separators=(',', ':'))})
    return Response(content=output.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{project_id}-redacted.csv"'})

@app.delete('/api/v1/projects/{project_id}/datasets/{dataset_id}', status_code=204)
def delete_dataset(project_id: str, dataset_id: str, user: dict = Depends(require_analyst)):
    dataset = datasets.get(dataset_id)
    if not dataset or dataset.get('project_id') != project_id:
        raise HTTPException(404, detail={'code': 'dataset_not_found'})
    repository.delete_dataset(dataset_id)
    return Response(status_code=204)

