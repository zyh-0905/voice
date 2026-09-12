"""工程计划 10.3 导出:CSV 安全处理、短时效、下载重新鉴权。

约束:
- 只导出脱敏字段;导出正文绝不含原始敏感值
- 以 = + - @ 开头的文本(含前置空白/控制字符)按公式注入处理,数值列保持数值
- 导出文件 24 小时失效,下载每次重新鉴权,不提供永久公开链接
- 删除项目/数据集后,未过期的导出也必须失效
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping

EXPORT_TTL_HOURS = 24
# 电子表格会把以这些字符开头的单元格当公式执行
_FORMULA_PREFIXES = ('=', '+', '-', '@')
# 前置空白与控制字符不能成为绕过手段
_LEADING_NOISE = ' \t\r\n\x00\x0b\x0c'


class ExportError(ValueError):
    """导出请求不合法。"""


def expired(export: Mapping) -> bool:
    expires_at = str(export.get('expires_at') or '')
    if not expires_at:
        return True
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= deadline


def sanitize_csv_cell(value: object) -> object:
    """文本单元格做公式注入防护;数值与非文本原样返回。

    处理方式:在前导噪声之后仍以 = + - @ 开头的文本,前置一个单引号,
    使电子表格按文本解释;数值列不受影响,保持数值类型。
    """
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(_LEADING_NOISE)
    if stripped[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def build_redacted_csv(rows: Iterable[Mapping[str, object]], columns: list[str]) -> str:
    """生成 CSV 文本:列固定、只输出给定列(调用方保证列已是脱敏字段)。"""
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({column: sanitize_csv_cell(row.get(column)) for column in columns})
    return buffer.getvalue()


def create_export(repository, project_id: str, scope: str, rows: Iterable[Mapping[str, object]],
                  columns: list[str], export_id: str, actor: str) -> dict:
    """创建导出任务并立即产出内容(演示实现);返回任务视图。"""
    content = build_redacted_csv(rows, columns)
    now = datetime.now(timezone.utc)
    export = {
        'id': export_id, 'project_id': project_id, 'scope': scope, 'state': 'DONE',
        'columns': columns, 'row_count': max(0, content.count('\n') - 1),
        'content': content, 'actor': actor,
        'created_at': now.isoformat(),
        'expires_at': (now + timedelta(hours=EXPORT_TTL_HOURS)).isoformat(),
        'invalidated': False,
    }
    repository.create_entity('exports', export)
    return view(export)


def view(export: Mapping) -> dict:
    """任务视图:不含正文,只给状态与时效;正文只能经下载端点获取。"""
    return {
        'id': export.get('id'),
        'project_id': export.get('project_id'),
        'scope': export.get('scope'),
        'state': export.get('state'),
        'row_count': export.get('row_count'),
        'created_at': export.get('created_at'),
        'expires_at': export.get('expires_at'),
        'expired': expired(export),
        'invalidated': bool(export.get('invalidated')),
        'download_path': f"/api/v1/projects/{export.get('project_id')}/exports/{export.get('id')}/download",
    }


def get_export(repository, project_id: str, export_id: str) -> dict | None:
    for export in repository.list_entities('exports', project_id):
        if export.get('id') == export_id:
            return export
    return None


def download_export(repository, project_id: str, export_id: str) -> dict:
    """下载:每次重新鉴权(由路由依赖保证),并校验时效与失效标记。"""
    export = get_export(repository, project_id, export_id)
    if export is None:
        raise ExportError('export_not_found')
    if export.get('invalidated'):
        raise ExportError('export_invalidated')
    if expired(export):
        raise ExportError('export_expired')
    return export


def invalidate_project_exports(repository, project_id: str) -> int:
    """删除项目/数据集时调用:未过期的导出一并失效,不留可用链接。"""
    invalidated = 0
    for export in repository.list_entities('exports', project_id):
        if export.get('invalidated'):
            continue
        try:
            repository.update_entity('exports', export['id'], {'invalidated': True, 'content': None})
            invalidated += 1
        except (KeyError, AttributeError):
            continue
    return invalidated
