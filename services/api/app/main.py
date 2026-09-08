from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import uuid4
from .ingestion import parse_csv_text
from .repository import get_repository
from .worker import AnalysisWorker
from .middleware import SecurityHeadersMiddleware
import hashlib
import os

app = FastAPI(title='VoiceLens API', version='0.1.0')
app.add_middleware(SecurityHeadersMiddleware)
repository = get_repository()
datasets = repository.datasets
analyses = repository.analyses
worker = AnalysisWorker(analyses)
MAX_BYTES = 50 * 1024 * 1024
_idempotency = {}
ALLOWED = {'txt', 'csv', 'xls', 'xlsx'}
def now(): return datetime.now(timezone.utc).isoformat()
class ValidateRequest(BaseModel):
    expected_version: int | None = None
    mapping: dict | None = None
    sheet_name: str | None = None
    encoding: str | None = None
    timezone: str | None = None
    time_policy: str | None = None
class AnalysisRequest(BaseModel):
    dataset_ids: list[str] = Field(min_length=1)
    config: dict = {}
@app.get('/api/v1/health')
def health(): return {'status':'ok','service':'voicelens-api'}
@app.post('/api/v1/projects/{project_id}/datasets', status_code=201)
async def upload(project_id: str, file: UploadFile = File(...), name: str|None = Form(None), source_namespace: str|None = Form(None), source_kind: str|None = Form(None), consent: bool = Form(False)):
    if not consent: raise HTTPException(422, detail={'code':'consent_required'})
    ext = (file.filename or '').rsplit('.',1)[-1].lower()
    if ext not in ALLOWED: raise HTTPException(422, detail={'code':'unsupported_file_type'})
    data = await file.read()
    if len(data) > MAX_BYTES: raise HTTPException(413, detail={'code':'file_too_large'})
    did='ds_'+uuid4().hex[:10]
    preview = parse_csv_text(data.decode('utf-8', errors='replace')) if ext == 'csv' else {'headers': [], 'rows': [], 'stats': {}}
    d={'id':did,'project_id':project_id,'name':name or file.filename,'rows':preview.get('stats',{}).get('total',0),'status':'uploaded','state':'UPLOADED','hasTime':False,'version':1,'health':{'completeness':0,'piiMasked':True,'timeFieldMissing':0},'preview':preview,'file_ext':ext,'created_at':now()}
    return repository.create_dataset(d)
@app.get('/api/v1/projects/{project_id}/datasets')
def list_datasets(project_id: str): return {'items':[d for d in datasets.values() if d['project_id']==project_id], 'total':sum(d['project_id']==project_id for d in datasets.values())}
@app.post('/api/v1/projects/{project_id}/datasets/{dataset_id}/validate', status_code=202)
def validate(project_id: str, dataset_id: str, req: ValidateRequest):
    d=datasets.get(dataset_id)
    if not d or d['project_id']!=project_id: raise HTTPException(404, detail={'code':'dataset_not_found'})
    if req.expected_version is not None and req.expected_version != d['version']: raise HTTPException(409, detail={'code':'version_conflict'})
    if d.get('file_ext') in ('xls','xlsx'): raise HTTPException(422, detail={'code':'unsupported_file_type','message':'xlsx parsing is not supported yet'})
    stats = d.get('preview', {}).get('stats', {})
    d.update(state='READY_WITH_WARNINGS' if stats.get('invalid',0) or stats.get('missing_time',0) else 'READY', status='ready', rows=max(1,d['rows']), version=d['version']+1)
    total = stats.get('total', 0); d['health'] = {'completeness': round((stats.get('valid',0)/total)*100) if total else 0, 'piiMasked': True, 'timeFieldMissing': stats.get('missing_time',0)}
    d['validation'] = {'health': d['health'], 'errors': [], 'preview': d.get('preview', {})}
    return repository.update_dataset(dataset_id, d)
