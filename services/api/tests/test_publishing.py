"""W11 发布原子性:引用校验失败不写任何数据;成功单写可见完整 revision。

5.2 之后发布落的是**实体行**而不是 run 里的 JSON 快照,所以这些用例断言的对象
也换成了表:`analysis_revisions` / `topic_evidence`。只断言 `run['result']` 为空
在新代码下会平凡通过——它本来就永远是空的,那种断言不再证明任何事情。
"""
import pytest

from app.main import repository
from app.publishing import EvidenceRef, PublishValidationError, TopicDraft, publish_revision

SOURCES = {'fb_1': '物流信息一直没有更新。', 'fb_2': '退款进度不透明。'}
PROJECT = 'p'
DATASET = 'ds_pub'


def _feedback_rows():
    """两条真实反馈行。

    topic_evidence 有指向 `feedback(project_id, id)` 的复合外键,所以「伪造一条
    证据」的前提是那条反馈真的存在——这也正是那个约束的意义。
    """
    return [
        {'id': 'fb_1', 'event_key': 'key-1', 'content_redacted': SOURCES['fb_1'],
         'content_hash': 'hash-1', 'source_row': 0, 'channel': 'unknown', 'product': 'unknown',
         'time_quality': 'missing', 'identity_quality': 'source_id', 'redaction_version': 'v1'},
        {'id': 'fb_2', 'event_key': 'key-2', 'content_redacted': SOURCES['fb_2'],
         'content_hash': 'hash-2', 'source_row': 1, 'channel': 'unknown', 'product': 'unknown',
         'time_quality': 'missing', 'identity_quality': 'source_id', 'redaction_version': 'v1'},
    ]


def _draft(evidence):
    return [TopicDraft(topic_id='t', name='主题', summary='摘要', severity='medium', evidence=evidence)]


def _seed_run(run_id):
    repository.save_feedback_rows(PROJECT, DATASET, _feedback_rows())
    repository.create_analysis({'id': run_id, 'project_id': PROJECT, 'dataset_ids': [DATASET],
                                'datasets': [], 'status': 'queued', 'stage': 'queued', 'total': 2})


def _publish(run_id, evidence, unassigned=0):
    return publish_revision(repository, run_id, _draft(evidence), SOURCES, unassigned,
                            repository=repository)


def test_foreign_reference_rejected_and_nothing_written():
    _seed_run('run_atomic_1')
    with pytest.raises(PublishValidationError, match='foreign'):
        _publish('run_atomic_1', [EvidenceRef('fb_foreign', 0, 'x', 0, 1)])
    # 失败即不落任何版本行,run 也停在原状态
    assert repository.latest_revision(PROJECT, 'run_atomic_1') is None
    assert repository.get_analysis('run_atomic_1').get('status') == 'queued'


def test_quote_mismatch_rejected():
    _seed_run('run_atomic_2')
    with pytest.raises(PublishValidationError, match='quote'):
        _publish('run_atomic_2', [EvidenceRef('fb_1', 0, '编造的引用', 0, 5)])
    assert repository.latest_revision(PROJECT, 'run_atomic_2') is None


def test_offsets_out_of_range_rejected():
    _seed_run('run_atomic_3')
    with pytest.raises(PublishValidationError, match='range'):
        _publish('run_atomic_3', [EvidenceRef('fb_1', 0, '物流', 99, 200)])
    assert repository.latest_revision(PROJECT, 'run_atomic_3') is None


def test_successful_publish_is_visible_and_count_consistent():
    _seed_run('run_atomic_4')
    snapshot = _publish('run_atomic_4',
                        [EvidenceRef('fb_1', 0, '物流信息一直没有更新', 0, 10)], unassigned=1)
    assert snapshot['revision'] == 1
    assert snapshot['topics'][0]['feedback_count'] == 1

    # 读模型从实体表现算,内容与快照一致
    from app.revisions import load_revision_snapshot
    run = repository.get_analysis('run_atomic_4')
    loaded = load_revision_snapshot(repository, run)
    assert loaded['revision'] == 1
    assert loaded['unassigned_count'] == 1
    assert [t['topic_id'] for t in loaded['topics']] == ['t']
    item = loaded['evidence_by_topic']['t'][0]
    assert item['source_row'] == 0
    # 正文可定位源行与脱敏片段
    assert SOURCES['fb_1'][item['quote_start']:item['quote_end']] == item['quote']
    # 主题版本行真的落在表里,且带版本号
    version = repository.get_topic_version(PROJECT, loaded['topics'][0]['version_id'])
    assert version['version'] == 1 and version['topic_id'] == 't'


