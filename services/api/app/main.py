from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from uuid import uuid4
from .ingestion import parse_csv_text, parse_xlsx_bytes, redact_text
from .repository import get_repository
from .worker import AnalysisWorker
from .middleware import CsrfMiddleware, SecurityHeadersMiddleware
from .rate_limit import WriteRateLimitMiddleware
from .auth import router as auth_router, require_user, require_analyst, require_owner, require_project_access, require_project_analyst, require_project_owner
from .config import dedupe_hmac_secret
from .settings import validate_production_settings
import hashlib
import hmac
import os

validate_production_settings()

app = FastAPI(title='VoiceLens API', version='0.1.0')
# 开发环境跨域:默认放行本地 vite/nginx 来源,生产用 CORS_ORIGINS 覆盖。
# 会话走 HttpOnly Cookie,跨源开发必须允许凭据;来源是显式白名单,不是通配。
_cors_origins = [o.strip() for o in os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173,http://localhost:8080,http://127.0.0.1:8080').split(',') if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(WriteRateLimitMiddleware)
app.include_router(auth_router)
repository = get_repository()
datasets = repository.datasets
analyses = repository.analyses
worker = AnalysisWorker(analyses, repository)
MAX_BYTES = 50 * 1024 * 1024
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
async def upload(project_id: str, file: UploadFile = File(...), name: str|None = Form(None), source_namespace: str|None = Form(None), source_kind: str|None = Form(None), consent: bool = Form(False), user: dict = Depends(require_project_analyst)):
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
            if existing.get('content_hash') == content_hash: return JSONResponse(status_code=200, content=_redacted_out(existing))
            raise HTTPException(409, detail={'code':'source_conflict'})
    did='ds_'+uuid4().hex[:10]
    try:
        preview = parse_csv_text(data.decode('utf-8')) if ext == 'csv' else parse_xlsx_bytes(data) if ext == 'xlsx' else {'headers': [], 'rows': [], 'stats': {}}
    except UnicodeDecodeError as exc:
        raise HTTPException(422, detail={'code': 'invalid_file', 'message': f'invalid UTF-8 CSV at byte {exc.start}'}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={'code': 'invalid_file', 'message': str(exc)}) from exc
    d={'id':did,'project_id':project_id,'event_key':event_key,'content_hash':content_hash,'name':source_name,'rows':preview.get('stats',{}).get('total',0),'status':'uploaded','state':'UPLOADED','hasTime':False,'version':1,'health':{'completeness':0,'piiMasked':True,'timeFieldMissing':0},'preview':preview,'file_ext':ext,'created_at':now()}
    return repository.create_dataset(d)
def _page(page: int, page_size: int):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, detail={'code': 'invalid_pagination'})
    return page, page_size