@app.post('/api/v1/projects/{project_id}/analyses', status_code=202)
def create_analysis(project_id: str, req: AnalysisRequest, idempotency_key: str|None = Header(None)):
    ds=[datasets.get(i) for i in req.dataset_ids]
    if idempotency_key:
        fingerprint = hashlib.sha256((project_id + '|' + '|'.join(req.dataset_ids) + '|' + repr(req.config)).encode()).hexdigest()
        previous = _idempotency.get(idempotency_key)
        if previous and previous[0] != fingerprint: raise HTTPException(409, detail={'code':'idempotency_conflict'})
        if previous: return analyses[previous[1]]
    if any(not d or d['project_id']!=project_id for d in ds): raise HTTPException(404, detail={'code':'dataset_not_found'})
    if any(d['state'] not in ('READY','READY_WITH_WARNINGS') for d in ds): raise HTTPException(422, detail={'code':'dataset_not_ready'})
    aid='run_'+uuid4().hex[:10]; a={'id':aid,'project_id':project_id,'dataset_ids':req.dataset_ids,'datasets':ds,'status':'queued','stage':'queued','progress':0,'total':sum(d['rows'] for d in ds)}; repository.create_analysis(a)
    if idempotency_key: _idempotency[idempotency_key] = (fingerprint, aid)
    if os.getenv('RUN_WORKER_INLINE', '').lower() in ('1', 'true', 'yes'):
        worker.run(aid)
    return analyses[aid]
@app.get('/api/v1/projects/{project_id}/analyses')
def list_analyses(project_id: str): return {'items':[a for a in analyses.values() if a['project_id']==project_id]}
@app.get('/api/v1/projects/{project_id}/analyses/{analysis_id}')
def get_analysis(project_id: str, analysis_id: str):
    a=analyses.get(analysis_id)
    if not a or a['project_id'] != project_id: raise HTTPException(404, detail={'code':'analysis_not_found'})
    return a
@app.post('/api/v1/projects/{project_id}/analyses/{analysis_id}/retry')
def retry_analysis(project_id: str, analysis_id: str):
    a=get_analysis(project_id, analysis_id)
    if a.get('status') not in ('error','cancelled'): raise HTTPException(409, detail={'code':'analysis_not_retryable'})
    worker.retry(analysis_id)
    if os.getenv('USE_CELERY', '').lower() in ('1','true','yes'):
        from .tasks import run_analysis_task
        if getattr(run_analysis_task, 'delay', None): run_analysis_task.delay(analysis_id)
    elif os.getenv('RUN_WORKER_INLINE', '').lower() in ('1','true','yes'): worker.run(analysis_id)
    return analyses[analysis_id]
@app.post('/api/v1/projects/{project_id}/analyses/{analysis_id}/cancel')
def cancel_analysis(project_id: str, analysis_id: str):
    get_analysis(project_id, analysis_id)
    return worker.cancel(analysis_id)


from fastapi.responses import Response

# Domain read models (in-memory demo repository)
projects = {'demo-project': {'id':'demo-project','name':'VoiceLens Demo Project','description':'Synthetic workspace','status':'active'}}
reviews = {}
def _project(pid): return projects.get(pid) or {'id':pid,'name':pid,'description':'Project','status':'active'}
@app.get('/api/v1/projects')
def list_projects(): return {'items': list(projects.values()), 'total': len(projects)}
@app.get('/api/v1/projects/{project_id}')
def get_project(project_id: str): return _project(project_id)
@app.get('/api/v1/projects/{project_id}/risks')
def list_risks(project_id: str): return {'items':[{'id':'risk-001','project_id':project_id,'title':'Missing time field','severity':'high','status':'open','evidence_count':2}], 'total':1}
@app.get('/api/v1/projects/{project_id}/tasks')
def list_tasks(project_id: str): return {'items':[{'id':'task-001','project_id':project_id,'title':'Missing time field','owner':'analyst','status':'todo','priority':'high'}], 'total':1}
@app.get('/api/v1/projects/{project_id}/reviews')
def list_reviews(project_id: str):
    items=[r for r in reviews.values() if r['project_id']==project_id] or [{'id':'review-001','project_id':project_id,'run_id':None,'status':'pending','finding':'Finding requires review','confirmed_by':None}]
    return {'items':items,'total':len(items)}
@app.post('/api/v1/projects/{project_id}/reviews/{review_id}/confirm')
def confirm_review(project_id: str, review_id: str, x_role: str|None = Header(None)):
    if (x_role or '').upper() == 'VIEWER': raise HTTPException(403, detail={'code':'forbidden'})
    r=reviews.setdefault(review_id, {'id':review_id,'project_id':project_id,'run_id':None,'status':'pending','finding':'Finding requires review','confirmed_by':None})
    if r['project_id'] != project_id: raise HTTPException(404, detail={'code':'review_not_found'})
    r.update(status='confirmed', confirmed_by='demo-user', confirmed_at=now()); return r
@app.get('/api/v1/projects/{project_id}/exports/redacted.csv')
def export_redacted(project_id: str):
    content = f'id,project_id,status\\nexport-001,{project_id},redacted\\n'
    return Response(content=content, media_type='text/csv')







