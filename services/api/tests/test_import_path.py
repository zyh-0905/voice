"""真实导入路径: T解析/编码选择/字段映射/时间策略与 4.1 限额(工程计划 4.1—4.3)。

审计发现 .txt 静默变空批次、mapping 与 time_policy 收下不用、50 MiB 上限与
无行数限制——这里逐条钉住替代行为:结构化解析、显式编码失败即报错、标准字段
规范化、严格/静态时间口径,以及 413/422 限额与单活跃分析 409。
"""
import io
import json
from uuid import uuid4

import pytest

import app.main as main
from app.ingestion import apply_mapping, parse_txt_text, row_text, validate_mapping
from app.main import repository
from app.pipeline import _flatten_rows
from support.client import make_client
from support.feedback import seed_run_feedback

client = make_client()


def _project(prefix='imp'):
    return f'{prefix}_{uuid4().hex[:8]}'


def _upload(project_id, filename, payload, **form):
    data = {'consent': 'true', **form}
    return client.post(
        f'/api/v1/projects/{project_id}/datasets',
        files={'file': (filename, payload)},
        data=data,
    )


def _validate(project_id, dataset_id, body):
    return client.post(f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate', json=body)


# —— TXT 解析 ——

def test_txt_parser_treats_each_non_empty_line_as_feedback():
    """工程计划 4.5:TXT 一行一条反馈,空行跳过,形状与 CSV 一致。"""
    parsed = parse_txt_text('物流很慢\n\n退款没到账 a@example.com\n   \n')

    assert parsed['headers'] == ['content']
    assert parsed['rows'] == [{'content': '物流很慢'}, {'content': '退款没到账 <EMAIL_REDACTED>'}]
    # stats 基于原始行:脱敏命中数不能因为落库行已脱敏而恒为 0
    assert parsed['stats']['total'] == 2
    assert parsed['stats']['redacted'] == 1


def test_txt_upload_preview_has_csv_shape_and_validates():
    """审计缺口:TXT 上传曾经静默产生空批次;现在必须走与 CSV 相同的解析与治理路径。"""
    project_id = _project('txt')
    upload = _upload(project_id, 'notes.txt', '物流很慢\n\n退款没到账\n'.encode())

    assert upload.status_code == 201
    preview = upload.json()['preview']
    assert preview['headers'] == ['content']
    assert preview['rows'] == [{'content': '物流很慢'}, {'content': '退款没到账'}]
    assert preview['stats']['total'] == 2

    # 无显式映射时按同名字段识别 content(TXT 的默认路径),下游即可复用
    validated = _validate(project_id, upload.json()['id'], {})
    assert validated.status_code == 202
    rows = validated.json()['preview']['rows']
    assert [row['content'] for row in rows] == ['物流很慢', '退款没到账']
    assert all(row['channel'] == 'unknown' and row['product'] == 'unknown' for row in rows)
    assert all(row['time_quality'] == 'missing' for row in rows)


# —— 编码选择 ——

def test_explicit_gb18030_decoding_succeeds():
    """工程计划 4.1:用户可显式选择 GB18030,而不是只认 UTF-8。"""
    project_id = _project('gb')
    upload = _upload(project_id, 'gb.csv', 'content\n反馈很慢\n退款没到账\n'.encode('gb18030'),
                     encoding='gb18030')

    assert upload.status_code == 201
    assert [row['content'] for row in upload.json()['preview']['rows']] == ['反馈很慢', '退款没到账']


def test_wrong_encoding_reports_error_instead_of_replacement_characters():
    project_id = _project('badenc')
    payload = 'content\n反馈很慢\n'.encode('gb18030')

    response = _upload(project_id, 'gb.csv', payload)
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['code'] == 'invalid_file'
    assert 'utf-8' in detail['message'].lower() and '编码' in detail['message']
    # 失败即不建档:不允许把乱码预览悄悄存进仓储
    assert not [d for d in repository.datasets.values() if d.get('project_id') == project_id]


def test_unsupported_encoding_name_is_rejected():
    project_id = _project('encname')
    response = _upload(project_id, 'a.csv', b'content\nhi\n', encoding='latin-1')

    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'unsupported_encoding'


def test_utf8_bom_header_is_stripped_before_mapping():
    """UTF-8 BOM 不得混进第一列表头,否则标准字段识别与映射整批落空。"""
    project_id = _project('bom')
    upload = _upload(project_id, 'bom.csv', 'content\n带 BOM 的反馈\n'.encode('utf-8-sig'))

    assert upload.status_code == 201
    assert upload.json()['preview']['headers'] == ['content']
    validated = _validate(project_id, upload.json()['id'], {})
    assert validated.json()['preview']['rows'][0]['content'] == '带 BOM 的反馈'


# —— 字段映射 ——

def test_mapping_normalises_rows_to_standard_fields():
    """审计缺口:mapping 曾经收下不用;现在落库行必须规范化到 §4.2 标准字段。"""
    project_id = _project('map')
    csv = (
        'msg,ts,ch,prod,star,oid,st,fid\n'
        '快递很慢,2026-08-26 09:12:00,客服,手机,5,ORD-123456,open,ext-1\n'
        '匿名反馈,,,,,,,ext-2\n'
    ).encode()
    upload = _upload(project_id, 'm.csv', csv)
    assert upload.status_code == 201
    mapping = {'msg': 'content', 'ts': 'created_at', 'ch': 'channel', 'prod': 'product',
               'star': 'rating', 'oid': 'order_id', 'st': 'status', 'fid': 'feedback_id'}

    validated = _validate(project_id, upload.json()['id'], {
        'mapping': mapping, 'time_policy': 'static', 'timezone': 'Asia/Shanghai',
    })
    assert validated.status_code == 202
    body = validated.json()
    rows = body['preview']['rows']

    assert rows[0]['content'] == '快递很慢'
    assert rows[0]['channel'] == '客服' and rows[0]['product'] == '手机'
    assert rows[0]['rating'] == 5
    assert rows[0]['order_id'] == '<ORDER_ID_REDACTED>'
    assert rows[0]['status'] == 'open'
    assert rows[0]['feedback_id'] == 'ext-1'
    assert rows[0]['created_at'] == '2026-08-26T09:12:00+08:00'
    assert rows[0]['time_quality'] == 'exact'
    assert rows[0]['source_row'] == 0
    # §4.2:渠道/产品缺失落 unknown;无时间在静态模式标 missing
    assert rows[1]['channel'] == 'unknown' and rows[1]['product'] == 'unknown'
    assert rows[1]['time_quality'] == 'missing'
    assert 'created_at' not in rows[1]
    # 健康计数满足 input = valid + invalid + duplicate(§4.5)
    stats = body['preview']['stats']
    assert stats['total'] == stats['valid'] + stats['invalid'] + stats['duplicate']
    assert stats['valid'] == 2 and stats['missing_time'] == 1
    # 完整订单号不得出站
    assert 'ORD-123456' not in json.dumps(body, ensure_ascii=False)


def test_mapped_rows_still_feed_row_text_and_run_feedback():
    """映射后的行必须继续被流水线/证据源共用取数函数消费(正文只取 content)。

    校验落库后 `_flatten_rows` 走 `feedback` 实体表:这里指向**真实落库**的批次,
    而不是把行再抄一份进 run JSON——后者是一条生产上不存在的取数路径。
    """
    project_id = _project('feed')
    upload = _upload(project_id, 'm.csv', 'msg,ch\n快递很慢,客服\n'.encode())
    mapping = {'msg': 'content', 'ch': 'channel'}
    validated = _validate(project_id, upload.json()['id'], {'mapping': mapping})
    dataset = validated.json()

    assert row_text(dataset['preview']['rows'][0]) == '快递很慢'
    run = {'id': 'run_feed', 'project_id': project_id,
           'dataset_ids': [dataset['id']], 'datasets': [dataset]}
    seed_run_feedback(repository, run)  # 5.3:run 创建时冻结输入集合
    rows, sources, total = _flatten_rows(run, repository)
    assert total == 1
    assert rows[0]['source_row'] == 0
    assert sources['fb_' + dataset['id'] + '_0'] == '快递很慢'


def test_mapping_rejects_unknown_target_duplicate_and_missing_content():
    """非法映射返回 422,不能静默忽略成「没映射」——那会让用户以为已按标准治理。"""
    project_id = _project('mapbad')
    dataset_id = _upload(project_id, 'm.csv', b'msg\nhi\n').json()['id']

    unknown = _validate(project_id, dataset_id, {'mapping': {'msg': '正文'}})
    assert unknown.status_code == 422 and unknown.json()['detail']['code'] == 'invalid_mapping'

    missing_content = _validate(project_id, dataset_id, {'mapping': {'msg': 'channel'}})
    assert missing_content.status_code == 422
    assert missing_content.json()['detail']['code'] == 'invalid_mapping'

    ghost_source = _validate(project_id, dataset_id, {'mapping': {'不存在': 'content'}})
    assert ghost_source.status_code == 422

    # 同目标重复映射在 validate_mapping 内被拒绝,不能由后写者悄悄覆盖前者
    with pytest.raises(ValueError):
        validate_mapping({'a': 'content', 'b': 'content'}, ['a', 'b'])


def test_duplicate_rows_are_counted_not_added_as_feedback():
    project_id = _project('dup')
    upload = _upload(project_id, 'd.csv', 'msg\n同一条反馈\n同一条反馈\n'.encode())
    validated = _validate(project_id, upload.json()['id'], {'mapping': {'msg': 'content'}})
    stats = validated.json()['preview']['stats']

    assert stats['total'] == 2 and stats['duplicate'] == 1 and stats['valid'] == 1
    assert len(validated.json()['preview']['rows']) == 1


# —— 内容与评分约束 ——

def test_empty_and_formula_content_never_become_feedback():
    """工程计划 4.2/4.3:content 必填;公式字符串不能当客诉正文,应提示导出为值。"""
    project_id = _project('formula')
    upload = _upload(project_id, 'f.csv', 'msg,note\n=SUM(A1:A2),公式行\n,空正文\n正常反馈,x\n'.encode())
    validated = _validate(project_id, upload.json()['id'], {'mapping': {'msg': 'content'}})

    assert validated.status_code == 202
    body = validated.json()
    rows = body['preview']['rows']
    assert [row['content'] for row in rows] == ['正常反馈']
    codes = {(e['source_row'], e['code']) for e in body['validation']['errors']}
    assert (0, 'FORMULA_NOT_ALLOWED') in codes
    assert (1, 'CONTENT_REQUIRED') in codes
    # 公式字符串绝不能进入治理结果(§4.3),也绝不能落进 feedback 实体表。
    # 整份响应体都要干净:`source`(待映射暂存)虽是服务端内部字段,但不能出站——
    # 它带着未映射的原始单元格值,出站等于绕过 4.3 的边界。
    assert '=SUM' not in json.dumps(body, ensure_ascii=False)
    assert 'source' not in body, '待映射暂存不得出现在响应里'
    assert [row['content_redacted']
            for row in repository.list_feedback(project_id, [body['id']])] == ['正常反馈']


def test_overlong_content_is_invalid_and_keeps_source_row():
    """工程计划 4.1:内容长度 1—10,000 字符,超长行无效但保留源行号供修正。"""
    project_id = _project('long')
    upload = _upload(project_id, 'l.csv', ('msg,note\n' + 'x' * 10_001 + ',超长\n正常,x\n').encode())
    validated = _validate(project_id, upload.json()['id'], {'mapping': {'msg': 'content'}})

    body = validated.json()
    assert [(e['source_row'], e['code']) for e in body['validation']['errors']] == \
        [(0, 'CONTENT_TOO_LONG')]
    assert [row['source_row'] for row in body['preview']['rows']] == [1]


def test_rating_outside_configured_range_marks_row_invalid():
    """工程计划 4.2:rating 只接受配置范围 1—5,越界不能悄悄落库。"""
    project_id = _project('rating')
    upload = _upload(project_id, 'r.csv', 'msg,star\n差评,6\n好评,3\n'.encode())
    validated = _validate(project_id, upload.json()['id'],
                          {'mapping': {'msg': 'content', 'star': 'rating'}})

    body = validated.json()
    assert [(e['source_row'], e['code']) for e in body['validation']['errors']] == \
        [(0, 'RATING_OUT_OF_RANGE')]
    assert [(row['source_row'], row['rating']) for row in body['preview']['rows']] == [(1, 3)]


# —— 时间策略 ——

def test_strict_policy_rejects_rows_without_usable_created_at():
    """审计缺口:严格模式下 created_at 必填,收下 time_policy 不用不算实现。"""
    project_id = _project('strict')
    upload = _upload(project_id, 't.csv', 'msg,ts\n无时间,\n有时间,2026-08-26\n'.encode())
    validated = _validate(project_id, upload.json()['id'], {
        'mapping': {'msg': 'content', 'ts': 'created_at'}, 'time_policy': 'strict',
    })

    body = validated.json()
    assert body['state'] == 'READY_WITH_WARNINGS'
    assert [(e['source_row'], e['code']) for e in body['validation']['errors']] == \
        [(0, 'CREATED_AT_REQUIRED')]
    assert [row['content'] for row in body['preview']['rows']] == ['有时间']
    assert body['preview']['stats']['invalid'] == 1


def test_static_policy_keeps_undated_row_and_marks_time_quality_missing():
    """静态模式:无时间的记录仍可用来看主题与风险,但必须标 time_quality=missing。"""
    project_id = _project('static')
    upload = _upload(project_id, 't.csv', 'msg,ts\n无时间,\n有时间,2026-08-26\n'.encode())
    validated = _validate(project_id, upload.json()['id'], {
        'mapping': {'msg': 'content', 'ts': 'created_at'}, 'time_policy': 'static',
    })

    body = validated.json()
    rows = body['preview']['rows']
    assert [row['time_quality'] for row in rows] == ['missing', 'exact']
    assert 'created_at' not in rows[0]
    assert body['preview']['stats']['missing_time'] == 1
    assert body['state'] == 'READY_WITH_WARNINGS'


def test_timezone_applies_to_naive_timestamps_and_offset_times_go_utc():
    """工程计划 4.5:无偏移按用户选定时区解释,带偏移直接转 UTC。"""
    project_id = _project('tz')
    upload = _upload(project_id, 't.csv',
                     'msg,ts\n甲,2026-08-26 09:12:00\n乙,2026-08-26T09:12:00+09:00\n'.encode())
    validated = _validate(project_id, upload.json()['id'], {
        'mapping': {'msg': 'content', 'ts': 'created_at'},
        'time_policy': 'strict', 'timezone': 'Asia/Shanghai',
    })

    rows = validated.json()['preview']['rows']
    # 无偏移按用户选定时区解释;带偏移直接转 UTC(工程计划 4.5)
    assert rows[0]['created_at'] == '2026-08-26T09:12:00+08:00'
    assert rows[1]['created_at'] == '2026-08-26T00:12:00+00:00'


def test_dst_ambiguous_and_nonexistent_times_are_flagged_not_silently_picked():
    project_id = _project('dst')
    upload = _upload(project_id, 't.csv',
                     'msg,ts\n甲,2026-11-01 01:30:00\n乙,2026-03-08 02:30:00\n'.encode())
    validated = _validate(project_id, upload.json()['id'], {
        'mapping': {'msg': 'content', 'ts': 'created_at'}, 'time_policy': 'strict',
        'timezone': 'America/New_York',
    })

    body = validated.json()
    codes = {(error['source_row'], error['code']) for error in body['validation']['errors']}
    # 秋季回拨的重复时刻与春季跳变的不存在时刻都不能由库静默选一个结果
    assert (0, 'TIMEZONE_AMBIGUOUS') in codes
    assert (1, 'TIMEZONE_NONEXISTENT') in codes
    assert body['preview']['rows'] == []


def test_invalid_time_policy_and_timezone_are_rejected():
    project_id = _project('tbad')
    dataset_id = _upload(project_id, 't.csv', b'msg\nhi\n').json()['id']

    assert _validate(project_id, dataset_id, {'mapping': {'msg': 'content'},
                                              'time_policy': 'loose'}).status_code == 422
    assert _validate(project_id, dataset_id, {'mapping': {'msg': 'content'},
                                              'timezone': 'Mars/Base'}).status_code == 422


# —— XLSX 公式 ——

def test_xlsx_formula_cell_in_content_column_is_not_imported():
    """工程计划 4.3:XLSX 只读检查公式单元格;公式字符串不能当正文。"""
    pytest.importorskip('openpyxl')
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['content', 'rating'])
    sheet.append(['=SUM(1,2)', 5])
    sheet.append(['正常反馈', 3])
    buffer = io.BytesIO()
    workbook.save(buffer)

    project_id = _project('xlsx')
    upload = _upload(project_id, 'f.xlsx', buffer.getvalue())
    assert upload.status_code == 201

    validated = _validate(project_id, upload.json()['id'],
                          {'mapping': {'content': 'content', 'rating': 'rating'}})
    body = validated.json()
    assert '=SUM' not in json.dumps(body, ensure_ascii=False)
    assert [row['content'] for row in body['preview']['rows']] == ['正常反馈']
    assert body['validation']['errors'][0]['source_row'] == 0


