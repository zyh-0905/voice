"""工程计划 5.2:feedback / segments 是实体表,不是 run 里的 JSON 副本。

此前反馈正文以 JSON 副本躺在 `datasets.governance->preview->rows` 里,再整份
复制进 `analysis_runs.result`。计划对这件事有明文禁止:

    「不要为了"减少表数"把整个项目装进一个不可查询的 JSON 字段。」

这些用例钉住的是**结构改变带来的能力**,不只是一次搬家:

- 4.4 的 `(project_id, event_key)` 事件幂等现在有唯一约束可依;
- 4.4 的 SOURCE_ID_CONFLICT 不能被静默覆盖;
- 10.4 的按行删除清单有了可执行的对象;
- 4.3 的预览上限让 JSON 副本不可能再冒充全量数据源。
"""
from uuid import uuid4

import pytest

import app.main as main
from app.main import repository
from support.client import make_client

client = make_client()


def _project(prefix='fb'):
    """建项目并返回 id。

    证据源端点会显式校验项目存在(其他端点只校验数据集归属),所以用例不能
    像别处那样只靠上传隐式建档。
    """
    project_id = f'{prefix}_{uuid4().hex[:8]}'
    created = client.post('/api/v1/projects',
                          json={'name': f'测试项目 {project_id}', 'timezone': 'Asia/Shanghai'})
    assert created.status_code == 201, created.text
    return created.json()['id']


def _upload(project_id, filename, payload, **form):
    return client.post(
        f'/api/v1/projects/{project_id}/datasets',
        files={'file': (filename, payload)},
        data={'consent': 'true', **form},
    )


