"""W08 风险扫描服务:治理后全量扫描、聚合与去重。

未开始主题分析时即可查看风险——扫描独立于向量与聚类;
同 (feedback_id, rule_id) 只保留一条,写入由发布事务(W11)负责。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .risk_rules import RiskCandidate, RiskPolicy, scan_risks

FEEDBACK_ID_KEYS = ('feedback_id', 'id')


@dataclass(frozen=True)
class RiskRecord:
    feedback_id: str
    candidate: RiskCandidate


def _feedback_id_of(row: Mapping, row_index: int) -> str:
    for key in FEEDBACK_ID_KEYS:
        value = row.get(key)
        if value is not None:
            return str(value)
    return f'row-{row_index}'


def scan_rows(rows: Iterable[Mapping], policy: RiskPolicy) -> list[RiskRecord]:
    """逐行全量扫描;行序稳定,同 (feedback_id, rule_id) 去重保首个。"""
    records: list[RiskRecord] = []
    seen: set[tuple[str, str]] = set()
    for row_index, row in enumerate(rows):
        text = ' '.join(str(value) for value in row.values() if value is not None)
        feedback_id = _feedback_id_of(row, row_index)
        for candidate in scan_risks(feedback_id, text, policy):
            key = (feedback_id, candidate.rule_id)
            if key in seen:
                continue
            seen.add(key)
            records.append(RiskRecord(feedback_id=feedback_id, candidate=candidate))
    return records


def dedupe(records: Iterable[RiskRecord]) -> list[RiskRecord]:
    """幂等去重,保持输入顺序。"""
    result: list[RiskRecord] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record.feedback_id, record.candidate.rule_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result
