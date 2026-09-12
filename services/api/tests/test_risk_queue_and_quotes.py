"""风险候选入队(计划 5.2 risk_findings / 8.1)与证据引文(计划 8.5 / 9.5)。

两条链路的共同毛病是「看起来有、实际不连通」:
- 扫描产物只写进 run 的 risk_findings,而复核队列读的是 risks 实体表,真实风险进不了队列;
- 证据引文是 text[:24] 的固定前缀,与它要支撑的结论无关,却照样能通过发布校验。
"""
from uuid import uuid4

from app import pipeline
from app.evidence_validation import Claim, TopicCandidate
from app.main import repository
from app.risk_service import risk_entity_id
from support.client import make_client

client = make_client()


class _Store:
    """最小 AnalysisStore:流水线只用到 get/update。"""

    def __init__(self, run):
        self.run = run

    def get_analysis(self, analysis_id):
        return self.run

    def update_analysis(self, analysis_id, changes):
        self.run.update(changes)
        return self.run


def _project_id() -> str:
    project_id = f'riskq_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': '风险入队用例'})
    return project_id


def _run(project_id: str, rows: list[dict]) -> dict:
    return {
        'id': f'run_{uuid4().hex[:8]}', 'project_id': project_id, 'dataset_ids': ['ds_x'],
        'status': 'queued', 'stage': 'queued', 'total': len(rows),
        'datasets': [{'id': 'ds_x', 'project_id': project_id, 'preview': {'rows': rows}}],
    }


def _queued(project_id: str) -> dict[str, dict]:
    return {item['rule_id']: item for item in repository.list_entities('risks', project_id)}


# —— 风险候选入队 ——

def test_scan_findings_enter_the_risk_queue():
    project_id = _project_id()
    run = _run(project_id, [
        {'feedback_id': 'fb_a', 'text': '订单被重复扣款了两次,请核查。'},
        {'feedback_id': 'fb_b', 'text': '充电时冒烟起火,非常危险。'},
        {'feedback_id': 'fb_c', 'text': '希望能增加配送方式。'},
    ])

    pipeline.run_analysis_pipeline(_Store(run), run['id'], repository)

    queued = _queued(project_id)
    assert 'duplicate_charge' in queued, '真实扫出的候选必须进复核队列'
    assert 'safety_fire' in queued
    assert queued['duplicate_charge']['severity'] == 'HIGH'
    assert queued['safety_fire']['severity'] == 'CRITICAL'
    # 单条严重投诉即使不成簇也要入队(计划 8.1),这里它确实没进任何主题
    assert queued['safety_fire']['feedback_id'] == 'fb_b'
    # 候选不是既成事实:入队恒为待复核
    assert {item['review_state'] for item in queued.values()} == {'pending'}
    assert 'fb_c' not in {item.get('feedback_id') for item in queued.values()}


def test_rescan_is_idempotent():
    """重跑分析不得往队列里灌重复候选——id 由唯一键派生,故同一候选稳定。"""
    project_id = _project_id()
    rows = [{'feedback_id': 'fb_a', 'text': '订单被重复扣款了两次,请核查。'}]

    for _ in range(2):
        run = _run(project_id, rows)
        pipeline.run_analysis_pipeline(_Store(run), run['id'], repository)

    assert len(repository.list_entities('risks', project_id)) == 1


def test_rescan_does_not_overwrite_human_decision():
    """人工裁决优先:重跑扫描不能把已确认/已排除的候选退回待复核(计划 6.4)。"""
    project_id = _project_id()
    rows = [{'feedback_id': 'fb_b', 'text': '充电时冒烟起火,非常危险。'}]

    run = _run(project_id, rows)
    pipeline.run_analysis_pipeline(_Store(run), run['id'], repository)
    risk_id = risk_entity_id(project_id, 'fb_b', 'safety_fire', 'ecommerce-v1')
    repository.update_entity('risks', risk_id, {
        'review_state': 'confirmed', 'reviewed_by': 'u_analyst', 'review_reason': '已核实为个例',
    })

    run2 = _run(project_id, rows)
    pipeline.run_analysis_pipeline(_Store(run2), run2['id'], repository)

    kept = next(item for item in repository.list_entities('risks', project_id) if item['id'] == risk_id)
    assert kept['review_state'] == 'confirmed', '重跑扫描把人工裁决冲掉了'
    assert kept['reviewed_by'] == 'u_analyst'