def _validate(project_id, dataset_id, body):
    return client.post(f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate', json=body)


def _ingest(project_id, filename, csv_text, mapping, **form):
    """上传并治理一个批次,返回 (dataset_id, 响应体)。"""
    upload = _upload(project_id, filename, csv_text.encode(), **form)
    assert upload.status_code == 201, upload.text
    validated = _validate(project_id, upload.json()['id'], {'mapping': mapping})
    assert validated.status_code == 202, validated.text
    return upload.json()['id'], validated.json()


FEEDBACK_MAPPING = {'msg': 'content', 'fid': 'feedback_id'}


# —— 5.2:反馈真的落进了实体表 ——

def test_validated_rows_land_in_the_feedback_table():
    """治理后的行必须进入 feedback 实体表,而不是只留在 JSON 预览里。"""
    project_id = _project('land')
    dataset_id, body = _ingest(project_id, 'a.csv',
                              'msg,fid\n物流很慢,ext-1\n退款没到账,ext-2\n', FEEDBACK_MAPPING)

    rows = repository.list_feedback(project_id, [dataset_id])
    assert [row['content_redacted'] for row in rows] == ['物流很慢', '退款没到账']
    assert [row['external_id'] for row in rows] == ['ext-1', 'ext-2']
    assert {row['redaction_version'] for row in rows} == {'v1'}
    # event_key 是 HMAC-SHA256 十六进制,4.4 的幂等就建在它上面
    assert all(len(row['event_key']) == 64 for row in rows)
    assert body['preview']['stats']['valid'] == 2


def test_feedback_id_shape_is_preserved_for_evidence_links():
    """`fb_{dataset_id}_{序号}` 是证据链接与导出一直在用的形状,不能因为换表而改变。"""
    project_id = _project('idshape')
    dataset_id, body = _ingest(project_id, 'a.csv', 'msg,fid\n甲,ext-1\n乙,ext-2\n', FEEDBACK_MAPPING)

    ids = [row['id'] for row in repository.list_feedback(project_id, [dataset_id])]
    assert ids == [f'fb_{dataset_id}_0', f'fb_{dataset_id}_1']
    # 预览行本身仍是标准字段行,前端表格靠它渲染
    assert [row['content'] for row in body['preview']['rows']] == ['甲', '乙']


# —— 4.4:事件幂等与冲突 ——

def test_same_source_id_same_content_is_a_duplicate_and_keeps_first_owner():
    """4.4:同 event_key 同内容 → duplicate,不新增反馈,归属仍是首次有效导入的批次。"""
    project_id = _project('dup')
    first_id, _ = _ingest(project_id, 'a.csv', 'msg,fid\n同一条反馈,ext-1\n',
                          FEEDBACK_MAPPING, source_namespace='店铺A')
    second_id, second = _ingest(project_id, 'b.csv', 'msg,fid\n同一条反馈,ext-1\n',
                                FEEDBACK_MAPPING, source_namespace='店铺A')

    assert second['preview']['stats']['duplicate'] == 1
    assert second['preview']['stats']['valid'] == 0
    # 4.4:必须告知用户这些行属于哪个既有批次,否则「本批 N 行」会误导分析范围
    assert second['health']['existingDatasetIds'] == [first_id]
    # 第二条批次自己没有落库任何反馈
    assert repository.list_feedback(project_id, [second_id]) == []
    assert len(repository.list_feedback(project_id, [first_id])) == 1


def test_same_source_id_different_content_reports_conflict_without_overwriting():
    """4.4:同 event_key 异内容 → SOURCE_ID_CONFLICT,不能无提示覆盖历史证据。"""
    project_id = _project('conflict')
    first_id, _ = _ingest(project_id, 'a.csv', 'msg,fid\n甲反馈,ext-9\n',
                          FEEDBACK_MAPPING, source_namespace='店铺A')
    second_id, second = _ingest(project_id, 'b.csv', 'msg,fid\n乙反馈,ext-9\n',
                                FEEDBACK_MAPPING, source_namespace='店铺A')

    codes = [error['code'] for error in second['validation']['errors']]
    assert 'SOURCE_ID_CONFLICT' in codes
    assert second['preview']['stats']['invalid'] == 1
    # 历史证据保持原样:冲突不能把甲反馈改写成乙反馈
    stored = repository.list_feedback(project_id, [first_id])
    assert [row['content_redacted'] for row in stored] == ['甲反馈']
    assert second['health']['existingDatasetIds'] == [first_id]
    assert repository.list_feedback(project_id, [second_id]) == []


def test_same_text_with_different_source_ids_are_two_events():
    """4.4:相同文本、不同来源 ID 是不同反馈事件,全部保留。

    用正文哈希做幂等会在这里把它们错误地合并成一条——而这两条来自
    两个不同的事件,合并就是丢数据。
    """
    project_id = _project('twoevents')
    first_id, _ = _ingest(project_id, 'a.csv', 'msg,fid\n包装破损了,ext-a\n',
                          FEEDBACK_MAPPING, source_namespace='店铺A')
    second_id, second = _ingest(project_id, 'b.csv', 'msg,fid\n包装破损了,ext-b\n',
                                FEEDBACK_MAPPING, source_namespace='店铺A')

    assert second['preview']['stats']['duplicate'] == 0
    assert second['preview']['stats']['invalid'] == 0
    assert second['preview']['stats']['valid'] == 1
    assert len(repository.list_feedback(project_id, [first_id])) == 1
    assert len(repository.list_feedback(project_id, [second_id])) == 1


def test_revalidating_a_dataset_does_not_conflict_with_itself():
    """重跑校验(改字段映射)必须幂等。

    行位置一变,`id` 就会跟着变;若按「同 event_key 异内容」处理,重跑一次
    校验每条反馈都会撞上上一轮的自己,整批变成 SOURCE_ID_CONFLICT——
    而用户只是换了个映射。
    """
    project_id = _project('reval')
    upload = _upload(project_id, 'a.csv', 'msg,ch,fid\n物流很慢,客服,ext-1\n'.encode())
    dataset_id = upload.json()['id']

    first = _validate(project_id, dataset_id, {'mapping': {'msg': 'content', 'fid': 'feedback_id'}})
    assert first.status_code == 202
    assert first.json()['preview']['stats']['valid'] == 1

    second = _validate(project_id, dataset_id,
                       {'mapping': {'msg': 'content', 'ch': 'channel', 'fid': 'feedback_id'}})
    assert second.status_code == 202
    body = second.json()
    assert body['preview']['stats']['valid'] == 1
    assert body['preview']['stats']['duplicate'] == 0
    assert body['validation']['errors'] == []
    # 就地把渠道补上,而不是新增一条
    stored = repository.list_feedback(project_id, [dataset_id])
    assert len(stored) == 1
    assert stored[0]['channel'] == '客服'


def test_revalidation_drops_rows_that_no_longer_exist():
    """改严时间策略后不再有效的行必须一并清掉。

    留着上一轮的正文,而分析看的是「当前有效批次」——那种分歧没有任何报错,
    只会让主题与分母悄悄包含一批已经被判无效的数据。
    """
    project_id = _project('prune')
    mapping = {'msg': 'content', 'ts': 'created_at'}
    upload = _upload(project_id, 'a.csv', 'msg,ts\n甲,2026-08-26\n乙,\n'.encode())
    dataset_id = upload.json()['id']

    static = _validate(project_id, dataset_id, {'mapping': mapping, 'time_policy': 'static'})
    assert static.json()['preview']['stats']['valid'] == 2
    assert len(repository.list_feedback(project_id, [dataset_id])) == 2

    strict = _validate(project_id, dataset_id, {'mapping': mapping, 'time_policy': 'strict'})
    assert strict.json()['preview']['stats']['valid'] == 1
    assert [row['content_redacted'] for row in repository.list_feedback(project_id, [dataset_id])] \
        == ['甲']


# —— 4.3/4.5:预览与健康计数 ——

def test_preview_is_capped_and_contains_only_stored_rows():
    """4.3:预览最多 20 行;而且必须是真正落库的那些行。

    预览若含被拒或被判重复的行,用户照着它校对映射就是在校对不存在的行。
    """
    project_id = _project('cap')
    lines = ['msg,fid'] + [f'反馈{i},ext-{i}' for i in range(25)]
    _, body = _ingest(project_id, 'big.csv', '\n'.join(lines) + '\n', FEEDBACK_MAPPING)

    assert body['preview']['sample_limit'] == 20
    assert len(body['preview']['rows']) == 20
    assert body['preview']['stats']['valid'] == 25


def test_health_identity_holds_after_cross_dataset_dedupe():
    """4.5:input = valid + invalid + duplicate,跨批次去重之后仍要成立。

    去重把行从 valid 移到 duplicate;不回填的话这个恒等式会悄悄失衡,
    而健康报告是用户判断「这批数据能不能用」的唯一依据。
    """
    project_id = _project('health')
    _ingest(project_id, 'a.csv', 'msg,fid\n甲,ext-1\n乙,ext-2\n', FEEDBACK_MAPPING,
            source_namespace='店铺A')
    _, second = _ingest(project_id, 'b.csv', 'msg,fid\n丙,ext-3\n甲,ext-1\n', FEEDBACK_MAPPING,
                        source_namespace='店铺A')

    stats = second['preview']['stats']
    assert stats['total'] == stats['valid'] + stats['invalid'] + stats['duplicate']
    assert stats['duplicate'] == 1 and stats['valid'] == 1


# —— 5.3:run 冻结输入 ——

def test_run_freezes_its_feedback_input():
    """5.3「输入固定」:run 创建后新增的反馈不得隐式扩大它的输入集合。

    冻结清单落 `run_feedbacks` 表(5.2),不是 run JSON 里的一个数组——
    进了表才有 `(run_id, feedback_id)` 唯一约束,以及「不得指向已删反馈」的外键。
    """
    project_id = _project('freeze')
    dataset_id, _ = _ingest(project_id, 'a.csv', 'msg,fid\n甲,ext-1\n', FEEDBACK_MAPPING)

    created = client.post(f'/api/v1/projects/{project_id}/analyses',
                          json={'dataset_ids': [dataset_id]})
    assert created.status_code == 202
    run_id = created.json()['id']
    frozen = repository.list_run_feedback_ids(project_id, run_id)
    assert len(frozen) == 1
    assert created.json()['total'] == 1

    # run 已创建,此时再治理一个更宽的批次
    _ingest(project_id, 'b.csv', 'msg,fid\n乙,ext-2\n丙,ext-3\n', FEEDBACK_MAPPING,
            source_namespace='店铺B')

    from app.ingestion import run_feedback
    run = main.analyses[run_id]
    assert [row['id'] for row in run_feedback(run, repository)] == frozen
    assert len(run_feedback(run, repository)) == 1


def test_deleting_a_run_purges_its_frozen_input(schema_session_factory):
    """冻结清单随 run 一起走:留着它会指向已删的反馈,而复合外键正是为了不让
    这种情况发生——清理顺序反了,删除会直接失败。"""
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('cascade')
    dataset = {'id': 'ds_c', 'project_id': project_id, 'source_namespace': '店铺',
               'content_hash': 'h', 'preview': {'rows': [{'content': '甲反馈'}]}}
    from app.ingestion import build_feedback_rows
    repo.save_feedback_rows(project_id, 'ds_c', build_feedback_rows(dataset, secret='s'))
    feedback_id = repo.list_feedback(project_id, ['ds_c'])[0]['id']
    assert repo.save_run_feedbacks(project_id, 'run_c', [feedback_id]) == 1

    # 顺序正确:先清单后反馈
    assert repo.delete_run_feedbacks_for_run(project_id, 'run_c') == 1
    assert repo.delete_feedback_for_dataset(project_id, 'ds_c') == 1

    # 顺序颠倒时复合外键必须拒绝——否则「冻结输入」只是注释
    repo.save_feedback_rows(project_id, 'ds_c', build_feedback_rows(dataset, secret='s'))
    other_id = repo.list_feedback(project_id, ['ds_c'])[0]['id']
    repo.save_run_feedbacks(project_id, 'run_d', [other_id])
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        repo.delete_feedback_for_dataset(project_id, 'ds_c')


# —— 8.1/8.2:分块落库 ——

def test_pipeline_persists_segments_whose_offsets_restore_the_text():
    """8.2:分块 offset 指向脱敏正文的 Unicode 字符位置,且能逐字复原。"""
    pytest.importorskip('sklearn')  # 流水线需要聚类
    project_id = _project('seg')
    # 正文里不能出现逗号——那会改变 CSV 的列数,与分块无关
    body_csv = 'msg,fid\n' + '\n'.join(
        f'包装破损需要处理。编号{i}请尽快回复。,seg-{i}' for i in range(6)) + '\n'
    dataset_id, _ = _ingest(project_id, 'a.csv', body_csv, FEEDBACK_MAPPING)

    created = client.post(f'/api/v1/projects/{project_id}/analyses',
                          json={'dataset_ids': [dataset_id]})
    run_id = created.json()['id']
    main.worker.run(run_id)

    feedback_id = repository.list_feedback(project_id, [dataset_id])[0]['id']
    segments = repository.list_segments(project_id, feedback_id)
    assert segments, '流水线必须把分块落进 segments 表'
    text = repository.get_feedback(project_id, feedback_id)['content_redacted']
    for item in segments:
        assert 0 <= item['start_offset'] < item['end_offset'] <= len(text)

    # 证据源查询读的就是这批分块,而不是每次按当时参数现算
    body = client.get(f'/api/v1/projects/{project_id}/feedback/{feedback_id}').json()
    assert [(s['start'], s['end']) for s in body['segments']] == \
        [(s['start_offset'], s['end_offset']) for s in segments]


# —— 10.4:删除 ——

def test_deleting_a_dataset_purges_its_feedback_and_segments():
    """10.4:删批次必须连反馈与分块一起走——分块是正文的切片,offset 能直接复原原文。"""
    project_id = _project('del')
    dataset_id, _ = _ingest(project_id, 'a.csv', 'msg,fid\n甲,ext-1\n乙,ext-2\n', FEEDBACK_MAPPING)
    feedback_id = repository.list_feedback(project_id, [dataset_id])[0]['id']
    from app.segments import split_redacted
    repository.replace_segments(project_id, feedback_id,
                                split_redacted('包装破损了。' * 8, max_tokens=10, overlap=0), 'v1')
    assert repository.count_segments(project_id) > 0

    preview = client.post(
        f'/api/v1/projects/{project_id}/deletions/preview',
        json={'target_type': 'dataset', 'target_id': dataset_id},
    ).json()
    assert preview['feedback'] == 2

    deleted = client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'dataset', 'target_id': dataset_id,
        'confirm_name': preview['target_name'],
    })
    assert deleted.status_code == 202, deleted.text
    assert repository.list_feedback(project_id, [dataset_id]) == []
    assert repository.count_segments(project_id) == 0
    assert deleted.json()['removed']['feedback'] == 2


