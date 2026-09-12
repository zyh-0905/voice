"""证据源查询(工程计划 7.5 GET /projects/{p}/feedback/{f})。

返回脱敏全文、源行号、来源、时间与分块;**不返回原始文件**,
且只在本项目的数据集内查找——外项目反馈一律 404,不暴露存在性。
"""
from __future__ import annotations

from typing import Mapping

from .ingestion import redact_text, row_text
from .segments import split_redacted

# 行内可识别为反馈标识/时间/渠道的字段名(治理后的脱敏行)
_ID_KEYS = ('feedback_id', 'id')
_TIME_KEYS = ('occurred_at', 'occurredAt', 'time', 'date', 'created_at', 'event_time')
_CHANNEL_KEYS = ('channel', 'source_channel', '来源渠道')
_SEGMENT_MAX_TOKENS = 120
_SEGMENT_OVERLAP = 12


class FeedbackNotFound(ValueError):
    """反馈不在本项目内(或不存在)。"""


def _first(row: Mapping, keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ''):
            return value
    return None


def _redact(value: object) -> str:
    return redact_text(str(value))['text']


def _row_text(row: Mapping) -> str:
    """拼出脱敏正文——与流水线共用 `ingestion.row_text`,保证两处口径一致。

    仓储里存的是解析后的**原始行**(`parse_csv_text` 只对 stats 走脱敏),所以那里
    会逐值再脱敏一次(纵深防御);标识字段不并入正文。
    """
    return row_text(row)


def find_feedback(repository, project_id: str, feedback_id: str) -> dict:
    """在项目的数据集预览行中定位反馈;找不到即抛 FeedbackNotFound。"""
    for dataset in repository.datasets.values():
        if dataset.get('project_id') != project_id:
            continue
        rows = (dataset.get('preview') or {}).get('rows') or []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            row_id = _first(row, _ID_KEYS)
            generated_id = f"fb_{dataset.get('id', 'ds')}_{index}"
            if str(row_id) != feedback_id and generated_id != feedback_id:
                continue
            text = _row_text(row)
            spans = split_redacted(text, max_tokens=_SEGMENT_MAX_TOKENS, overlap=_SEGMENT_OVERLAP)
            channel = _first(row, _CHANNEL_KEYS)
            return {
                'feedback_id': feedback_id,
                'dataset_id': dataset.get('id'),
                'dataset_name': dataset.get('name'),
                'source_row': index,
                'channel': None if channel is None else _redact(channel),
                'occurred_at': _first(row, _TIME_KEYS),
                # 只给脱敏全文;不提供原始文件或未脱敏内容
                'text': text,
                'segments': [
                    {'start': span.start, 'end': span.end, 'text': span.text} for span in spans
                ],
            }
    raise FeedbackNotFound(feedback_id)