def test_persist_findings_is_skipped_without_repository():
    """不传仓储时只算不写:纯计算场景不应产生副作用。"""
    project_id = _project_id()
    run = _run(project_id, [{'feedback_id': 'fb_b', 'text': '充电时冒烟起火。'}])
    pipeline.run_analysis_pipeline(_Store(run), run['id'])
    assert repository.list_entities('risks', project_id) == []
    assert run['risk_findings'], '扫描产物本身仍要写进 run'


# —— 证据引文 ——

def test_evidence_quote_uses_the_claim_not_a_text_prefix(monkeypatch):
    """命名阶段说「这条结论引用的是这句」,证据就必须是那一句。

    旧实现给的是 text[:24],它照样是正文的精确子串、照样能通过发布校验,
    却与结论无关——这条用例就是钉住这一点。
    """
    base = '物流信息一直没有更新。第二句才是结论真正引用的那一句。第三句收尾。'
    quote = '第二句才是结论真正引用的那一句。'

    # 不要假设哪条反馈会成为代表——由 stub 记下它实际引用了谁
    cited: dict[str, str] = {}

    class _StubNamer:
        def __init__(self, *args, **kwargs):
            pass

        def name_topic(self, evidence, context=None):
            ids = [row['evidence_id'] for row in evidence]
            # 只对"近似文本"那一簇给出引用,另一簇不给——这样 cited 一定落在前者
            target = next((row['evidence_id'] for row in evidence if row['text'].startswith(base)), None)
            if target is None:
                return TopicCandidate(topic_name='另一主题', summary='摘要', severity='medium',
                                      evidence_ids=ids, claims=[])
            cited['id'] = target
            return TopicCandidate(
                topic_name='物流体验', summary='摘要', severity='medium',
                evidence_ids=ids,
                claims=[Claim(evidence_id=target, quote=quote, claim='结论')],
            )

    monkeypatch.setattr(pipeline, 'TopicNamer', _StubNamer)
    project_id = _project_id()
    # 数据形状经过实测:6 条近似文本 + 3 条无关文本 → 两个干净的簇。
    # 文本完全相同或只有 2-4 条时,sklearn 的 HDBSCAN 会把它们判为噪声(互达距离
    # 退化),那是算法性质,不是本用例要测的东西。
    rows = [{'feedback_id': f'fb_{i}', 'text': base + f'补充说明{i}'} for i in range(1, 7)]
    rows += [{'feedback_id': f'fb_other_{i}', 'text': '完全不同的另一批反馈内容,关于退款到账时间的问题。'}
             for i in range(1, 4)]
    text_of = {row['feedback_id']: row['text'] for row in rows}
    run = _run(project_id, rows)

    drafts = pipeline.build_topics_from_run(run)
    assert drafts, '近似文本应聚成一簇'
    refs = {ref.feedback_id: ref for draft in drafts for ref in draft.evidence}
    assert refs, '主题应带证据'

    ref = refs[cited['id']]
    assert ref.quote == quote, '被引用的那条必须是 claim 里的那一句'
    assert text_of[ref.feedback_id][ref.quote_start:ref.quote_end] == quote
    assert ref.quote != text_of[ref.feedback_id][:24], '引文退回成了正文前缀'
    # 同簇其余反馈没有 claim,退化为可定位片段
    others = [r for fid, r in refs.items() if fid != cited['id']]
    assert others
    for other in others:
        assert text_of[other.feedback_id][other.quote_start:other.quote_end] == other.quote


def test_evidence_quote_falls_back_to_a_locatable_segment():
    """没有 claim 时取分块器给出的首个片段:有界、句段对齐、可在正文里定位。

    `split_redacted` 是按预算打包句段的,所以短文本整段就是一块——那正是最合适的引文。
    """
    short = '第一句。第二句。'
    quote, start, end = pipeline._resolve_quote(short, None)
    assert short[start:end] == quote
    assert quote == short

    long_text = '第一句足够长用来占位测试。' * 20
    quote, start, end = pipeline._resolve_quote(long_text, None)
    assert long_text[start:end] == quote
    assert 0 < len(quote) <= 80, '引文必须有界'
    assert quote.endswith('。'), '引文应对齐句末,而不是拦腰截断'


def test_evidence_quote_survives_text_without_punctuation():
    """整段没有句读且超预算时退化为有界切片,offset 仍必须自洽。"""
    text = '很长的连续文本' * 40
    quote, start, end = pipeline._resolve_quote(text, None)

    assert text[start:end] == quote
    assert 0 < len(quote) <= 80
