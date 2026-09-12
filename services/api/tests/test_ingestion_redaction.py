"""脱敏边界:持久业务正文只保留脱敏结果(工程计划 7.2 / 6.2 / 10.2)。

原始行只允许存在于上传请求内部。落库、下游流水线(向量、聚类、主题引文)、
看板过滤、导出与证据源一律只见脱敏内容——所以本文件断言的是「响应体里不含
原始值」,而不是某个字段恰好等于某个值。
"""
import hashlib
import hmac
import json
from uuid import uuid4

from app.config import dedupe_hmac_secret
from app.ingestion import parse_csv_text, redact_text
from app.main import repository
from app.pipeline import _flatten_rows
from support.client import make_client

client = make_client()

CSV_WITH_PII = (
    'email,phone,order,note\n'
    'person@example.com,13812345678,ORD-123456,物流很慢\n'
    'other@example.com,13900000000,ORD-654321,退款没到账\n'
).encode()

_RAW_VALUES = ('person@example.com', '13812345678', 'ORD-123456',
               'other@example.com', '13900000000', 'ORD-654321')


def _project() -> str:
    project_id = f'redact_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': 'Redaction Case'})
    return project_id


def _upload(project_id: str, payload: bytes = CSV_WITH_PII, name: str | None = None):
    return client.post(
        f'/api/v1/projects/{project_id}/datasets',
        files={'file': (name or f'batch-{uuid4().hex[:6]}.csv', payload, 'text/csv')},
        data={'consent': 'true'},
    )


def test_parser_returns_redacted_rows_but_counts_hits_on_raw():
    parsed = parse_csv_text(CSV_WITH_PII.decode())

    # 出函数的行已脱敏——下游拿到原始值的机会为零
    assert parsed['rows'][0] == {
        'email': '<EMAIL_REDACTED>', 'phone': '<PHONE_REDACTED>',
        'order': '<ORDER_ID_REDACTED>', 'note': '物流很慢',
    }
    # 命中数必须按**原始行**统计:先脱敏再统计会让这里恒为 0,健康报告就撒谎了
    assert parsed['stats']['redacted'] == 2
    assert parsed['stats']['total'] == 2


def test_uploaded_dataset_never_exposes_raw_pii():
    project_id = _project()
    assert _upload(project_id).status_code == 201

    listed = client.get(f'/api/v1/projects/{project_id}/datasets')
    assert listed.status_code == 200
    blob = json.dumps(listed.json(), ensure_ascii=False)
    for raw in _RAW_VALUES:
        assert raw not in blob, f'数据集列表泄漏了原始值 {raw}'
    assert '<EMAIL_REDACTED>' in blob


def test_validation_preview_never_exposes_raw_pii():
    project_id = _project()
    dataset_id = _upload(project_id).json()['id']

    validated = client.post(
        f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate',
        json={'expected_version': 1},
    )
    assert validated.status_code == 202
    blob = json.dumps(validated.json(), ensure_ascii=False)
    for raw in _RAW_VALUES:
        assert raw not in blob, f'校验响应泄漏了原始值 {raw}'


def test_pipeline_and_feedback_see_the_same_redacted_body():
    """证据引文与 GET /feedback 的正文同源,offset 才能在正文里定位(计划 8.2/744)。"""
    project_id = _project()
    dataset = _upload(project_id).json()

    rows, sources, _ = _flatten_rows({'datasets': [dataset]})
    assert rows, '流水线应至少展开出一条反馈'
    for row in rows:
        for raw in _RAW_VALUES:
            assert raw not in row['text'], f'流水线取数泄漏了原始值 {raw}'

    # 流水线写进 run 的正文,必须与证据源端点返回的正文逐字一致
    feedback_id = rows[0]['feedback_id']
    body = client.get(f'/api/v1/projects/{project_id}/feedback/{feedback_id}').json()
    assert body['text'] == sources[feedback_id]
    # 分块 offset 指向脱敏正文,可逐字复原
    for segment in body['segments']:
        assert body['text'][segment['start']:segment['end']] == segment['text']


def test_redaction_survives_a_second_pass():
    """读取边界仍会再脱敏一次(纵深防御),对已脱敏正文必须是恒等变换。"""
    parsed = parse_csv_text(CSV_WITH_PII.decode())
    again = {key: redact_text(value)['text'] for key, value in parsed['rows'][0].items()}
    assert again == parsed['rows'][0]