# —— 脱敏出站兜底 ——
# 新数据在导入时已脱敏(ingestion.parse_csv_text 只吐出脱敏行),这里兜的是**存量
# 数据**与纵深防御:旧解析器写入的 preview、按原始正文发布的证据引文与规则扫描
# 片段,都还躺在仓储里。与导出边界同因——数据访问层不能假设上游都合规。
#
# 递归而不是逐个字段点名:run 快照由数据集行、规则扫描证据、主题引用等多个模块
# 写入,点名容易漏(漏一个就是一次 PII 泄露)。只影响响应,不改写仓储。
#
# 已知代价:旧 run 的 offset/quote 按**原始正文**计算,脱敏后不再自洽——那正是要
# 移除的数据本身。新 run 的正文导入即脱敏,offset 自洽。
def _redacted_out(value):
    if isinstance(value, str):
        return redact_text(value)['text']
    if isinstance(value, dict):
        return {key: _redacted_out(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted_out(item) for item in value]
    return value
@app.get('/api/v1/projects/{project_id}/datasets')
def list_datasets(project_id: str, page: int = 1, page_size: int = 20, user: dict = Depends(require_project_access)):
    page, page_size = _page(page, page_size)
    all_items = [d for d in datasets.values() if d['project_id']==project_id]
    start = (page - 1) * page_size
    return {'items': [_redacted_out(d) for d in all_items[start:start + page_size]], 'total': len(all_items), 'page': page, 'page_size': page_size}

@app.get('/api/v1/projects/{project_id}/datasets/{dataset_id}')
def get_dataset(project_id: str, dataset_id: str, user: dict = Depends(require_project_access)):
    """数据集详情(工程计划 7.3):外项目/不存在一律 404;出站与列表同样兜底脱敏。"""
    dataset = datasets.get(dataset_id)
    if not dataset or dataset.get('project_id') != project_id:
        raise HTTPException(404, detail={'code': 'dataset_not_found'})
    return _redacted_out(dataset)

@app.post('/api/v1/projects/{project_id}/datasets/{dataset_id}/validate', status_code=202)
def validate(project_id: str, dataset_id: str, req: ValidateRequest, user: dict = Depends(require_project_analyst)):
    d=datasets.get(dataset_id)
    if not d or d['project_id']!=project_id: raise HTTPException(404, detail={'code':'dataset_not_found'})
    if req.expected_version is not None and req.expected_version != d['version']: raise HTTPException(409, detail={'code':'version_conflict'})
    stats = d.get('preview', {}).get('stats', {})
    d.update(state='READY_WITH_WARNINGS' if stats.get('invalid',0) or stats.get('missing_time',0) else 'READY', status='ready', rows=d['rows'], version=d['version']+1)
    total = stats.get('total', 0); d['health'] = {'completeness': round((stats.get('valid',0)/total)*100) if total else 0, 'piiMasked': True, 'timeFieldMissing': stats.get('missing_time',0)}
    d['validation'] = {'health': d['health'], 'errors': [], 'preview': d.get('preview', {})}
    return _redacted_out(repository.update_dataset(dataset_id, d))
@app.post('/api/v1/projects/{project_id}/analyses', status_code=202)
def create_analysis(project_id: str, req: AnalysisRequest, idempotency_key: str|None = Header(None), user: dict = Depends(require_project_analyst)):
    ds=[datasets.get(i) for i in req.dataset_ids]
    fingerprint = None
    if idempotency_key:
        fingerprint = hashlib.sha256((project_id + '|' + '|'.join(req.dataset_ids) + '|' + repr(req.config)).encode()).hexdigest()
        previous = repository.get_idempotency(idempotency_key)
        if previous:
            if previous['fingerprint'] != fingerprint: raise HTTPException(409, detail={'code':'idempotency_conflict'})
            return analyses[previous['analysis_id']]
    if any(not d or d['project_id']!=project_id for d in ds): raise HTTPException(404, detail={'code':'dataset_not_found'})
    if sum(d['rows'] for d in ds if d) > 5000: raise HTTPException(422, detail={'code':'feedback_limit_exceeded'})
    if any(d['state'] not in ('READY','READY_WITH_WARNINGS') for d in ds): raise HTTPException(422, detail={'code':'dataset_not_ready'})
    total_rows = sum(d.get('rows', 0) for d in ds)
    if total_rows > 5000: raise HTTPException(422, detail={'code':'analysis_row_limit','max_rows':5000,'rows':total_rows})
    aid='run_'+uuid4().hex[:10]; a={'id':aid,'project_id':project_id,'dataset_ids':req.dataset_ids,'datasets':ds,'status':'queued','stage':'queued','progress':0,'total':total_rows}; repository.create_analysis(a)
    repository.create_outbox_event({'event_key': f'analysis.created:{aid}', 'event_type':'analysis.created', 'payload': {'analysis_id': aid, 'project_id': project_id}})
    if idempotency_key:
        try:
            repository.create_idempotency(idempotency_key, {'project_id': project_id, 'fingerprint': fingerprint, 'analysis_id': aid})
        except ValueError:
            # 并发竞态:另一请求先写入;重读并按指纹裁决。
            # 注:演示仓储下竞争窗口内的重复 analysis/outbox 为孤儿记录,无害;
            # 生产实现应在同一事务内完成 analysis+outbox+幂等写入。
            existing = repository.get_idempotency(idempotency_key)
            if existing and existing['fingerprint'] != fingerprint:
                raise HTTPException(409, detail={'code':'idempotency_conflict'})
            if existing:
                return analyses[existing['analysis_id']]
    if os.getenv('RUN_WORKER_INLINE', '').lower() in ('1', 'true', 'yes'):
        worker.run(aid)
    return analyses[aid]

@app.get('/api/v1/projects/{project_id}/outbox/status')
def outbox_status(project_id: str, user: dict = Depends(require_project_access)):
    events = [e for e in repository.list_pending_outbox() if e.get('payload', {}).get('project_id') == project_id]
    return {'pending': len(events), 'items': events}
@app.get('/api/v1/projects/{project_id}/analyses')
def list_analyses(project_id: str, page: int = 1, page_size: int = 20, user: dict = Depends(require_project_access)):
    page, page_size = _page(page, page_size)
    all_items = [a for a in analyses.values() if a['project_id']==project_id]
    start = (page - 1) * page_size
    return {'items': [_redacted_out(a) for a in all_items[start:start + page_size]], 'total': len(all_items), 'page': page, 'page_size': page_size}
@app.get('/api/v1/projects/{project_id}/analyses/{analysis_id}')
def get_analysis(project_id: str, analysis_id: str, user: dict = Depends(require_project_access)):
    a=analyses.get(analysis_id)
    if not a or a['project_id'] != project_id: raise HTTPException(404, detail={'code':'analysis_not_found'})
    return _redacted_out(a)
@app.post('/api/v1/projects/{project_id}/analyses/{analysis_id}/retry')
def retry_analysis(project_id: str, analysis_id: str, user: dict = Depends(require_project_analyst)):
    a=get_analysis(project_id, analysis_id)
    if a.get('status') not in ('error','cancelled'): raise HTTPException(409, detail={'code':'analysis_not_retryable'})
    worker.retry(analysis_id)
    if os.getenv('USE_CELERY', '').lower() in ('1','true','yes'):
        from .celery_tasks import run_analysis_task
        if getattr(run_analysis_task, 'delay', None): run_analysis_task.delay(analysis_id)
    elif os.getenv('RUN_WORKER_INLINE', '').lower() in ('1','true','yes'): worker.run(analysis_id)
    return _redacted_out(analyses[analysis_id])
@app.post('/api/v1/projects/{project_id}/analyses/{analysis_id}/cancel')
def cancel_analysis(project_id: str, analysis_id: str, user: dict = Depends(require_project_analyst)):
    get_analysis(project_id, analysis_id)
    return worker.cancel(analysis_id)


from fastapi.responses import Response, JSONResponse
import csv
import io
import json

# Domain read models backed by repository
if not repository.get_project('demo-project'):
    try:
        repository.create_project({'id':'demo-project','name':'VoiceLens Demo Project'})
    except ValueError:
        pass
# W03 成员种子:登录会话按真实成员关系构建,demo 演示账号必须能进入 demo-project
for seed in (
    {'project_id':'demo-project','user_id':'demo-user','role':'OWNER','display_name':'Demo Analyst'},
    {'project_id':'demo-project','user_id':'viewer-user','role':'VIEWER','display_name':'Demo Viewer'},
):
    if repository.get_membership(seed['project_id'], seed['user_id']) is None:
        try:
            repository.create_membership(seed)
        except ValueError:
            pass
reviews = {}
# 演示种子:severity/review_state/task 状态使用规范枚举;两种仓储均为「空则注入」。
# SQL 模式下非模型列的富字段(rule/due_at 等)由仓储按列过滤,基础演示不受影响。
if not repository.list_entities('risks', 'demo-project'):
    repository.create_entity('risks', {'id':'risk-001','project_id':'demo-project','title':'退款率异常','rule':'R-204 · 近30天','severity':'HIGH','review_state':'pending','status':'OPEN'})
    repository.create_entity('risks', {'id':'risk-002','project_id':'demo-project','title':'支付失败率突增','rule':'R-302 · 近24小时','severity':'CRITICAL','review_state':'pending','status':'OPEN'})
    repository.create_entity('risks', {'id':'risk-003','project_id':'demo-project','title':'订单金额缺失','rule':'R-101 · 完整性','severity':'MEDIUM','review_state':'confirmed','status':'IN_PROGRESS'})
if not repository.list_entities('tasks', 'demo-project'):
    for seed in (
        {'id':'task-001','title':'退款率异常整改','owner':'数据团队','owner_id':'owner-1','state':'IN_PROGRESS','priority':'HIGH','source':'关联风险 R-204','due_at':'2026-09-08T18:00:00+08:00','acceptance':'退款率回落并复核一周','effect_status':'NOT_EVALUATED'},
        {'id':'task-002','title':'支付失败率复盘','owner':'运营团队','owner_id':'owner-2','state':'OPEN','priority':'CRITICAL','source':'关联风险 R-302','due_at':'2026-09-15T18:00:00+08:00','acceptance':'失败率恢复正常区间','effect_status':'NOT_EVALUATED'},
        {'id':'task-003','title':'字段治理复核','owner':'运营团队','owner_id':'owner-3','state':'PENDING_REVIEW','priority':'MEDIUM','source':'关联风险 R-101','due_at':'2026-09-20T18:00:00+08:00','acceptance':'时间字段缺失率低于 1%','effect_status':'NOT_EVALUATED'},
    ):
        repository.create_entity('tasks', {**seed, 'project_id':'demo-project', 'status':seed['state'], 'version':1, 'events':[], 'idempotency_keys':[]})
if not repository.list_entities('reviews', 'demo-project'):
    # W17 复盘:固定口径结果(黄金样例),不可比样例单独一条
    repository.create_entity('reviews', {
        'id':'review-001','project_id':'demo-project','run_id':'run_demo_001','revision':1,
        'topic_version_ids':['delivery'], 'task_id':None,
        'before':{'n':168,'N':1000}, 'after':{'n':102,'N':1000},
        'metrics':{'count_change':-66,'share_before_pp':16.8,'share_after_pp':10.2,'share_delta_pp':-6.6,'relative_share_change':-0.3929,'comparable':True},
        'effect_status':'OBSERVED_CHANGE', 'limitations':[],
        'status':'pending','finding':'复盘:物流体验占比变化','confirmed_by':None,
    })
    repository.create_entity('reviews', {
        'id':'review-002','project_id':'demo-project','run_id':'run_demo_001','revision':1,
        'topic_version_ids':['refund'], 'task_id':None,
        'before':{'n':0,'N':0}, 'after':{'n':12,'N':400},
        'metrics':{'count_change':12,'share_before_pp':None,'share_after_pp':None,'share_delta_pp':None,'relative_share_change':None,'comparable':False},
        'effect_status':'INSUFFICIENT_DATA', 'limitations':['数据不足,暂不输出变化结论'],
        'status':'pending','finding':'复盘:退款进度(数据不足)','confirmed_by':None,
    })
def _project(pid): return repository.get_project(pid)
@app.get('/api/v1/projects')
def list_projects(user: dict = Depends(require_user)):
    items = repository.list_projects()
    if not user.get("demo_bypass"):
        allowed = {item["project_id"] for item in user.get("projects", [])}
        items = [item for item in items if item["id"] in allowed]
    return {'items': items, 'total': len(items)}

class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    timezone: str = Field(min_length=1)

@app.post('/api/v1/projects', status_code=201)
def create_project(req: ProjectCreateRequest, user: dict = Depends(require_user)):
    """创建项目(W03):公开注册关闭,仅已登录用户;创建者成为 OWNER 成员。"""
    project_id = 'proj_' + uuid4().hex[:10]
    project = repository.create_project({'id': project_id, 'name': req.name, 'timezone': req.timezone})
    try:
        repository.create_membership({'project_id': project_id, 'user_id': user['id'],
                                      'role': 'OWNER', 'display_name': user.get('name')})
    except ValueError:
        # 新建项目不可能已有成员;并发下以先写入者为准
        pass
    return project

@app.get('/api/v1/projects/{project_id}')
def get_project(project_id: str, user: dict = Depends(require_project_access)):
    project = repository.get_project(project_id)
    if not project: raise HTTPException(404, detail={'code':'project_not_found'})
    return project

def _require_project(project_id: str) -> None:
    if repository.get_project(project_id) is None:
        raise HTTPException(404, detail={'code': 'project_not_found'})

@app.get('/api/v1/projects/{project_id}/members')
def list_project_members(project_id: str, user: dict = Depends(require_project_access)):
    """项目成员列表(W03):供任务选择负责人;只含本项目成员,不暴露其他项目。"""
    _require_project(project_id)
    items = [{'id': m['user_id'], 'display_name': m.get('display_name') or m['user_id'], 'role': m.get('role')}
             for m in repository.list_members(project_id)]
    return {'items': items, 'total': len(items)}

# W03 项目设置:对外只暴露白名单键(timezone/limits/rules/model_available),
# settings_json 里的其他内容一律不透传——密钥与上游内部地址不在出站契约里。
_DEFAULT_PROJECT_TIMEZONE = 'UTC'
_DEFAULT_PROJECT_LIMITS = {'max_feedback_rows': 5000, 'max_upload_bytes': MAX_BYTES}
_DEFAULT_PROJECT_RULES = {'min_severity': 'LOW', 'scan_on_import': True}

def _settings_view(project_id: str) -> dict:
    stored = repository.get_project_settings(project_id) or {}
    return {
        'timezone': stored.get('timezone') or _DEFAULT_PROJECT_TIMEZONE,
        'limits': stored.get('limits') or _DEFAULT_PROJECT_LIMITS,
        'rules': stored.get('rules') or _DEFAULT_PROJECT_RULES,
        'model_available': bool(stored.get('model_available', True)),
        'version': int(stored.get('version') or 1),
    }

@app.get('/api/v1/projects/{project_id}/settings')
def get_project_settings(project_id: str, user: dict = Depends(require_project_access)):
    """项目设置(W03):时区、限额、规则与模型可用性;不含密钥或上游内部地址。"""
    _require_project(project_id)
    return _settings_view(project_id)

class ProjectSettingsPatch(BaseModel):
    expected_version: int
    timezone: str | None = None
    limits: dict | None = None
    rules: dict | None = None
    model_available: bool | None = None

@app.patch('/api/v1/projects/{project_id}/settings')
def update_project_settings(project_id: str, req: ProjectSettingsPatch, user: dict = Depends(require_project_owner)):
    """修改项目设置(W03):仅 OWNER;乐观锁 expected_version 冲突 409;只影响下次分析。"""
    _require_project(project_id)
    version = _settings_view(project_id)['version']
    if int(req.expected_version) != version:
        raise HTTPException(409, detail={'code': 'VERSION_CONFLICT'})
    changes = req.model_dump(exclude_none=True)
    changes.pop('expected_version', None)
    if not changes:
        raise HTTPException(422, detail={'code': 'no_fields'})
    changes['version'] = version + 1
    repository.update_project_settings(project_id, changes)
    return _settings_view(project_id)

# —— 工程计划 7.7:行动首页只读聚合契约 ——
@app.get('/api/v1/projects/{project_id}/summary')
def project_summary(
    project_id: str,
    run_id: str | None = Query(None),
    revision: int | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    channel: str | None = Query(None),
    product: str | None = Query(None),
    user: dict = Depends(require_project_access),
):
    """行动首页聚合(7.7):insight 绑定所选分析+筛选;action 绑定项目全部任务。

    无已发布 run 时洞察指标为 null 而非 0;只给 revision 不给 run_id 返回 422;
    指定不存在或外项目 run 返回 404,不悄悄换成默认 run。
    """
    from .summary import SummaryRequestError, build_summary
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    try:
        return build_summary(
            list(analyses.values()), repository.list_entities('tasks', project_id), project_id,
            run_id=run_id, revision=revision,
            filters={'start': start, 'end': end, 'channel': channel, 'product': product},
        )
    except SummaryRequestError as exc:
        raise HTTPException(exc.status_code, detail={'code': exc.code})
@app.get('/api/v1/projects/{project_id}/topics')
def list_topics(project_id: str, user: dict = Depends(require_project_access)):
    """主题洞察列表:优先返回已发布 revision(W11),无发布时回退合成演示数据。"""
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    published = _latest_published_run(project_id)
    if published is not None:
        from .topics import list_topics_from_run
        snapshot = published.get('result') or {}
        total = int(snapshot.get('unassigned_count') or 0) + sum(
            int(t.get('feedback_count') or 0) for t in snapshot.get('topics') or []
        )
        rows = [
            {
                'id': t['topic_id'], 'title': t['name'], 'feedbackCount': t['feedback_count'],
                'denominator': total, 'ratio': round((t['feedback_count'] / total) * 100, 1) if total else 0,
                'trend': None, 'cpiDisplayValue': None, 'reviewState': 'pending',
                'evidence': {'topicId': t['topic_id'], 'topicTitle': t['name'], 'runId': published['id'],
                             'revision': snapshot['revision'], 'summary': t.get('summary', ''),
                             'cpi': None,
                             # 引文必须来自本 run 发布的证据。此前这里是硬编码的空数组,
                             # 于是真实模式下证据面板的「原文与来源」永远空白,而 mock 有内容——
                             # 前端契约与后端实现各说各话,只有真连一次才看得出来。
                             'quotes': _evidence_quotes(published, t['topic_id'], snapshot.get('revision')),
                             'aiProvenance': {'origin': 'rule', 'needsReview': True, 'reviewRecord': None}},
            }
            for t in snapshot.get('topics') or []
        ]
        return {'items': rows, 'total': len(rows)}
    rows = [
        {'id': 'delivery', 'title': '物流体验', 'feedbackCount': 218, 'denominator': 1000, 'ratio': 21.8, 'trend': 'down', 'cpiDisplayValue': '68', 'reviewState': 'confirmed', 'evidence': {'topicId': 'delivery', 'topicTitle': '物流体验', 'runId': 'run_demo_001', 'revision': 1, 'summary': '配送等待与物流信息更新是主要关注点。', 'cpi': None, 'quotes': [], 'aiProvenance': {'origin': 'ai', 'needsReview': False, 'reviewRecord': None}}},
        {'id': 'refund', 'title': '退款进度', 'feedbackCount': 164, 'denominator': 1000, 'ratio': 16.4, 'trend': 'up', 'cpiDisplayValue': '82', 'reviewState': 'pending', 'evidence': {'topicId': 'refund', 'topicTitle': '退款进度', 'runId': 'run_demo_001', 'revision': 1, 'summary': '反馈关注退款处理时间和状态透明度。', 'cpi': None, 'quotes': [], 'aiProvenance': {'origin': 'ai', 'needsReview': True, 'reviewRecord': None}}},
        {'id': 'product', 'title': '产品使用', 'feedbackCount': 121, 'denominator': 1000, 'ratio': 12.1, 'trend': 'flat', 'cpiDisplayValue': '54', 'reviewState': 'pending', 'evidence': {'topicId': 'product', 'topicTitle': '产品使用', 'runId': 'run_demo_001', 'revision': 1, 'summary': '使用引导与功能说明仍有改善空间。', 'cpi': None, 'quotes': [], 'aiProvenance': {'origin': 'rule', 'needsReview': True, 'reviewRecord': None}}},
    ]
    return {'items': rows, 'total': len(rows)}


def _evidence_quotes(run: dict, topic_id: str, revision) -> list[dict]:
    """把已发布主题的证据映射成前端引文契约(EvidenceQuoteItem)。

    引文是脱敏正文里的精确子串,offset 为其 Unicode 字符位置——前端据此高亮,
    不能自行猜 token 位置(计划 8.2)。
    """
    evidence = ((run.get('result') or {}).get('evidence_by_topic') or {}).get(topic_id) or []
    sources = {feedback_id: text for feedback_id, text in _run_sources(run).items()}
    quotes: list[dict] = []
    for item in evidence:
        feedback_id = str(item.get('feedback_id') or '')
        text = sources.get(feedback_id, '')
        start = int(item.get('quote_start') or 0)
        end = int(item.get('quote_end') or 0)
        quotes.append({
            'feedbackId': feedback_id,
            'text': text,
            'start': start,
            'end': end,
            'channel': item.get('channel'),
            'occurredAt': item.get('occurred_at'),
            'rowIndex': item.get('source_row'),
        })
    return quotes


def _run_sources(run: dict) -> dict[str, str]:
    """run 输入集合的 feedback_id → 脱敏正文。"""
    from .ingestion import iter_run_feedback, row_text
    return {feedback_id: row_text(row) for feedback_id, row in iter_run_feedback(run)}


def _latest_published_run(project_id: str) -> dict | None:
    """本项目最近已发布 revision 的 run;无发布返回 None。"""
    published = None
    for run in analyses.values():
        if run.get('project_id') != project_id:
            continue
        revision = (run.get('result') or {}).get('revision')
        if not revision:
            continue
        if published is None or int(revision) >= int(published['result']['revision']):
            published = run
    return published

@app.get('/api/v1/projects/{project_id}/topics/{topic_id}/evidence')
def get_topic_evidence(project_id: str, topic_id: str, topic_version_id: int | None = Query(None), user: dict = Depends(require_project_access)):
    """主题证据:仅返回本 run 输入内的记录;版本不匹配/不存在返回 404。"""
    from .topics import RevisionNotFound, TopicNotFound, topic_evidence_from_run
    published = _latest_published_run(project_id)
    if published is None:
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    try:
        items = topic_evidence_from_run(published, topic_id, topic_version_id)
    except (TopicNotFound, RevisionNotFound):
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    return {'items': items, 'total': len(items)}
class CorrectionRequest(BaseModel):
    operation: str
    expected_revision: int
    name: str | None = None
    source_topic_ids: list[str] | None = None
    feedback_ids: list[str] | None = None
    reason: str = Field(min_length=1)

@app.post('/api/v1/projects/{project_id}/topics/{topic_id}/corrections', status_code=201)
def correct_topic(project_id: str, topic_id: str, req: CorrectionRequest, user: dict = Depends(require_project_analyst)):
    """W13 校正:RENAME/MERGE/SPLIT/CREATE;乐观锁 expected_revision,并发只有一个成功(409);
    新快照 revision+1,旧版本保留在 revision_history。"""
    from .pipeline import _flatten_rows
    from .versioning import CorrectionConflict, TopicNotFound, apply_correction
    published = _latest_published_run(project_id)
    if published is None:
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    _rows, sources, _total = _flatten_rows(published)
    params = {'topic_id': topic_id, 'name': req.name,
              'source_topic_ids': req.source_topic_ids, 'feedback_ids': req.feedback_ids}
    try:
        new_snapshot, history, affected = apply_correction(
            published, req.operation, req.expected_revision, params, req.reason, sources)
    except CorrectionConflict:
        raise HTTPException(409, detail={'code': 'correction_conflict'})
    except TopicNotFound:
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    except ValueError as exc:
        raise HTTPException(422, detail={'code': 'invalid_correction', 'message': str(exc)})
    repository.update_analysis(published['id'], {'result': new_snapshot, 'revision_history': history})
    return {'revision': new_snapshot['revision'], 'affected_topic_ids': affected}

@app.get('/api/v1/projects/{project_id}/topics/{topic_id}')
def get_topic_detail(project_id: str, topic_id: str, topic_version_id: int | None = Query(None), user: dict = Depends(require_project_access)):
    """主题详情:默认当前 revision,传 topic_version_id 可查任意旧版本(不可变)。"""
    from .versioning import snapshot_at
    published = _latest_published_run(project_id)
    if published is None:
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    snapshot = snapshot_at(published, topic_version_id) if topic_version_id is not None else (published.get('result') or {})
    if not snapshot:
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    topic = next((t for t in snapshot.get('topics') or [] if t['topic_id'] == topic_id), None)
    if topic is None:
        raise HTTPException(404, detail={'code': 'topic_not_found'})
    return {'topic': topic, 'evidence': snapshot.get('evidence_by_topic', {}).get(topic_id, []), 'revision': snapshot.get('revision')}
@app.get('/api/v1/projects/{project_id}/trend')
def list_trend(project_id: str, user: dict = Depends(require_project_access)):
    """反馈趋势。演示环境返回合成点列(含一个缺失断点)。"""
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    points = [
        {'date': '08-26', 'value': 142}, {'date': '08-27', 'value': 151},
        {'date': '08-28', 'value': None}, {'date': '08-29', 'value': 158},
        {'date': '08-30', 'value': 149}, {'date': '08-31', 'value': 161},
        {'date': '09-01', 'value': 155},
    ]
    return {'items': points, 'total': len(points)}
def _risk_view(risk: dict) -> dict:
    """风险的前端契约视图:severity 与复核状态分开,列表与裁决返回同一形状。"""
    return {
        'id': risk.get('id'),
        'title': risk.get('title', ''),
        'rule': risk.get('rule', ''),
        'severity': str(risk.get('severity', 'MEDIUM')).upper(),
        'reviewState': risk.get('review_state', 'pending'),
        'status': str(risk.get('status', 'OPEN')).upper(),
        'version': int(risk.get('version') or 1),
        'reviewedBy': risk.get('reviewed_by'),
        'reviewReason': risk.get('review_reason'),
        'reviewedAt': risk.get('reviewed_at'),
    }


@app.get('/api/v1/projects/{project_id}/risks')
def list_risks(project_id: str, user: dict = Depends(require_project_access)):
    """风险队列(前端契约):severity 与 review_state 分开,候选不是已确认事故。"""
    mapped = [_risk_view(r) for r in repository.list_entities('risks', project_id)]
    return {'items': mapped, 'total': len(mapped)}
class RiskReviewRequest(BaseModel):
    decision: str          # confirmed | excluded | reopened
    reason: str = Field(min_length=1)
    expected_version: int | None = None

# 裁决动作 → 复核状态;重新审查回到待复核
_RISK_DECISIONS = {'confirmed': 'confirmed', 'exclude': 'excluded', 'excluded': 'excluded', 'reopen': 'pending', 'reopened': 'pending'}

@app.post('/api/v1/projects/{project_id}/risks/{risk_id}/reviews')
def review_risk(project_id: str, risk_id: str, req: RiskReviewRequest, user: dict = Depends(require_project_analyst)):
    """W14 风险裁决:确认/排除/重新审查;理由必填;版本冲突 409;写审计事件。

    候选不是既成事实:确认意味着人工核验通过,而不是系统判定事故。
    """
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    decision = _RISK_DECISIONS.get(req.decision.strip().lower())
    if decision is None:
        raise HTTPException(422, detail={'code': 'invalid_decision', 'allowed': ['confirmed', 'excluded', 'reopened']})
    if not req.reason.strip():
        raise HTTPException(422, detail={'code': 'reason_required'})
    risk = next((r for r in repository.list_entities('risks', project_id) if r.get('id') == risk_id), None)
    if risk is None:
        raise HTTPException(404, detail={'code': 'risk_not_found'})
    version = int(risk.get('version') or 1)
    if req.expected_version is not None and int(req.expected_version) != version:
        raise HTTPException(409, detail={'code': 'VERSION_CONFLICT'})
    updated = repository.update_entity('risks', risk_id, {
        'review_state': decision,
        'status': 'OPEN' if decision == 'confirmed' else 'CLOSED' if decision == 'excluded' else risk.get('status', 'OPEN'),
        'version': version + 1,
        'reviewed_by': user.get('id', 'demo-user'),
        'review_reason': req.reason.strip(),
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
    })
    _record_audit(project_id, 'risk.review', user, {'risk_id': risk_id, 'decision': decision})
    return _risk_view(updated)

def _record_audit(project_id: str, action: str, user: dict, detail: dict) -> None:
    """审计事件:只留元数据与理由,不落正文(规范 10.4:审计为脱敏元数据列表)。"""
    try:
        repository.create_entity('audits', {
            'id': f'audit_{uuid4().hex[:10]}', 'project_id': project_id, 'action': action,
            'actor': user.get('id', 'demo-user'), 'detail': detail,
            'created_at': datetime.now(timezone.utc).isoformat(),
        })
    except (ValueError, KeyError):
        # 审计表在演示仓储下可能未就绪;不因审计失败回滚业务动作
        pass

class DeletionTarget(BaseModel):
    target_type: str            # project | dataset
    target_id: str


class DeletionRequest(DeletionTarget):
    # 仅执行删除需要逐字确认;预览是只读查询,不要求提供
    confirm_name: str = Field(min_length=1)


@app.post('/api/v1/projects/{project_id}/deletions/preview')
def preview_project_deletion(project_id: str, req: DeletionTarget, user: dict = Depends(require_owner)):
    """只预览影响范围,不写入;OWNER 专有。确认前必须展示将失效的报告数量。"""
    from .deletions import DeletionError, preview_deletion
    try:
        return preview_deletion(repository, project_id, req.target_type, req.target_id)
    except DeletionError as exc:
        code = str(exc)
        raise HTTPException(404 if code.endswith('_not_found') else 422, detail={'code': code})


@app.post('/api/v1/projects/{project_id}/deletions', status_code=202)
def execute_project_deletion(project_id: str, req: DeletionRequest,
                             idempotency_key: str | None = Header(None),
                             user: dict = Depends(require_owner)):
    """执行删除:写 tombstone → 取消作业 → 级联清理 → 核验为零 → 最小回执。"""
    from .deletions import DeletionConflict, DeletionError, execute_deletion, get_deletion
    if idempotency_key:
        existing = repository.get_idempotency(idempotency_key)
        if existing:
            # 同一幂等键重复调用:返回首次执行的回执,不重复删除
            previous = get_deletion(repository, project_id, existing['analysis_id'])
            if previous is not None:
                return previous.get('receipt') or previous
    job_id = f'del_{uuid4().hex[:10]}'
    try:
        receipt = execute_deletion(repository, project_id, req.target_type, req.target_id,
                                   req.confirm_name, job_id, user.get('id', 'demo-user'))
    except DeletionConflict as exc:
        raise HTTPException(409, detail={'code': str(exc)})
    except DeletionError as exc:
        code = str(exc)
        raise HTTPException(404 if code.endswith('_not_found') else 422, detail={'code': code})
    _record_audit(project_id, 'project.deletion', user, {'job_id': job_id, 'target_type': req.target_type})
    if idempotency_key:
        repository.create_idempotency(idempotency_key, {
            'project_id': project_id, 'fingerprint': req.target_id, 'analysis_id': job_id,
        })
    return receipt


@app.get('/api/v1/projects/{project_id}/deletions/{job_id}')
def get_deletion_receipt(project_id: str, job_id: str, user: dict = Depends(require_owner)):
    """删除进度/回执:项目本体被清理后仍可查最小回执(不含正文)。"""
    from .deletions import get_deletion
    job = get_deletion(repository, project_id, job_id)
    if job is None:
        raise HTTPException(404, detail={'code': 'deletion_not_found'})
    # 与 POST 返回同一形状:已完成的直接给回执,进行中的给登记行
    return job.get('receipt') or job


@app.get('/api/v1/projects/{project_id}/audits')
def list_audits(project_id: str, page: int = 1, page_size: int = 20, user: dict = Depends(require_project_access)):
    """审计列表(脱敏元数据;OWNER 专有按工程计划 7.5,演示环境放开给项目成员只读)。"""
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    page, page_size = _page(page, page_size)
    items = repository.list_entities('audits', project_id)
    items.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)
    start = (page - 1) * page_size
    return {'items': items[start:start + page_size], 'total': len(items), 'page': page, 'page_size': page_size}

