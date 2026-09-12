"""redact persisted preview rows (7.2 / 10.2)

Revision ID: 0011_redact_stored_rows
Revises: 0010_export_jobs
Create Date: 2026-09-12

导入侧现在落库即脱敏,但此前写入的数据把解析后的**原始行**存进了 JSON 列
(`datasets.governance` 与 `analysis_runs.result`,后者含数据集快照、规则扫描证据
与已发布引文)。计划 7.2 要求「持久业务正文只保留脱敏结果」——读取侧虽然已经
兜底,但原文躺在库里本身就是不合规的,所以这里就地脱敏一次。

刻意复用 `app.ingestion.redact_text` 而不是内联一份正则副本:读取路径每次都按
**当时**的规则再脱敏一次,迁移复用活函数才不会留下永远不更新的影子规则。

已知代价:旧 run 的 `quote_start`/`quote_end` 是按原始正文算的,脱敏后不再自洽。
读取侧不做 offset 校验(`topic_evidence_from_run` 只透传),因此不会读坏;新 run
的正文导入即脱敏,端到端自洽。
"""
import json

from alembic import op
import sqlalchemy as sa

from app.ingestion import redact_text

revision = '0011_redact_stored_rows'
down_revision = '0010_export_jobs'
branch_labels = None
depends_on = None


def _redact_deep(value):
    """递归脱敏:JSON 列里既有行数据,也有发布引文与规则扫描片段。"""
    if isinstance(value, str):
        return redact_text(value)['text']
    if isinstance(value, dict):
        return {key: _redact_deep(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_deep(item) for item in value]
    return value


def redact_persisted_rows(bind) -> int:
    """把存量 JSON 列就地脱敏,返回改写的行数。

    走反射表而不是裸 SQL:JSON 列的编解码交给 SQLAlchemy,PostgreSQL 与 sqlite
    两种驱动行为一致。
    """
    metadata = sa.MetaData()
    table_names = set(sa.inspect(bind).get_table_names())
    rewritten = 0

    targets = (('datasets', 'governance'), ('analysis_runs', 'result'))
    for table_name, column_name in targets:
        if table_name not in table_names:
            continue
        table = sa.Table(table_name, metadata, autoload_with=bind)
        if column_name not in table.c:
            continue
        for row in bind.execute(sa.select(table.c.id, table.c[column_name])).fetchall():
            row_id, stored = row[0], row[1]
            if stored is None:
                continue
            # sqlite 下经反射列读出的是文本,统一成 Python 对象再处理
            if isinstance(stored, str):
                try:
                    stored = json.loads(stored)
                except ValueError:
                    pass
            scrubbed = _redact_deep(stored)
            if scrubbed == stored:
                continue
            bind.execute(
                table.update().where(table.c.id == row_id).values({column_name: scrubbed})
            )
            rewritten += 1
    return rewritten


def upgrade():
    redact_persisted_rows(op.get_bind())


def downgrade():
    """脱敏不可逆:原始值已经不存在,没有回滚路径。"""
    pass
