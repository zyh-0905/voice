"""W11 主题用例 fixture:本项目已发布 run + 外项目干扰数据,全部为合成合法引用。"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.main import repository
from app.publishing import EvidenceRef, TopicDraft, publish_revision

TOPIC_ID = 't1'
REVISION = 1
FEEDBACK_ID = 'fb_a'
FOREIGN_FEEDBACK_ID = 'fb_foreign'

SOURCES = {
    FEEDBACK_ID: '物流信息一直没有更新,等待了三天。',
    'fb_b': '申请退款后,希望看到预计到账时间。',
    'fb_free': '一条待归类的反馈。',
}

UNASSIGNED_FEEDBACK_ID = 'fb_free'


@pytest.fixture
def topic_case():
    # 项目与 run 均动态生成:共享 InMemory 仓储下 fixture 之间完全隔离,
    # _latest_published_run 按项目过滤,不会取到其他测试发布的 revision
    project_id = f'demo-project-{uuid4().hex[:8]}'
    other_project_id = f'other-project-{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': 'Topics Case Project'})
    repository.create_project({'id': other_project_id, 'name': 'Other Project'})
    run_id = f'run_topics_case_{uuid4().hex[:8]}'
    # 本项目 run:两主题、各一条证据,成功发布 revision
    drafts = [
        TopicDraft(
            topic_id=TOPIC_ID, name='物流体验', summary='物流更新延迟', severity='medium',
            evidence=[EvidenceRef(FEEDBACK_ID, 0, '物流信息一直没有更新', 0, 10)],
        ),
        TopicDraft(
            topic_id='t2', name='退款进度', summary='退款状态关注', severity='medium',
            evidence=[EvidenceRef('fb_b', 1, '申请退款后', 0, 5)],
        ),
    ]
    repository.create_analysis({
        'id': run_id, 'project_id': project_id, 'dataset_ids': ['ds_case'], 'status': 'queued', 'stage': 'queued', 'total': 3,
        'datasets': [{'id': 'ds_case', 'project_id': project_id, 'preview': {'rows': [
            {'feedback_id': FEEDBACK_ID, 'text': SOURCES[FEEDBACK_ID]},
            {'feedback_id': 'fb_b', 'text': SOURCES['fb_b']},
            {'feedback_id': UNASSIGNED_FEEDBACK_ID, 'text': SOURCES[UNASSIGNED_FEEDBACK_ID]},
        ]}}],
    })
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