@app.get('/api/v1/projects/{project_id}/tasks')
def list_tasks(project_id: str, state: list[str] | None = Query(None), overdue: bool = False, user: dict = Depends(require_project_access)):
    """任务列表(前端契约):state 可多值,overdue=true 限定未关闭且逾期,取交集。"""
    _as_of = datetime.now(timezone.utc)
    mapped = []
    for t in repository.list_entities('tasks', project_id):
        due_at = t.get('due_at') or t.get('due')
        due_at = due_at if isinstance(due_at, str) else None
        is_overdue = False
        if due_at:
            try:
                is_overdue = datetime.fromisoformat(due_at) < _as_of
            except ValueError:
                is_overdue = False
        item = {
            'id': t.get('id'),
            'title': t.get('title', ''),
            'status': str(t.get('state') or t.get('status') or 'OPEN').upper(),
            'dueAt': due_at,
            'overdue': is_overdue,
            'owner': t.get('owner'),
            'priority': str(t.get('priority', 'MEDIUM')).upper(),
            'source': t.get('source'),
        }
        if state and item['status'] not in {s.upper() for s in state}:
            continue
        if overdue and not is_overdue:
            continue
        mapped.append(item)
    return {'items': mapped, 'total': len(mapped)}
@app.get('/api/v1/projects/{project_id}/reviews')
def list_reviews(project_id: str, user: dict = Depends(require_project_access)):
    items=repository.list_entities('reviews', project_id)
    return {'items':items,'total':len(items)}

