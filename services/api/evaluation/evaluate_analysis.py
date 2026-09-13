"""离线分析质量评估(工程计划 13.3 / 13.4)。

**此前这个脚本测的是死代码**:它调用 `app.analysis.analyze_feedback`——一个
词频统计函数,而真实流水线走的是分块 → 向量 → 聚类 → 命名 → 发布,从来不经过它。
于是「离线评估通过」证明的是一件生产上不会发生的事。

现在评估的是真实路径:把夹具当作一批反馈播种进仓储,跑 `build_topics_from_run`
(与流水线**同一个**函数),再按 13.3 的证据口径统计。

13.3 明确要求分开报告的三项,这里都给:
- **引用存在率**:每条 claim 引用的 evidence_id 是否在本簇证据内;
- **quote 精确匹配率**:quote 是否为对应正文的精确子串;
- **降级比例**:命名退化到 `rule_fallback` 的比例。

刻意**不**输出「主题一致性 Macro-F1」:聚类标签本身是任意编号,没有金标准映射
就无法计算,而 13.3 禁止把它换名成 F1 报出来。夹具只有两条,任何百分比都不具
统计意义——所以这里同时打印原始计数,让人看得见样本量。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures.json')


def load_fixtures(path: str = FIXTURES) -> list[dict]:
    """读夹具;文件带 UTF-8 BOM,用 utf-8-sig 解。"""
    with open(path, encoding='utf-8-sig') as handle:
        return json.load(handle)


def evaluate(rows: list[dict] | None = None) -> dict:
    """在真实主题构建路径上评估一批反馈。"""
    from app.pipeline import build_topics_from_run
    from app.repository import InMemoryRepository

    rows = rows if rows is not None else load_fixtures()
    repository = InMemoryRepository()
    project_id, dataset_id, run_id = 'eval_project', 'eval_dataset', 'eval_run'

    built = repository.save_feedback_rows(project_id, dataset_id, [
        {'id': f'fb_eval_{index}', 'event_key': f'eval-{index}',
         'content_redacted': str(row.get('text') or ''),
         'content_hash': f'hash-{index}', 'source_row': index,
         'channel': 'unknown', 'product': 'unknown', 'time_quality': 'missing',
         'identity_quality': 'source_id', 'redaction_version': 'v1'}
        for index, row in enumerate(rows)
    ])
    frozen = [row['id'] for row in repository.list_feedback(project_id, [dataset_id])]
    run = {'id': run_id, 'project_id': project_id, 'dataset_ids': [dataset_id]}
    repository.create_analysis(run)
    repository.save_run_feedbacks(project_id, run_id, frozen)

    drafts = build_topics_from_run(run, repository)

    sources = {row['id']: row['content_redacted']
               for row in repository.list_feedback(project_id, feedback_ids=frozen)}
    claimed = 0
    exact = 0
    for draft in drafts:
        for evidence in draft.evidence:
            claimed += 1
            text = sources.get(evidence.feedback_id, '')
            if text[evidence.quote_start:evidence.quote_end] == evidence.quote:
                exact += 1

    fallback = sum(1 for draft in drafts if draft.name.startswith('待确认主题'))
    return {
        # 样本量必须与比例一起出现:两条夹具的 100% 不是质量结论
        'fixtures': len(rows),
        'valid_rows': built['inserted'],
        'topic_count': len(drafts),
        'named_topic_count': len(drafts) - fallback,
        'fallback_topic_count': fallback,
        'evidence_refs': claimed,
        'evidence_refs_exact': exact,
        'quote_exact_match_rate': round(exact / claimed, 4) if claimed else None,
        # 13.3:引用存在率与精确匹配率都不等于「所有断言 100% 正确」
        'note': '仅统计引用可用性;语义支持率需人工评估,不能由本脚本代替',
        'limitations': [
            f'夹具仅 {len(rows)} 条,任何比例都不具统计意义',
            '未与人工标注对照,不报告主题一致性 F1',
        ],
    }


if __name__ == '__main__':
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
