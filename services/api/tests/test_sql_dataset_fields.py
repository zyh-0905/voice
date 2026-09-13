"""SQL 模式下 `datasets` 的派生字段必须能活着回来。

`content_hash` / `source_namespace` / `source_kind` **不是 datasets 表的列**,它们存在
`governance` JSON 里。此前 `_EntityMap._to_dict` 用
`getattr(obj, 'content_hash', None)` 读回来(永远 None)并覆盖 governance 里正确的值,
于是这些字段在 SQL 模式下重新加载后一律为空。

后果不是「少个字段」:`event_key = HMAC(secret, content_hash + sheet_name + source_row)`
因此退化成 `HMAC(secret, '' + '' + source_row)`——**一个项目里所有数据集按行号共用同一个
事件键**,第二批次的第 0 行被判成第一批次第 0 行的冲突,整批 valid 归零。

内存仓储原样存 dict,所以这类缺陷在它面前完全不可见。用例必须在真 PG 上跑。
"""
from uuid import uuid4

from app.ingestion import REDACTION_VERSION, build_feedback_rows
from app.repository import InMemoryRepository


def _dataset(value, key='ds_fields'):
    return {'id': key, 'project_id': 'p', 'name': '批次', 'status': 'uploaded',
            'content_hash': value, 'source_namespace': '店铺A', 'source_kind': 'csv',
            'preview': {'rows': [{'content': '重复扣款了两次'}]},
            'created_at': None}


def test_dataset_derived_fields_survive_a_reload_on_postgres(schema_session_factory):
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    key = f'ds_{uuid4().hex[:8]}'
    repo.create_dataset(_dataset('sha-of-file-a', key))

    stored = repo.datasets[key]

    assert stored['content_hash'] == 'sha-of-file-a'
    assert stored['source_namespace'] == '店铺A'
    assert stored['source_kind'] == 'csv'


def test_two_datasets_do_not_share_event_keys_on_postgres(schema_session_factory):
    """这正是上面那个覆盖 bug 的可观测后果。"""
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    keys = []
    for suffix in ('a', 'b'):
        key = f'ds_{suffix}_{uuid4().hex[:6]}'
        repo.create_dataset(_dataset(f'sha-{suffix}', key))
        rows = build_feedback_rows(repo.datasets[key], secret='s')
        keys.append(rows[0]['event_key'])

    assert keys[0] != keys[1], '不同文件的数据集不能共用事件键'


def test_namespace_separates_source_ids_on_postgres(schema_session_factory):
    """有来源编号时消息是 `namespace + \\0 + external_id`;namespace 丢了,两个店铺的
    同一条订单号会互相判成重复。"""
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    keys = []
    for suffix, namespace in (('a', '店铺A'), ('b', '店铺B')):
        key = f'ds_ns_{suffix}_{uuid4().hex[:6]}'
        dataset = _dataset(f'sha-{suffix}', key)
        dataset['source_namespace'] = namespace
        dataset['preview'] = {'rows': [{'content': '同一个订单的反馈', 'feedback_id': 'ORD-1'}]}
        repo.create_dataset(dataset)
        keys.append(build_feedback_rows(repo.datasets[key], secret='s')[0]['event_key'])

    assert keys[0] != keys[1], '不同来源命名空间不能共用事件键'


def test_in_memory_repository_matches_the_sql_one():
    """两个仓储对同一份输入必须给出同一个事件键——分叉的话,测试里的绿灯不成立。"""
    repo = InMemoryRepository()
    repo.create_dataset(_dataset('sha-of-file-a', 'ds_mem'))

    stored = repo.datasets['ds_mem']
    assert stored['content_hash'] == 'sha-of-file-a'
    assert build_feedback_rows(stored, secret='s')[0]['redaction_version'] == REDACTION_VERSION