# —— W15 任务状态机路由 ——
class TaskDraftRequest(BaseModel):
    source_topic_version_id: str | None = None
    evidence_ids: list[str] = []
    title: str = Field(min_length=1)

class TaskConfirmRequest(BaseModel):
    expected_version: int
    owner_id: str
    due_at: str
    acceptance: str

class TaskTransitionRequest(BaseModel):
    action: str
    expected_version: int
    comment: str = ''
    material_refs: list[str] = []

def _find_task(project_id: str, task_id: str) -> dict | None:
    for task in repository.list_entities('tasks', project_id):
        if task.get('id') == task_id:
            return task
    return None

@app.post('/api/v1/projects/{project_id}/tasks/drafts', status_code=201)
def create_task_draft(project_id: str, req: TaskDraftRequest, user: dict = Depends(require_project_analyst)):
    """草稿:来源为已保存主题版本/规则模板,响应不等待外部 LLM。"""
    task = {
        'id': 'task_' + uuid4().hex[:8], 'project_id': project_id, 'title': req.title,
        'source': req.source_topic_version_id or 'manual', 'owner_id': None, 'due_at': None,
        'acceptance': None, 'state': 'DRAFT', 'version': 1, 'priority': 'MEDIUM',
        'events': [], 'effect_status': 'NOT_EVALUATED', 'idempotency_keys': [],
    }
    repository.create_entity('tasks', task)
    return task