# —— 真实 PostgreSQL:约束真的在库上 ——

def test_postgres_enforces_event_uniqueness_and_stores_segments(schema_session_factory):
    """真实 PostgreSQL 上验证 4.4 的唯一约束确实存在。

    内存仓储不校验约束,SQLite 也不完整支持——只有真库能证明「同项目同
    event_key 只能有一条反馈」不是一句注释。
    """
    from sqlalchemy.exc import IntegrityError

    from app.ingestion import build_feedback_rows
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('pg')
    dataset = {'id': 'ds_pg', 'project_id': project_id, 'source_namespace': '店铺A',
               'content_hash': 'h', 'preview': {'rows': [{'content': '甲反馈', 'feedback_id': 'ext-1'}]}}
    built = build_feedback_rows(dataset, secret='pg-secret')

    saved = repo.save_feedback_rows(project_id, 'ds_pg', built)
    assert saved['inserted'] == 1
    stored = repo.list_feedback(project_id, ['ds_pg'])
    assert [row['content_redacted'] for row in stored] == ['甲反馈']
    # occurred_at 两个仓储都必须是 ISO 字符串:调用方按字符串解析时间
    assert stored[0]['occurred_at'] is None or isinstance(stored[0]['occurred_at'], str)

    from app.segments import split_redacted
    feedback_id = stored[0]['id']
    repo.replace_segments(project_id, feedback_id,
                          split_redacted('甲反馈。' * 20, max_tokens=10, overlap=0), 'v1')
    segments = repo.list_segments(project_id, feedback_id)
    assert segments and segments[0]['start_offset'] == 0

    # 绕过 save_feedback_rows 的冲突判定,直接插同 event_key 的第二条
    from app.models import Feedback
    with pytest.raises(IntegrityError):
        with repo.session() as session, session.begin():
            session.add(Feedback(
                id='fb_pg_conflict', project_id=project_id, dataset_id='ds_other',
                event_key=built[0]['event_key'], content_redacted='乙反馈',
                content_hash='hash2', time_quality='missing', channel='unknown',
                product='unknown', source_row=0, identity_quality='source_id',
                redaction_version='v1',
            ))
            session.flush()


