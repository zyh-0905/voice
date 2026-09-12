"""10.3 导出:公式注入防护、只导出脱敏字段、24h 失效、删除后失效、下载重新鉴权。"""
import csv as _csv
import json
from uuid import uuid4

import pytest

from app.exports import (
    ExportError,
    build_redacted_csv,
    create_export,
    download_export,
    expired,
    invalidate_project_exports,
    sanitize_csv_cell,
)
from app.main import repository
from support.client import make_client

client = make_client()
PROJECT = 'demo-project'


# —— 纯函数:公式注入防护 ——

@pytest.mark.parametrize('payload', ['=1+1', '+1+1', '-1+1', '@SUM(A1)', '=cmd|calc'])
def test_formula_prefixes_are_neutralised(payload):
    assert sanitize_csv_cell(payload) == "'" + payload


@pytest.mark.parametrize('payload', [' =1+1', '\t=SUM(A1)', '\x00-2+3', '\n@x'])
def test_leading_noise_cannot_bypass_the_guard(payload):
    assert sanitize_csv_cell(payload).startswith("'")


def test_ordinary_text_and_numbers_untouched():
    assert sanitize_csv_cell('正常反馈') == '正常反馈'
    assert sanitize_csv_cell('a=1') == 'a=1'          # 公式字符出现在中间不算注入
    assert sanitize_csv_cell(42) == 42                 # 数值保持数值类型
    assert sanitize_csv_cell(3.5) == 3.5
    assert sanitize_csv_cell(None) is None


def test_csv_keeps_numbers_as_numbers():
    # csv 模块按 RFC 4180 输出 CRLF 行尾
    content = build_redacted_csv([{'n': 1234, 'text': '=evil'}], ['n', 'text'])
    lines = [line.rstrip('\r') for line in content.strip().split('\n')]
    assert lines[0] == 'n,text'
    assert lines[1] == "1234,'=evil"


def test_expired_handles_missing_and_bad_values():
    assert expired({}) is True
    assert expired({'expires_at': 'not-a-date'}) is True
    assert expired({'expires_at': '2000-01-01T00:00:00+00:00'}) is True


# —— 任务与端点 ——

def _export_rows(rows, columns=('dataset_id', 'row_index', 'data')):
    export_id = f'exp_test_{uuid4().hex[:8]}'
    if not repository.get_project('exp_case'):
        repository.create_project({'id': 'exp_case', 'name': '导出用例'})
    return create_export(repository, 'exp_case', 'dataset', rows, list(columns), export_id, 'demo-user')


def test_create_export_view_hides_content():
    view = _export_rows([{'dataset_id': 'ds', 'row_index': 0, 'data': '{}'}])
    assert view['state'] == 'DONE'
    assert view['row_count'] == 1
    assert view['expired'] is False
    assert 'content' not in view          # 视图不含正文
    assert view['download_path'].endswith('/download')


def test_download_requires_live_export():
    view = _export_rows([{'dataset_id': 'ds', 'row_index': 0, 'data': '{}'}])
    export = download_export(repository, 'exp_case', view['id'])
    assert 'content' in export
    # 失效后不可下载
    repository.update_entity('exports', view['id'], {'invalidated': True})
    with pytest.raises(ExportError, match='export_invalidated'):
        download_export(repository, 'exp_case', view['id'])


def test_expired_export_cannot_be_downloaded():
    view = _export_rows([{'dataset_id': 'ds', 'row_index': 0, 'data': '{}'}])
    repository.update_entity('exports', view['id'], {'expires_at': '2000-01-01T00:00:00+00:00'})
    with pytest.raises(ExportError, match='export_expired'):
        download_export(repository, 'exp_case', view['id'])


def test_invalidate_project_exports_clears_content():
    view = _export_rows([{'dataset_id': 'ds', 'row_index': 0, 'data': '{}'}])
    count = invalidate_project_exports(repository, 'exp_case')
    assert count >= 1
    stored = next(e for e in repository.list_entities('exports', 'exp_case') if e['id'] == view['id'])
    assert stored['invalidated'] is True
    assert stored['content'] is None      # 正文一并清除,不留可用副本


def test_viewer_gets_410_on_expired_download():
    view = _export_rows([{'dataset_id': 'ds', 'row_index': 0, 'data': '{}'}])
    repository.update_entity('exports', view['id'], {'expires_at': '2000-01-01T00:00:00+00:00'})
    response = client.get(f'/api/v1/projects/exp_case/exports/{view["id"]}/download')
    assert response.status_code == 410
    assert response.json()['detail']['code'] == 'export_expired'


def test_unknown_export_404():
    repository.create_project({'id': 'exp_case2', 'name': '导出用例2'})
    assert client.get('/api/v1/projects/exp_case2/exports/exp_ghost/download').status_code == 404


def test_folder_endpoint_creates_and_downloads_redacted_csv():
    repository.create_project({'id': 'exp_demo', 'name': '导出端点'})
    repository.create_dataset({
        'id': 'ds_exp', 'project_id': 'exp_demo', 'name': '批次', 'rows': 1,
        'preview': {'rows': [{'email': 'person@example.com', 'note': '=1+1'}]},
    })
    created = client.post('/api/v1/projects/exp_demo/exports', json={'scope': 'project'})
    assert created.status_code == 202
    body = created.json()
    assert body['row_count'] == 1

    download = client.get(body['download_path'])
    assert download.status_code == 200
    assert download.headers['content-type'].startswith('text/csv')
    text = download.text
    # 只导出脱敏字段,原始邮箱不得出现
    assert 'person@example.com' not in text
    assert '<EMAIL_REDACTED>' in text
    # 逐格检查:任何单元格都不得以公式字符开头(电子表格会执行)
    parsed = list(_csv.reader(text.splitlines()))
    for row in parsed:
        for cell in row:
            assert not cell.lstrip(' \t\r\n\x00\x0b\x0c')[:1] in ('=', '+', '-', '@'), cell
    # data 列是 JSON 文本(不泄露任意来源列名);解析后核对脱敏与原文保留
    header, first = parsed[0], parsed[1]
    payload = json.loads(first[header.index('data')])
    assert payload['email'] == '<EMAIL_REDACTED>'
    assert payload['note'] == '=1+1'


def test_deletion_invalidates_unexpired_exports():
    repository.create_project({'id': 'exp_del', 'name': '删除联动'})
    repository.create_dataset({'id': 'ds_del', 'project_id': 'exp_del', 'name': '批次', 'rows': 1,
                               'preview': {'rows': [{'note': 'x'}]}})
    created = client.post('/api/v1/projects/exp_del/exports', json={'scope': 'project'}).json()
    assert client.get(created['download_path']).status_code == 200

    client.post('/api/v1/projects/exp_del/deletions', json={
        'target_type': 'project', 'target_id': 'exp_del', 'confirm_name': '删除联动',
    })
    # 项目已删,导出链接不再可用
    assert client.get(created['download_path']).status_code in (404, 410)
