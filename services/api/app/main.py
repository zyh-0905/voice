from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import uuid4

app = FastAPI(title='VoiceLens API', version='0.1.0')
datasets: dict[str, dict] = {}
analyses: dict[str, dict] = {}
MAX_BYTES = 50 * 1024 * 1024
ALLOWED = {'csv', 'xls', 'xlsx'}

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
    d={'id':did,'project_id':project_id,'name':name or file.filename,'rows':0,'status':'uploaded','state':'UPLOADED','hasTime':False,'version':1,'health':{'completeness':0,'piiMasked':True,'timeFieldMissing':0},'created_at':now()}
    datasets[did]=d; return d
@app.get('/api/v1/projects/{project_id}/datasets')
def list_datasets(project_id: str): return {'items':[d for d in datasets.values() if d['project_id']==project_id], 'total':sum(d['project_id']==project_id for d in datasets.values())}
@app.post('/api/v1/projects/{project_id}/datasets/{dataset_id}/validate', status_code=202)
def validate(project_id: str, dataset_id: str, req: ValidateRequest):
    d=datasets.get(dataset_id)
    if not d or d['project_id']!=project_id: raise HTTPException(404, detail={'code':'dataset_not_found'})
    if req.expected_version is not None and req.expected_version != d['version']: raise HTTPException(409, detail={'code':'version_conflict'})
    d.update(state='READY',status='ready',rows=max(1,d['rows']),version=d['version']+1); return d
@app.post('/api/v1/projects/{project_id}/analyses', status_code=202)
def create_analysis(project_id: str, req: AnalysisRequest):
    ds=[datasets.get(i) for i in req.dataset_ids]
    if any(not d or d['project_id']!=project_id for d in ds): raise HTTPException(404, detail={'code':'dataset_not_found'})
    if any(d['state'] not in ('READY','READY_WITH_WARNINGS') for d in ds): raise HTTPException(422, detail={'code':'dataset_not_ready'})
    aid='run_'+uuid4().hex[:10]; a={'id':aid,'project_id':project_id,'dataset_ids':req.dataset_ids,'status':'queued','stage':'queued','progress':0,'total':sum(d['rows'] for d in ds)}; analyses[aid]=a; return a
@app.get('/api/v1/projects/{project_id}/analyses')
def list_analyses(project_id: str): return {'items':[a for a in analyses.values() if a['project_id']==project_id]}