@app.post('/api/v1/projects/{project_id}/tasks/{task_id}/confirm')
def confirm_task(project_id: str, task_id: str, req: TaskConfirmRequest, idempotency_key: str | None = Header(None), user: dict = Depends(require_project_analyst)):
    """草稿确认:owner/due/acceptance 必填;同 Idempotency-Key 重复确认不产生第二次事件。"""
    task = _find_task(project_id, task_id)
    if task is None:
        raise HTTPException(404, detail={'code': 'task_not_found'})
    if idempotency_key and idempotency_key in task.get('idempotency_keys', []):
        return task
    try:
        from .tasks import FieldValidationError, InvalidTransition, VersionConflict, confirm_draft
        confirm_draft(task, req.expected_version, req.owner_id, req.due_at, req.acceptance, user.get('id', 'demo-user'))
    except VersionConflict:
        raise HTTPException(409, detail={'code': 'VERSION_CONFLICT'})
    except InvalidTransition:
        raise HTTPException(409, detail={'code': 'INVALID_TRANSITION'})
    except FieldValidationError as exc:
        raise HTTPException(422, detail={'code': 'field_required', 'message': str(exc)})
    if idempotency_key:
        task.setdefault('idempotency_keys', []).append(idempotency_key)
    # list_entities 返回快照副本,状态与事件必须显式写回仓储(同一次更新)
    repository.update_entity('tasks', task_id, task)
    return task

