"""证据源查询(工程计划 7.5 GET /projects/{p}/feedback/{f})。

返回脱敏全文、源行号、来源、时间与分块;**不返回原始文件**,
且只在本项目的数据集内查找——外项目反馈一律 404,不暴露存在性。
"""
from __future__ import annotations

from typing import Mapping

from .ingestion import redact_text
from .segments import split_redacted

_SEGMENT_MAX_TOKENS = 120
_SEGMENT_OVERLAP = 12


class FeedbackNotFound(ValueError):
    """反馈不在本项目内(或不存在)。"""


def _redact(value: object) -> str:
    return redact_text(str(value))['text']


def find_feedback(repository, project_id: str, feedback_id: str) -> dict:
    """在项目的 feedback 实体表中定位反馈;找不到即抛 FeedbackNotFound。

    取数走 `feedback` 表(工程计划 5.2)而不是遍历数据集预览行。预览现在是
    4.3 要求的**最多 20 行样例**,拿它当索引会有一条更难发现的失效路径:
    第 21 条之后的反馈查不到,而前 20 条一切正常。
    """
    row = repository.get_feedback(project_id, feedback_id)
    if row is None:
        raise FeedbackNotFound(feedback_id)
    # 读取侧兜底:数据访问层不假设上游都合规(与导出端点同一做法)。
    # 对已经脱敏的正文是幂等的——替换标记本身不匹配任何 PII 模式——
    # 所以 offset 仍然落在同一条正文上。
    text = _redact(row.get('content_redacted') or '')
    dataset = repository.datasets.get(row.get('dataset_id')) or {}
    segments = repository.list_segments(project_id, feedback_id)
    if segments:
        spans = [{'start': item['start_offset'], 'end': item['end_offset'],
                  'text': text[item['start_offset']:item['end_offset']]} for item in segments]
    else:
        # 还没跑过分析,分块尚未落库。用与流水线**同一个**分块函数现算:
        # 同一份正文在任何地方都应得到同一组分块。
        spans = [{'start': span.start, 'end': span.end, 'text': span.text}
                 for span in split_redacted(text, max_tokens=_SEGMENT_MAX_TOKENS,
                                            overlap=_SEGMENT_OVERLAP)]
    return {
        'feedback_id': feedback_id,
        'dataset_id': row.get('dataset_id'),
        'dataset_name': dataset.get('name'),
        'source_row': int(row.get('source_row') or 0),
        'channel': row.get('channel'),
        'occurred_at': row.get('occurred_at'),
        # 只给脱敏全文;不提供原始文件或未脱敏内容
        'text': text,
        'segments': spans,
    }
