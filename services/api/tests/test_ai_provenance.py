"""aiProvenance 的真实来源链(8.5/UI-09)。

此前整条链是断的:命名候选带着 origin/needs_review,但 TopicDraft 不收、
快照不带、topic_versions 的列恒 NULL/默认、读模型丢字段、接口硬编码
origin='rule'/needsReview=True——前端徽标显示的东西与真实命名来源无关。
这里的用例钉住从命名到接口的完整透传。
"""
from app.main import _ai_origin_label, repository, worker
from app.versioning import apply_correction
from support.client import make_client

client = make_client()


def _project(name='来源链项目'):
    from uuid import uuid4
    project_id = f'ai_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': name})
    return project_id


def _run_analysis(project_id) -> str:
    """上传→治理→建 run→同步执行(与 celery 任务同一条 pipeline);返回 run id。"""
    upload = client.post(
        f'/api/v1/projects/{project_id}/datasets',
        files={'file': ('ai.csv', 'msg,fid\n退款到账偏慢,ext-1\n退款到账偏慢,ext-2\n'
                        '退款到账偏慢,ext-3\n物流信息不更新,ext-4\n物流信息不更新,ext-5\n'
                        '物流信息不更新,ext-6\n'.encode())},
        data={'consent': 'true'},
    )
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()['id']
    validated = client.post(
        f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate',
        json={'mapping': {'msg': 'content', 'fid': 'feedback_id'}},
    )
    assert validated.status_code == 202, validated.text
    created = client.post(f'/api/v1/projects/{project_id}/analyses',
                          json={'dataset_ids': [dataset_id], 'config': {}})
    assert created.status_code == 202, created.text
    run_id = created.json()['id']
    finished = worker.run(run_id)
    assert finished.get('status') == 'done', finished
    return run_id


def test_origin_label_maps_raw_values_to_the_contract():
    """库存原始值,接口说展示词汇;mock 不冒充 ai/rule(演示路径另有 DemoNotice)。"""
    assert _ai_origin_label('http') == 'ai'
    assert _ai_origin_label('my-custom-gateway') == 'ai'
    assert _ai_origin_label('rule_fallback') == 'rule'
    assert _ai_origin_label('human') == 'human'
    assert _ai_origin_label('mock') == 'unknown'
    assert _ai_origin_label(None) == 'unknown'
    assert _ai_origin_label('') == 'unknown'


def test_topics_report_the_real_naming_provenance():
    """mock 命名 → origin 映射 'unknown'、needsReview 用命名器自报值,不再硬编码。"""
    project_id = _project()
    _run_analysis(project_id)

    rows = client.get(f'/api/v1/projects/{project_id}/topics').json()['items']
    assert rows, '分析已发布,主题列表不应为空'
    for row in rows:
        provenance = row['evidence']['aiProvenance']
        assert provenance['origin'] == 'unknown', provenance  # mock 命名
        assert provenance['needsReview'] is True  # mock 自报待复核
        # 7.5 复盘契约要 topic_version_ids:主题行不带版本行 id 的话,
        # 复盘向导只能写死(此前 revision=1、主题三条硬编码的根因)
        assert row.get('versionId'), row
        version = repository.get_topic_version(project_id, row['versionId'])
        assert version is not None and version['topic_id'] == row['id']


def test_correction_keeps_provenance_and_create_is_human():
    """RENAME 继承来源;CREATE(人工从待归类反馈建题)→ human/非待复核。"""
    project_id = _project()
    _run_analysis(project_id)
    rows = client.get(f'/api/v1/projects/{project_id}/topics').json()['items']
    row = rows[0]
    revision = row['evidence']['revision']
    topic_id = row['id']

    corrected = client.post(
        f'/api/v1/projects/{project_id}/topics/{topic_id}/corrections',
        json={'operation': 'RENAME', 'expected_revision': revision,
              'name': '人工改名', 'reason': '核对原文后校正'},
    )
    assert corrected.status_code == 201, corrected.text
    rows_after = client.get(f'/api/v1/projects/{project_id}/topics').json()['items']
    renamed = next(r for r in rows_after if r['id'] == topic_id)
    assert renamed['title'] == '人工改名'
    assert renamed['evidence']['aiProvenance']['origin'] == 'unknown'  # 继承,不丢
    assert renamed['evidence']['aiProvenance']['needsReview'] is True


def test_apply_correction_create_marks_human_origin():
    """纯函数层:CREATE 的新主题 origin='human'、needs_review=False。"""
    snapshot = {
        'revision': 1,
        'topics': [{'topic_id': 't1', 'name': '旧主题', 'summary': '', 'severity': 'medium',
                    'feedback_count': 1, 'origin': 'http', 'needs_review': True}],
        'evidence_by_topic': {'t1': [{'feedback_id': 'fb1', 'quote': 'x',
                                      'quote_start': 0, 'quote_end': 1}]},
        'unassigned_count': 1,
    }
    new_snapshot, affected = apply_correction(
        snapshot, 'CREATE', 1,
        {'topic_id': 't1', 'name': '人工建题', 'feedback_ids': ['fb2']},
        '人工归置', {'fb2': '新出现的反馈正文'})
    created = next(t for t in new_snapshot['topics'] if t['topic_id'] != 't1')
    assert created['origin'] == 'human'
    assert created['needs_review'] is False
    assert affected == [created['topic_id']]


def test_published_evidence_points_at_real_segments():
    """证据行指回真实存在的分块:segment_id 非空、能在 segments 表找到、offset 覆盖引文。

    此前恒为空串:segments 表在写、feedback 源视图在读,却没有任何
    topic_evidence 行引用它——(version, feedback, segment) 唯一约束退化成反馈级。
    """
    from app.revisions import load_revision_snapshot

    project_id = _project()
    _run_analysis(project_id)
    run = next(a for a in repository.analyses.values() if a['project_id'] == project_id)
    snapshot = load_revision_snapshot(repository, run)
    assert snapshot['topics'], '分析已发布,快照应有主题'

    checked = 0
    for topic in snapshot['topics']:
        for item in repository.list_topic_evidence(project_id, topic['version_id']):
            assert item['segment_id'], f'evidence 行 segment_id 为空: {item}'
            segments = repository.list_segments(project_id, item['feedback_id'])
            by_id = {seg['id']: seg for seg in segments}
            assert item['segment_id'] in by_id, \
                f'segment_id {item["segment_id"]} 不在 segments 表: {list(by_id)}'
            seg = by_id[item['segment_id']]
            assert seg['start_offset'] <= item['quote_start']
            assert item['quote_end'] <= seg['end_offset']
            checked += 1
    assert checked > 0, '至少应核对一条证据'
