"""工程计划 4.3:XLSX 工作表选择。

此前只读 `worksheets[0]` 且不返回工作表名,于是「选择工作表」这一步不存在;而
`sheet_name` 从不落库,导致 §4.4 无来源编号的事件键退化成 `file_sha256 + source_row`
——**同一工作簿的两张表按行号互相碰撞**,第二张表的第 3 行会被判成第一张表第 3 行的
重复。这是静默的:健康报告只会说「重复 1 条」,而那条数据根本没进分析。
"""
import io

import pytest

from app.ingestion import build_feedback_rows, parse_xlsx_bytes, parse_xlsx_sheets
from app.main import repository
from support.client import make_client

client = make_client()
pytest.importorskip('openpyxl')


def _workbook(sheets: dict[str, list[list]]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    for index, (name, rows) in enumerate(sheets.items()):
        ws = wb.active if index == 0 else wb.create_sheet()
        ws.title = name
        for row in rows:
            ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _project(prefix='xl'):
    from uuid import uuid4
    project_id = f'{prefix}_{uuid4().hex[:8]}'
    created = client.post('/api/v1/projects',
                          json={'name': f'测试项目 {project_id}', 'timezone': 'Asia/Shanghai'})
    assert created.status_code == 201, created.text
    return created.json()['id']


# —— 解析:命名工作表 + 列出全部 ——

def test_parser_lists_every_worksheet():
    data = _workbook({'一月': [['content'], ['物流很慢']],
                      '二月': [['content'], ['退款没到账']]})

    parsed = parse_xlsx_bytes(data)

    assert parsed['sheet_names'] == ['一月', '二月']
    assert parsed['sheet_name'] == '一月'
    assert [row['content'] for row in parsed['rows']] == ['物流很慢']


def test_parser_reads_the_named_worksheet():
    data = _workbook({'一月': [['content'], ['物流很慢']],
                      '二月': [['content'], ['退款没到账']]})

    parsed = parse_xlsx_bytes(data, sheet_name='二月')

    assert parsed['sheet_name'] == '二月'
    assert [row['content'] for row in parsed['rows']] == ['退款没到账']


def test_unknown_worksheet_errors_instead_of_falling_back():
    """工作表明写错时**报错**,不悄悄退回第一张。

    静默退回会让用户以为分析的是他选的那张——而结果看起来完全正常。
    """
    data = _workbook({'一月': [['content'], ['物流很慢']]})

    with pytest.raises(ValueError, match='worksheet not found'):
        parse_xlsx_bytes(data, sheet_name='三月')


def test_parse_all_sheets_keeps_rows_per_sheet():
    data = _workbook({'A': [['content'], ['甲']], 'B': [['content'], ['乙']]})

    sheets = parse_xlsx_sheets(data)

    assert sorted(sheets) == ['A', 'B']
    assert [row['content'] for row in sheets['A']['rows']] == ['甲']
    assert [row['content'] for row in sheets['B']['rows']] == ['乙']


# —— 导入流程:选择真的生效,且进入事件键 ——

def test_upload_reports_available_worksheets():
    project_id = _project('list')
    data = _workbook({'一月': [['content'], ['物流很慢']],
                      '二月': [['content'], ['退款没到账']]})
    upload = client.post(f'/api/v1/projects/{project_id}/datasets',
                         files={'file': ('m.xlsx', data)}, data={'consent': 'true'})

    assert upload.status_code == 201, upload.text
    assert upload.json()['preview']['sheet_names'] == ['一月', '二月']
    # 工作表**内容**不出站:它留在 source 暂存里
    assert 'sheets' not in upload.json()


def test_validate_honours_the_chosen_worksheet():
    project_id = _project('choose')
    data = _workbook({'一月': [['content'], ['物流很慢']],
                      '二月': [['content'], ['退款没到账']]})
    dataset_id = client.post(f'/api/v1/projects/{project_id}/datasets',
                             files={'file': ('m.xlsx', data)},
                             data={'consent': 'true'}).json()['id']

    body = client.post(f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate',
                       json={'mapping': {'content': 'content'}, 'sheet_name': '二月'}).json()

    assert body['preview']['sheet_name'] == '二月'
    assert [row['content'] for row in body['preview']['rows']] == ['退款没到账']
    assert [row['content_redacted']
            for row in repository.list_feedback(project_id, [dataset_id])] == ['退款没到账']


def test_unknown_worksheet_is_rejected_at_validate():
    project_id = _project('bad')
    data = _workbook({'一月': [['content'], ['物流很慢']]})
    dataset_id = client.post(f'/api/v1/projects/{project_id}/datasets',
                             files={'file': ('m.xlsx', data)},
                             data={'consent': 'true'}).json()['id']

    response = client.post(f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate',
                           json={'mapping': {'content': 'content'}, 'sheet_name': '三月'})

    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'worksheet_not_found'


def test_two_worksheets_in_one_workbook_do_not_collide():
    """同一工作簿的两张表按行号会碰撞——这正是 sheet_name 要进事件键的原因。

    碰撞是静默的:健康报告只说「重复」,而那条数据根本没进分析。
    """
    project_id = _project('collide')
    data = _workbook({'一月': [['content'], ['第一张表的内容']],
                      '二月': [['content'], ['第二张表的内容']]})

    first_id = client.post(f'/api/v1/projects/{project_id}/datasets',
                           files={'file': ('m.xlsx', data)},
                           data={'consent': 'true'}).json()['id']
    first = client.post(f'/api/v1/projects/{project_id}/datasets/{first_id}/validate',
                        json={'mapping': {'content': 'content'}, 'sheet_name': '一月'}).json()
    assert first['preview']['stats']['valid'] == 1

    # 第二份上传:不同文件名 → 不同数据集级来源键,所以能建出来
    second_id = client.post(f'/api/v1/projects/{project_id}/datasets',
                            files={'file': ('m2.xlsx', data)},
                            data={'consent': 'true'}).json()['id']
    second = client.post(f'/api/v1/projects/{project_id}/datasets/{second_id}/validate',
                         json={'mapping': {'content': 'content'}, 'sheet_name': '二月'}).json()

    assert second['preview']['stats']['duplicate'] == 0, '两张表不是同一条事件'
    assert second['preview']['stats']['valid'] == 1
    stored = repository.list_feedback(project_id, [second_id])
    assert [row['content_redacted'] for row in stored] == ['第二张表的内容']


def test_sheet_name_enters_the_event_key():
    """直接钉住口径:同名行号、不同工作表 → 不同 event_key。"""
    rows = [{'content': '同一行号'}]
    january = build_feedback_rows(
        {'id': 'ds', 'content_hash': 'same-file', 'sheet_name': '一月',
         'preview': {'rows': rows}}, secret='s')
    february = build_feedback_rows(
        {'id': 'ds', 'content_hash': 'same-file', 'sheet_name': '二月',
         'preview': {'rows': rows}}, secret='s')

    assert january[0]['event_key'] != february[0]['event_key']