def test_legacy_raw_rows_are_redacted_on_read():
    """存量行由旧解析器写入,没有机会重写——出站投影必须兜住。

    这条守住的是「纵深防御」:即使数据层里躺着原始值,响应体也不能带出去。
    """
    project_id = f'legacy_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': 'Legacy Case'})
    dataset_id = f'ds_legacy_{uuid4().hex[:6]}'
    repository.create_dataset({
        'id': dataset_id, 'project_id': project_id, 'name': '旧批次', 'rows': 1, 'version': 1,
        'preview': {'rows': [{'email': 'legacy@example.com', 'phone': '13800001111'}]},
    })
    run_id = f'run_legacy_{uuid4().hex[:6]}'
    repository.create_analysis({
        'id': run_id, 'project_id': project_id, 'dataset_ids': [dataset_id],
        'status': 'done', 'stage': 'completed', 'total': 1,
        'datasets': [repository.datasets[dataset_id]],
    })

    paths = [
        f'/api/v1/projects/{project_id}/datasets',
        f'/api/v1/projects/{project_id}/analyses',
        f'/api/v1/projects/{project_id}/analyses/{run_id}',
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        blob = json.dumps(response.json(), ensure_ascii=False)
        assert 'legacy@example.com' not in blob, f'{path} 泄漏存量原始值'
        assert '13800001111' not in blob, f'{path} 泄漏存量原始值'
        assert '<EMAIL_REDACTED>' in blob, f'{path} 未给出脱敏正文'

    # 校验响应里的 validation.preview 与 preview 是同一对象,两份都要脱敏
    validated = client.post(
        f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate',
        json={'expected_version': 1},
    )
    assert validated.status_code == 202
    blob = json.dumps(validated.json(), ensure_ascii=False)
    assert 'legacy@example.com' not in blob, '校验响应泄漏存量原始值'
    assert '13800001111' not in blob, '校验响应泄漏存量原始值'


def test_legacy_run_payloads_are_redacted_on_read():
    """run 快照由多个模块写入(数据集行、W08 规则扫描证据、W11 发布引文),
    逐个字段点名会漏,所以出站走递归兜底。这里按历史形状造一份「什么都有一点」。"""
    project_id = f'legacy_run_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': 'Legacy Run'})
    dataset_id = f'ds_lr_{uuid4().hex[:6]}'
    raw_row = {'email': 'legacy-run@example.com', 'phone': '13800002222'}
    repository.create_dataset({
        'id': dataset_id, 'project_id': project_id, 'name': '旧批次', 'rows': 1, 'version': 1,
        'preview': {'rows': [raw_row]},
        'validation': {'preview': {'rows': [raw_row]}},
    })
    run_id = f'run_lr_{uuid4().hex[:6]}'
    repository.create_analysis({
        'id': run_id, 'project_id': project_id, 'dataset_ids': [dataset_id],
        'status': 'done', 'stage': 'completed', 'total': 1,
        'datasets': [repository.datasets[dataset_id]],
        'analysis': {
            'summary': '规则扫描摘要', 'topics': [],
            'evidence': [{'row_index': 0, 'keyword': 'legacy-run',
                          'offset': {'start': 0, 'end': 10},
                          'text': 'legacy-run@example.com 13800002222'}],
        },
        'risk_findings': [{'rule_id': 'r1', 'severity': 'high',
                           'quote': 'legacy-run@example.com', 'snippet': '13800002222'}],
        'result': {'revision': 1, 'status': 'done', 'evidence_by_topic': {'t1': [
            {'feedback_id': 'fb_x', 'quote': 'legacy-run@example.com',
             'quote_start': 0, 'quote_end': 17}]}},
    })

    for path in (f'/api/v1/projects/{project_id}/analyses',
                 f'/api/v1/projects/{project_id}/analyses/{run_id}'):
        response = client.get(path)
        assert response.status_code == 200, path
        blob = json.dumps(response.json(), ensure_ascii=False)
        for raw in ('legacy-run@example.com', '13800002222'):
            assert raw not in blob, f'{path} 泄漏 {raw}'
        assert '<EMAIL_REDACTED>' in blob


def test_reupload_dedupe_echo_is_redacted():
    """重传同源文件时走的是「回显已存对象」分支,同样要过出站兜底。"""
    project_id = _project()
    dataset_id = f'ds_dup_{uuid4().hex[:6]}'
    secret, _fallback = dedupe_hmac_secret()
    event_key = hmac.new(secret.encode('utf-8'),
                         '\x1f'.join((project_id, '', 'csv', 'dup-legacy.csv')).encode('utf-8'),
                         hashlib.sha256).hexdigest()
    repository.create_dataset({
        'id': dataset_id, 'project_id': project_id, 'name': 'dup-legacy.csv', 'rows': 1, 'version': 1,
        'event_key': event_key, 'source_namespace': '', 'source_kind': 'csv',
        'content_hash': hashlib.sha256(CSV_WITH_PII).hexdigest(),
        'preview': {'rows': [{'email': 'person@example.com', 'phone': '13812345678'}]},
    })

    echoed = _upload(project_id, name='dup-legacy.csv')
    assert echoed.status_code == 200, '同源同内容应回显已存数据集'
    blob = json.dumps(echoed.json(), ensure_ascii=False)
    for raw in ('person@example.com', '13812345678'):
        assert raw not in blob, f'重传回显泄漏了 {raw}'
