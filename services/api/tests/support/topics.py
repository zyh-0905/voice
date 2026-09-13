"""W11 主题用例 fixture:本项目已发布 run + 外项目干扰数据,全部为合成合法引用。"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.main import repository
from app.publishing import EvidenceRef, TopicDraft, publish_revision
from support.feedback import seed_run_feedback

TOPIC_ID = 't1'
REVISION = 1
# 计划 5.2 之后 feedback 行的 id 由 `build_feedback_rows` 按 `fb_{dataset}_{序号}`
# 派生,不再是调用方给的编号;证据与校正都引用这个真实 id
DATASET_ID = 'ds_case'
FEEDBACK_ID = f'fb_{DATASET_ID}_0'
SECOND_FEEDBACK_ID = f'fb_{DATASET_ID}_1'
UNASSIGNED_FEEDBACK_ID = f'fb_{DATASET_ID}_2'
FOREIGN_FEEDBACK_ID = 'fb_foreign'

SOURCES = {
    FEEDBACK_ID: '物流信息一直没有更新,等待了三天。',
    SECOND_FEEDBACK_ID: '申请退款后,希望看到预计到账时间。',
    UNASSIGNED_FEEDBACK_ID: '一条待归类的反馈。',
}


@pytest.fixture
def topic_case():
    # 项目与 run 均动态生成:共享 InMemory 仓储下 fixture 之间完全隔离,
    # _latest_published_run 按项目过滤,不会取到其他测试发布的 revision
    project_id = f'demo-project-{uuid4().hex[:8]}'
    other_project_id = f'other-project-{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': 'Topics Case Project'})
    repository.create_project({'id': other_project_id, 'name': 'Other Project'})
    run_id = f'run_topics_case_{uuid4().hex[:8]}'
    # 本项目 run:两主题、各一条证据,成功发布 revision。
    # 反馈正文来自 `feedback` 实体表,所以先把行播种进去再建 run——只在 run 里
    # 摆行的话,校正与证据会走一条生产上不存在的取数路径。
    run = {
        'id': run_id, 'project_id': project_id, 'dataset_ids': [DATASET_ID],
        'status': 'queued', 'stage': 'queued', 'total': 3,
        'datasets': [{'id': DATASET_ID, 'project_id': project_id, 'preview': {'rows': [
            {'content': SOURCES[FEEDBACK_ID]},
            {'content': SOURCES[SECOND_FEEDBACK_ID]},
            {'content': SOURCES[UNASSIGNED_FEEDBACK_ID]},
        ]}}],
    }
    seed_run_feedback(repository, run)
    repository.create_analysis(run)
    drafts = [
        TopicDraft(
            topic_id=TOPIC_ID, name='物流体验', summary='物流更新延迟', severity='medium',
            evidence=[EvidenceRef(FEEDBACK_ID, 0, '物流信息一直没有更新', 0, 10)],
        ),
        TopicDraft(
            topic_id='t2', name='退款进度', summary='退款状态关注', severity='medium',
            evidence=[EvidenceRef(SECOND_FEEDBACK_ID, 1, '申请退款后', 0, 5)],
        ),
    ]
    publish_revision(repository, run_id, drafts, SOURCES, unassigned_count=1)

    # 外项目干扰:同名 topic 带外项目证据,任何查询都不应泄漏
    repository.create_analysis({
        'id': f'run_foreign_{uuid4().hex[:8]}', 'project_id': other_project_id, 'dataset_ids': [], 'datasets': [],
        'status': 'done', 'stage': 'completed', 'total': 1,
        'result': {
            'revision': 1,
            'topics': [{'topic_id': TOPIC_ID, 'name': '外项目主题', 'summary': '', 'severity': 'medium', 'feedback_count': 1}],
            'evidence_by_topic': {TOPIC_ID: [{'feedback_id': FOREIGN_FEEDBACK_ID, 'source_row': 0,
                                               'quote': '外项目原文', 'quote_start': 0, 'quote_end': 5}]},
            'unassigned_count': 0,
        },
    })

    return SimpleNamespace(
        project_id=project_id,
        other_project_id=other_project_id,
        run_id=run_id,
        topic_id=TOPIC_ID,
        topic_version_id=REVISION,
        feedback_id=FEEDBACK_ID,
        foreign_feedback_id=FOREIGN_FEEDBACK_ID,
        unassigned_feedback_id=UNASSIGNED_FEEDBACK_ID,
    )