@app.post('/api/v1/projects/{project_id}/tasks/{task_id}/transition')
def transition_task_route(project_id: str, task_id: str, req: TaskTransitionRequest, idempotency_key: str | None = Header(None), user: dict = Depends(require_project_analyst)):
    """状态机流转:草稿不能直接验收;负责人不得自验收;事件与状态同次提交。"""
    task = _find_task(project_id, task_id)
    if task is None:
        raise HTTPException(404, detail={'code': 'task_not_found'})
    if idempotency_key and idempotency_key in task.get('idempotency_keys', []):
        return task
    is_assignee = bool(task.get('owner_id')) and task.get('owner_id') == user.get('id')
    try:
        from .tasks import InvalidTransition, VersionConflict, transition_task
        transition_task(task, req.action, req.expected_version, user.get('id', 'demo-user'),
                        user.get('role', 'ANALYST'), is_assignee, req.comment)
    except VersionConflict:
        raise HTTPException(409, detail={'code': 'VERSION_CONFLICT'})
    except InvalidTransition:
        raise HTTPException(409, detail={'code': 'INVALID_TRANSITION'})
    if idempotency_key:
        task.setdefault('idempotency_keys', []).append(idempotency_key)
    # list_entities 返回快照副本,状态与事件必须显式写回仓储(同一次更新)
    repository.update_entity('tasks', task_id, task)
    return task

