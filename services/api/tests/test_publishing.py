"""W11 发布原子性:引用校验失败不写任何数据;成功单写可见完整 revision。"""
import pytest

from app.main import repository
from app.publishing import EvidenceRef, PublishValidationError, TopicDraft, publish_revision

SOURCES = {'fb_1': '物流信息一直没有更新。', 'fb_2': '退款进度不透明。'}


def _draft(evidence):
    return [TopicDraft(topic_id='t', name='主题', summary='摘要', severity='medium', evidence=evidence)]


def _seed_run(run_id):
    repository.create_analysis({'id': run_id, 'project_id': 'p', 'dataset_ids': [], 'datasets': [],
                                'status': 'queued', 'stage': 'queued', 'total': 1})


def test_foreign_reference_rejected_and_nothing_written():
    _seed_run('run_atomic_1')
    with pytest.raises(PublishValidationError, match='foreign'):
        publish_revision(repository, 'run_atomic_1',
                         _draft([EvidenceRef('fb_foreign', 0, 'x', 0, 1)]), SOURCES, 0)
    run = repository.get_analysis('run_atomic_1')
    assert (run.get('result') or {}) == {}
    assert run.get('status') == 'queued'


def test_quote_mismatch_rejected():
    _seed_run('run_atomic_2')
    with pytest.raises(PublishValidationError, match='quote'):
        publish_revision(repository, 'run_atomic_2',
                         _draft([EvidenceRef('fb_1', 0, '编造的引用', 0, 5)]), SOURCES, 0)
    assert (repository.get_analysis('run_atomic_2').get('result') or {}) == {}


def test_offsets_out_of_range_rejected():
    _seed_run('run_atomic_3')
    with pytest.raises(PublishValidationError, match='range'):
        publish_revision(repository, 'run_atomic_3',
                         _draft([EvidenceRef('fb_1', 0, '物流', 99, 200)]), SOURCES, 0)
    assert (repository.get_analysis('run_atomic_3').get('result') or {}) == {}


def test_successful_publish_is_visible_and_count_consistent():
    _seed_run('run_atomic_4')
    snapshot = publish_revision(
        repository, 'run_atomic_4',
        _draft([EvidenceRef('fb_1', 0, '物流信息一直没有更新', 0, 10)]),
        SOURCES, unassigned_count=1,
    )
    assert snapshot['revision'] == 1
    assert snapshot['topics'][0]['feedback_count'] == 1
    assert len(snapshot['evidence_by_topic']['t']) == 1
    # 正文可定位源行与脱敏片段
    item = snapshot['evidence_by_topic']['t'][0]
    assert item['source_row'] == 0
    assert SOURCES['fb_1'][item['quote_start']:item['quote_end']] == item['quote']


def test_revision_increments_and_interrupted_run_shows_previous():
    _seed_run('run_atomic_5')
    publish_revision(repository, 'run_atomic_5',
                     _draft([EvidenceRef('fb_1', 0, '物流信息一直没有更新', 0, 10)]), SOURCES, 0)
    # 第二次发布中途失败:仍只能看到上一个完整 revision
    with pytest.raises(PublishValidationError):
        publish_revision(repository, 'run_atomic_5',
                         _draft([EvidenceRef('fb_2', 0, '退款进度不透明', 0, 7),
                                 EvidenceRef('fb_foreign', 0, 'x', 0, 1)]), SOURCES, 0)
    run = repository.get_analysis('run_atomic_5')
    assert run['result']['revision'] == 1
    assert [t['topic_id'] for t in run['result']['topics']] == ['t']
