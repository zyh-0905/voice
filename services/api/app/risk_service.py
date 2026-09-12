"""W08 风险扫描服务:治理后全量扫描、聚合、去重与入队。

未开始主题分析时即可查看风险——扫描独立于向量与聚类;
同 (feedback_id, rule_id) 只保留一条。

扫描结果此前只写进 run 的 `risk_findings`,而 `GET /risks` 读的是 risks 实体表
(仅由演示种子填充),于是真实扫出的风险进不了复核队列。`persist_findings` 补上这一步。
"""
from __future__ import annotations

import hashlib
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


# —— 入队:扫描候选 → 项目风险队列实体(工程计划 5.2 risk_findings) ——

def risk_entity_id(project_id: str, feedback_id: str, rule_id: str, policy_version: str) -> str:
    """按 (project, feedback_id, rule_id, policy_version) 派生稳定 id。

    计划 5.2 规定这四元组唯一。用它派生 id 而不是随机生成,是为了让重跑分析幂等——
    否则每次分析都会往复核队列里灌一批重复候选,人审队列很快就没法用了。
    """
    digest = hashlib.sha256(
        '\x1f'.join((project_id, feedback_id, rule_id, policy_version)).encode('utf-8')
    ).hexdigest()
    return f'risk_{digest[:12]}'


def findings_to_entities(project_id: str, findings: Iterable[Mapping]) -> list[dict]:
    """扫描产物 → risks 实体。缺 feedback_id / rule_id / policy_version 的条目跳过。"""
    entities: list[dict] = []
    for finding in findings:
        feedback_id = str(finding.get('feedback_id') or '')
        rule_id = str(finding.get('rule_id') or '')
        policy_version = str(finding.get('policy_version') or '')
        if not (feedback_id and rule_id and policy_version):
            continue
        entities.append({
            'id': risk_entity_id(project_id, feedback_id, rule_id, policy_version),
            'project_id': project_id,
            'feedback_id': feedback_id,
            'source_row': finding.get('source_row'),
            'rule_id': rule_id,
            'policy_version': policy_version,
            # title 用规则给出的理由(诊断文案),不写"某规则命中"这类无信息量的占位
            'title': str(finding.get('reason') or rule_id),
            'rule': f'{rule_id} · {policy_version}',
            'severity': str(finding.get('severity', 'medium')).upper(),
            'review_state': 'pending',
            'status': 'OPEN',
            'version': 1,
            'evidence_offsets': {'start': finding.get('start'), 'end': finding.get('end')},
        })
    return entities


def persist_findings(repository, project_id: str, findings: Iterable[Mapping]) -> dict:
    """把扫描候选写入项目风险队列;返回 {'created', 'refreshed', 'human_decided'} 计数。

    **人工裁决优先**:已存在的候选若已被确认或排除,只保留——不把 review_state 退回
    pending。否则每跑一次分析就会把人的判断冲掉(计划 6.4:裁决必须记录人员、理由、
    时间与版本,重新审查要留下新增复核事件)。
    """
    existing_by_id = {item.get('id'): item for item in repository.list_entities('risks', project_id)}
    created = refreshed = human_decided = 0
    for entity in findings_to_entities(project_id, findings):
        existing = existing_by_id.get(entity['id'])
        if existing is None:
            repository.create_entity('risks', entity)
            created += 1
            continue
        if str(existing.get('review_state', 'pending')).lower() != 'pending':
            human_decided += 1
            continue
        # 仍待复核:刷新策略可能已变的字段(严重度、理由、命中位置)
        repository.update_entity('risks', entity['id'], {
            'title': entity['title'], 'rule': entity['rule'], 'severity': entity['severity'],
            'evidence_offsets': entity['evidence_offsets'], 'source_row': entity['source_row'],
        })
        refreshed += 1
    return {'created': created, 'refreshed': refreshed, 'human_decided': human_decided}