# —— 4.1 限额 ——

def test_upload_over_row_limit_is_rejected_without_truncation():
    """工程计划 4.1:单批 5,000 行,超限 422 建议拆批,不得静默截断。"""
    project_id = _project('rows')
    payload = ('content\n' + '\n'.join(f'反馈{i}' for i in range(5_001)) + '\n').encode()

    response = _upload(project_id, 'big.csv', payload)
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['code'] == 'row_limit_exceeded'
    assert detail['max_rows'] == 5_000 and detail['rows'] == 5_001
    # 拒绝而不是静默截断:仓储里不能出现半批数据
    listed = client.get(f'/api/v1/projects/{project_id}/datasets').json()
    assert listed['total'] == 0


def test_upload_size_limit_is_20_mib_and_checked_while_reading(monkeypatch):
    assert main.MAX_BYTES == 20 * 1024 * 1024

    # 缩小上限验证「边读边累计」的路径;真实常量已在上方钉住
    monkeypatch.setattr(main, 'MAX_BYTES', 1024)
    response = _upload(_project('size'), 'big.csv', b'content\n' + b'x' * 4096)
    assert response.status_code == 413
    assert response.json()['detail']['code'] == 'file_too_large'


# —— 单项目单活跃分析 ——

def test_second_active_analysis_returns_409_with_active_run_id():
    """工程计划 4.1:每项目仅一个活跃分析,409 必须带出活跃 run_id。"""
    project_id = _project('active')
    dataset_id = _upload(project_id, 'a.csv', b'content\nhello\n').json()['id']
    assert _validate(project_id, dataset_id, {}).status_code == 202

    first = client.post(f'/api/v1/projects/{project_id}/analyses', json={'dataset_ids': [dataset_id]})
    assert first.status_code == 202
    second = client.post(f'/api/v1/projects/{project_id}/analyses', json={'dataset_ids': [dataset_id]})
    assert second.status_code == 409
    assert second.json()['detail'] == {'code': 'active_analysis_exists', 'run_id': first.json()['id']}

    # 取消后不再算活跃,允许重开
    assert client.post(
        f"/api/v1/projects/{project_id}/analyses/{first.json()['id']}/cancel"
    ).status_code == 200
    assert client.post(f'/api/v1/projects/{project_id}/analyses',
                       json={'dataset_ids': [dataset_id]}).status_code == 202


def test_apply_mapping_is_deterministic_without_endpoint_state():
    """apply_mapping 纯函数:同样输入得到同样的标准行与计数。"""
    rows = [{'msg': 'a@example.com 物流很慢', 'ch': ''}]
    mapping = validate_mapping({'msg': 'content', 'ch': 'channel'}, ['msg', 'ch'])
    first = apply_mapping(rows, mapping, time_policy='static', timezone_name='Asia/Shanghai')
    second = apply_mapping(rows, mapping, time_policy='static', timezone_name='Asia/Shanghai')
    assert first == second
    assert first['rows'][0]['content'] == '<EMAIL_REDACTED> 物流很慢'
    assert first['rows'][0]['channel'] == 'unknown'