class TaskPatchRequest(BaseModel):
    expected_version: int
    # 允许修改的字段;未出现的字段不动
    title: str | None = None
    source: str | None = None
    priority: str | None = None
    due_at: str | None = None
    acceptance: str | None = None


# 草稿与正式任务采用不同可改字段清单(工程计划 7.5);
# state 一律经状态机端点变更,不在 PATCH 里改
_DRAFT_EDITABLE = {'title', 'source', 'priority'}
_FORMAL_EDITABLE = {'due_at', 'acceptance', 'priority'}


@app.patch('/api/v1/projects/{project_id}/tasks/{task_id}')
def patch_task(project_id: str, task_id: str, req: TaskPatchRequest,
               user: dict = Depends(require_project_analyst)):
    """编辑任务字段:草稿与正式任务可改字段不同;乐观锁冲突 409。"""
    from .tasks import state_of
    task = _find_task(project_id, task_id)
    if task is None:
        raise HTTPException(404, detail={'code': 'task_not_found'})
    version = int(task.get('version') or 1)
    if int(req.expected_version) != version:
        raise HTTPException(409, detail={'code': 'VERSION_CONFLICT'})
    changes = {key: value for key, value in req.model_dump(exclude_none=True).items()
               if key not in ('expected_version',)}
    if not changes:
        raise HTTPException(422, detail={'code': 'no_fields'})
    editable = _DRAFT_EDITABLE if state_of(task) == 'DRAFT' else _FORMAL_EDITABLE
    disallowed = sorted(set(changes) - editable)
    if disallowed:
        raise HTTPException(422, detail={'code': 'field_not_editable', 'fields': disallowed,
                                         'state': state_of(task), 'editable': sorted(editable)})
    task.update(changes)
    task['version'] = version + 1
    repository.update_entity('tasks', task_id, task)
    return task


@app.get('/api/v1/projects/{project_id}/feedback/{feedback_id}')
def get_feedback(project_id: str, feedback_id: str, user: dict = Depends(require_project_access)):
    """证据源:脱敏全文、源行号、来源、时间与分块;不返回原始文件。"""
    from .feedback import FeedbackNotFound, find_feedback
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    try:
        return find_feedback(repository, project_id, feedback_id)
    except FeedbackNotFound:
        # 外项目或不存在的反馈一律 404,不暴露存在性
        raise HTTPException(404, detail={'code': 'feedback_not_found'})


@app.get('/api/v1/projects/{project_id}/tasks/{task_id}')
def get_task(project_id: str, task_id: str, user: dict = Depends(require_project_access)):
    """任务详情:task + source_snapshot + events + version。"""
    task = _find_task(project_id, task_id)
    if task is None:
        raise HTTPException(404, detail={'code': 'task_not_found'})
    return {'task': task, 'source_snapshot': task.get('source'), 'events': task.get('events', []),
            'version': task.get('version', 1)}

# —— W17 复盘路由 ——
class ReviewWindow(BaseModel):
    start: str
    end: str


class ReviewCreateRequest(BaseModel):
    """计划 7.5 冻结契约:两个窗口 + filters + alignment,不含 n/N。

    调用方给数字的接口等于没有口径——窗口是否等长、是否重叠、主题是否属于该
    revision、样本是否够,全都无从校验。分子分母由服务端从 run 推导。
    """
    task_id: str | None = None
    run_id: str
    revision: int
    topic_version_ids: list[str] = []
    before: ReviewWindow
    after: ReviewWindow
    filters: dict = {}
    alignment_confirmed: bool = False

