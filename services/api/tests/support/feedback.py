"""把一个 run 的手工构造行写进 feedback 实体表。

工程计划 5.2 之后,反馈正文的取数来源是 `feedback` 表,不再是 run 里内嵌的
`datasets[].preview.rows`。用例若只在 run 里摆行,测的就是一条生产上不存在的
取数路径——而这正是本项目反复出现的那类缺陷:「看起来接通了,实际是哑的」。

`seed_run_feedback` 走的是与导入完全相同的派生函数(`build_feedback_rows`),
所以测试数据与真实数据在 id、event_key、正文口径上一致。
"""
from __future__ import annotations

from app.ingestion import build_feedback_rows
from app.repository import InMemoryRepository

TEST_SECRET = 'test-dedupe-secret'


def new_repository() -> InMemoryRepository:
    return InMemoryRepository()


def seed_run_feedback(repository, run, *, secret: str = TEST_SECRET) -> list[str]:
    """把 run 内嵌的数据集行写进仓储,并把冻结的 feedback_id 清单写回 run。

    就地修改 `run` 并返回 id 列表:用例构造的是「一个 run 的输入集合」,
    冻结清单也是这个 run 的一部分(5.3 输入固定),分两步写容易只做一半。
    """
    project_id = run.get('project_id', 'p')
    frozen: list[str] = []
    for dataset in run.get('datasets') or []:
        dataset_id = dataset.get('id', 'ds')
        rows = (dataset.get('preview') or {}).get('rows') or []
        built = build_feedback_rows(
            {'id': dataset_id, 'project_id': project_id,
             'source_namespace': dataset.get('source_namespace'),
             'content_hash': dataset.get('content_hash') or 'test-hash',
             'preview': {'rows': rows}},
            secret=secret,
        )
        saved = repository.save_feedback_rows(project_id, dataset_id, built)
        frozen.extend(built[index]['id'] for index in saved['stored_indexes'])
    run['run_feedback_ids'] = frozen
    return frozen


def publish_revision_rows(repository, run, *, next_versions=None) -> bool:
    """把 run 里内嵌的快照物化成实体行(主题/版本/证据/revision)。

    走的是与生产发布**同一个**展开函数 `plan_revision`。用例若只往 run 里塞一个
    `result` dict,读模型算不出来——因为读取端已经只认实体表,而那只会在真实
    路径上表现为「主题列表是空的」。

    **刻意不放进 `seed_run_feedback`**:证据常常需要在播种之后才对齐到真实
    feedback_id,自动发布会在对齐之前就把错的 id 写进证据行,而那是静默的——
    分子照算、只是永远为 0。
    """
    from app.revisions import plan_revision

    snapshot = run.get('result') or {}
    if not snapshot.get('revision'):
        return False
    plan = plan_revision(run['project_id'], run['id'], snapshot, next_versions=next_versions)
    repository.save_revision(run['project_id'], run['id'], plan)
    return True


def run_with_feedback(run, *, project_id: str | None = None, secret: str = TEST_SECRET):
    """一次给出 (repository, run):用例不再需要自己记得先播种。"""
    repository = new_repository()
    if project_id is not None:
        run['project_id'] = project_id
    seed_run_feedback(repository, run, secret=secret)
    return repository, run