def test_revision_increments_and_interrupted_run_shows_previous():
    _seed_run('run_atomic_5')
    _publish('run_atomic_5', [EvidenceRef('fb_1', 0, '物流信息一直没有更新', 0, 10)])
    # 第二次发布中途失败:仍只能看到上一个完整 revision
    with pytest.raises(PublishValidationError):
        _publish('run_atomic_5', [EvidenceRef('fb_2', 0, '退款进度不透明', 0, 7),
                                  EvidenceRef('fb_foreign', 0, 'x', 0, 1)])

    from app.revisions import load_revision_snapshot
    run = repository.get_analysis('run_atomic_5')
    assert repository.latest_revision(PROJECT, 'run_atomic_5') == 1
    assert load_revision_snapshot(repository, run)['revision'] == 1
    # 第二次发布的主题不该以半份状态出现
    assert [t['topic_id'] for t in load_revision_snapshot(repository, run)['topics']] == ['t']


def test_second_publish_creates_a_new_topic_version():
    """5.2:`(topic_id, version)` 唯一、不可原地更新——重发是新增版本行。"""
    _seed_run('run_atomic_6')
    _publish('run_atomic_6', [EvidenceRef('fb_1', 0, '物流信息一直没有更新', 0, 10)])
    _publish('run_atomic_6', [EvidenceRef('fb_2', 0, '退款进度不透明', 0, 7)])

    from app.revisions import load_revision_snapshot
    run = repository.get_analysis('run_atomic_6')
    latest = load_revision_snapshot(repository, run)
    assert latest['revision'] == 2
    assert latest['evidence_by_topic']['t'][0]['feedback_id'] == 'fb_2'
    # 第一版仍然可读,而且没有被第二版改写
    first = load_revision_snapshot(repository, run, revision=1)
    assert first['evidence_by_topic']['t'][0]['feedback_id'] == 'fb_1'


def test_two_runs_in_one_project_do_not_collide_on_topic_ids():
    """同一项目的两个 run 必须各自持有自己的主题行。

    `topic_id` 只在一次分析内稳定(5.2),而每个 run 都会把簇命名为 `topic-1`、
    `topic-2`……。行 id 不带 run_id 的话,第二个 run 会与第一个撞主键——它的版本行
    被**静默跳过**,表现为「这个 run 的主题是空的」,没有任何报错。demo 库上两个
    run 正是这样互相覆盖的,而当时所有测试都是绿的。
    """
    from app.revisions import load_revision_snapshot

    for run_id in ('run_iso_a', 'run_iso_b'):
        repository.save_feedback_rows(PROJECT, DATASET, _feedback_rows())
        repository.create_analysis({'id': run_id, 'project_id': PROJECT,
                                    'dataset_ids': [DATASET], 'datasets': [],
                                    'status': 'queued', 'stage': 'queued', 'total': 2})
        _publish(run_id, [EvidenceRef('fb_1', 0, '物流信息一直没有更新', 0, 10)])

    for run_id in ('run_iso_a', 'run_iso_b'):
        snapshot = load_revision_snapshot(repository, repository.get_analysis(run_id))
        assert snapshot is not None, f'{run_id} 没有可读的 revision'
        assert [t['topic_id'] for t in snapshot['topics']] == ['t'], \
            f'{run_id} 的主题被别人覆盖了'
        assert snapshot['evidence_by_topic']['t'][0]['feedback_id'] == 'fb_1'
    # 两个 run 的主题行是两条不同的行,不是同一条被反复改写
    assert repository.count_topics_for_run(PROJECT, 'run_iso_a') == 1
    assert repository.count_topics_for_run(PROJECT, 'run_iso_b') == 1