@app.post('/api/v1/projects/{project_id}/reviews', status_code=201)
def create_review(project_id: str, req: ReviewCreateRequest, user: dict = Depends(require_project_analyst)):
    """复盘创建:口径由服务端从 run 推导(计划 8.7);不可比 → insufficient,不输出改善结论。"""
    from .reviews import INSUFFICIENT, WindowSpec, compute_review
    run = analyses.get(req.run_id)
    if not run or run.get('project_id') != project_id:
        raise HTTPException(404, detail={'code': 'analysis_not_found'})

    computation = compute_review(
        run,
        revision=req.revision,
        topic_version_ids=req.topic_version_ids,
        before=WindowSpec(req.before.start, req.before.end),
        after=WindowSpec(req.after.start, req.after.end),
        filters=req.filters,
        alignment_confirmed=req.alignment_confirmed,
    )
    review = {
        'id': 'review_' + uuid4().hex[:8], 'project_id': project_id, 'run_id': req.run_id,
        'revision': req.revision, 'topic_version_ids': req.topic_version_ids, 'task_id': req.task_id,
        'before': computation.before.__dict__, 'after': computation.after.__dict__,
        'filters': req.filters, 'alignment_confirmed': req.alignment_confirmed,
        'metrics': computation.metrics.__dict__ if computation.metrics else None,
        # 可比才给效果判断;低样本保留数量但不宣称变化
        'effect_status': 'OBSERVED_CHANGE' if computation.comparable else 'INSUFFICIENT_DATA',
        'comparability': computation.comparability,
        'reasons': list(computation.reasons),
        'limitations': list(computation.reasons) or ['变化是观察到的,不构成因果证明'],
    }
    repository.create_entity('reviews', review)
    return review

@app.get('/api/v1/projects/{project_id}/reviews/{review_id}')
def get_review(project_id: str, review_id: str, user: dict = Depends(require_project_access)):
    """复盘详情:固定统计结果、分母、版本与限制;不可比不显示改善。"""
    for review in repository.list_entities('reviews', project_id):
        if review.get('id') == review_id:
            return review
    raise HTTPException(404, detail={'code': 'review_not_found'})

@app.post('/api/v1/projects/{project_id}/reviews/{review_id}/confirm')
def confirm_review(project_id: str, review_id: str, user: dict = Depends(require_project_analyst)):
    if not any(item['id'] == review_id for item in repository.list_entities('reviews', project_id)):
        raise HTTPException(404, detail={'code':'review_not_found'})
    try: r=repository.update_entity('reviews', review_id, {'status':'confirmed','confirmed_by':user.get('id','demo-user'),'confirmed_at':datetime.now(timezone.utc)})
    except KeyError: raise HTTPException(404, detail={'code':'review_not_found'})
    if r['project_id'] != project_id: raise HTTPException(404, detail={'code':'review_not_found'})
    return r
@app.get('/api/v1/projects/{project_id}/exports/redacted.csv')
def export_redacted(project_id: str, user: dict = Depends(require_project_access)):
    """Export only the redacted dataset previews belonging to *project_id*.

    The payload intentionally keeps each row in a JSON column.  This avoids
    leaking arbitrary source column names while preserving nested/duplicate
    fields, and applies redaction once more at the export boundary so a
    repository populated by an older parser cannot emit raw PII.
    """
    if not repository.get_project(project_id):
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



class ExportRequest(BaseModel):
    scope: str = 'project'          # 首版仅 CSV,项目范围
    run_id: str | None = None
    review_id: str | None = None


@app.post('/api/v1/projects/{project_id}/exports', status_code=202)
def create_project_export(project_id: str, req: ExportRequest, idempotency_key: str | None = Header(None),
                          user: dict = Depends(require_project_analyst)):
    """创建导出任务:只导出脱敏字段;24 小时失效,不提供永久链接。"""
    from .exports import create_export
    if not repository.get_project(project_id):
        raise HTTPException(404, detail={'code': 'project_not_found'})
    if req.scope not in ('project', 'dataset'):
        raise HTTPException(422, detail={'code': 'unsupported_scope'})
    if idempotency_key:
        previous = repository.get_idempotency(idempotency_key)
        if previous:
            from .exports import get_export, view as export_view
            existing = get_export(repository, project_id, previous['analysis_id'])
            if existing is not None:
                return export_view(existing)
    export_id = f'exp_{uuid4().hex[:10]}'
    rows: list[dict] = []
    for dataset in datasets.values():
        if dataset.get('project_id') != project_id:
            continue
        for index, row in enumerate((dataset.get('preview') or {}).get('rows') or []):
            # 与既有下载端点一致:导出边界再做一次脱敏,列固定不泄露任意来源列名
            clean = {str(key): redact_text(str(value))['text'] for key, value in (row or {}).items()}
            clean['dataset_id'] = dataset.get('id', '')
            clean['row_index'] = index
            rows.append(clean)
    columns = ['dataset_id', 'row_index', 'data']
    payload = [{'dataset_id': r['dataset_id'], 'row_index': r['row_index'],
                'data': json.dumps({k: v for k, v in r.items() if k not in ('dataset_id', 'row_index')},
                                   ensure_ascii=False, separators=(',', ':'))} for r in rows]
    result = create_export(repository, project_id, req.scope, payload, columns, export_id, user.get('id', 'demo-user'))
    _record_audit(project_id, 'export.created', user, {'export_id': export_id, 'rows': result['row_count']})
    if idempotency_key:
        repository.create_idempotency(idempotency_key, {
            'project_id': project_id, 'fingerprint': req.scope, 'analysis_id': export_id,
        })
    return result


@app.get('/api/v1/projects/{project_id}/exports/{export_id}')
def get_export_status(project_id: str, export_id: str, user: dict = Depends(require_project_access)):
    """导出状态与时效:不含正文;已失效/过期按 410 返回。"""
    from .exports import ExportError, download_export, view as export_view
    try:
        return export_view(download_export(repository, project_id, export_id))
    except ExportError as exc:
        code = str(exc)
        raise HTTPException(404 if code == 'export_not_found' else 410, detail={'code': code})


@app.get('/api/v1/projects/{project_id}/exports/{export_id}/download')
def download_project_export(project_id: str, export_id: str, user: dict = Depends(require_project_access)):
    """下载 CSV:每次重新鉴权;过期或已失效返回 410。"""
    from .exports import ExportError, download_export
    try:
        export = download_export(repository, project_id, export_id)
    except ExportError as exc:
        code = str(exc)
        raise HTTPException(404 if code == 'export_not_found' else 410, detail={'code': code})
    return Response(
        content=export.get('content') or '', media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{project_id}-redacted.csv"'},
    )


@app.delete('/api/v1/projects/{project_id}/datasets/{dataset_id}', status_code=204)
def delete_dataset(project_id: str, dataset_id: str, user: dict = Depends(require_project_analyst)):
    dataset = datasets.get(dataset_id)
    if not dataset or dataset.get('project_id') != project_id:
        raise HTTPException(404, detail={'code': 'dataset_not_found'})
    repository.delete_dataset(dataset_id)
    return Response(status_code=204)