def test_segments_cannot_reference_a_foreign_project(schema_session_factory):
    """5.1:跨表引用必须用 (project_id, id) 复合外键,防止 A 项目对象引用 B 项目反馈。"""
    from sqlalchemy.exc import IntegrityError

    from app.models import Feedback, Segment
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    with repo.session() as session, session.begin():
        session.add(Feedback(
            id='fb_owner', project_id='prj_a', dataset_id='ds_a', event_key='k1',
            content_redacted='本项目反馈', content_hash='h', time_quality='missing',
            channel='unknown', product='unknown', source_row=0,
            identity_quality='source_id', redaction_version='v1',
        ))
        session.flush()

    with pytest.raises(IntegrityError):
        with repo.session() as session, session.begin():
            # 项目对不上:复合外键 (project_id, feedback_id) 必须拒绝
            session.add(Segment(id='seg_foreign', project_id='prj_b', feedback_id='fb_owner',
                                start_offset=0, end_offset=2, segment_index=0,
                                redaction_version='v1'))
            session.flush()


# —— 全重复批次:状态与可否分析 ——

def test_fully_duplicated_batch_is_not_ready_and_cannot_be_analyzed():
    """4.4:一批行全部被判重复时,它一条反馈都没贡献。

    标成 READY 并放行分析会产出 0 输入、0 主题的空 run,而用户以为这批被分析了。
    状态要降级,分析要被挡住,并且要告诉用户这些行归属在哪个批次上——
    他该做的是去分析那个批次,不是重传一遍。
    """
    project_id = _project('alldup')
    owner_id, _ = _ingest(project_id, 'a.csv', 'msg,fid\n甲,ext-1\n乙,ext-2\n', FEEDBACK_MAPPING,
                          source_namespace='店铺A')
    dup_id, dup = _ingest(project_id, 'b.csv', 'msg,fid\n甲,ext-1\n乙,ext-2\n', FEEDBACK_MAPPING,
                          source_namespace='店铺A')

    assert dup['preview']['stats']['valid'] == 0
    assert dup['preview']['stats']['duplicate'] == 2
    assert dup['state'] == 'READY_WITH_WARNINGS'
    assert dup['health']['existingDatasetIds'] == [owner_id]

    blocked = client.post(f'/api/v1/projects/{project_id}/analyses', json={'dataset_ids': [dup_id]})
    assert blocked.status_code == 422
    detail = blocked.json()['detail']
    assert detail['code'] == 'no_feedback_to_analyze'
    assert detail['existing_dataset_ids'] == [owner_id]
    # 没有产生任何 run
    assert client.get(f'/api/v1/projects/{project_id}/analyses').json()['total'] == 0

    # 归属批次本身照样可以分析
    allowed = client.post(f'/api/v1/projects/{project_id}/analyses', json={'dataset_ids': [owner_id]})
    assert allowed.status_code == 202
    assert allowed.json()['total'] == 2
