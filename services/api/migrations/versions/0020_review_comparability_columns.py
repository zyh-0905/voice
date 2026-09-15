"""reviews gains the comparability columns it always claimed (W17)

Revision ID: 0020_review_comparability
Revises: 0019_align_nullability
Create Date: 2026-09-15

POST /reviews 的响应一直带 comparability / reasons / filters /
alignment_confirmed(main.py 本地拼的 dict),但这四列**不在 reviews 表里**。
SQL 仓储按列名过滤写入与读取(sql_repository._EntityMap),于是:

- POST 侥幸「正常」——端点返回的是本地 dict,不是仓储返回值;
- GET /reviews 与 GET /reviews/{id} 走仓储按列返回 → 四个字段永远丢失;
- 前端复盘详情页读 `record.reasons.length` → TypeError 崩页。

这是 SQL-only 缺陷:内存仓储原样收 dict,全套件在内存模式下绿。真实
PostgreSQL(compose 生产栈与 real-api 套件)上创建复盘后打不开详情。

存量行回填:comparability='insufficient'、reasons='[]'、filters='{}'——
旧行无从判定可比性,如实标不可比,不编造一个 ok。
"""
from alembic import op
import sqlalchemy as sa

revision = '0020_review_comparability'
down_revision = '0019_align_nullability'
branch_labels = None
depends_on = None

_COLUMNS = (
    ('comparability', sa.String(length=32)),
    ('reasons', sa.JSON()),
    ('filters', sa.JSON()),
    ('alignment_confirmed', sa.Boolean()),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column('reviews', sa.Column(name, type_, nullable=True))
    # 回填:新列全可空,旧行不补一个「看起来可比」的值
    # (裸字面量由 PG 按 json 输入函数解析;jsonb 到 json 没有赋值转换)
    op.execute("UPDATE reviews SET comparability = 'insufficient' WHERE comparability IS NULL")
    op.execute("UPDATE reviews SET reasons = '[]' WHERE reasons IS NULL")
    op.execute("UPDATE reviews SET filters = '{}' WHERE filters IS NULL")
    op.execute("UPDATE reviews SET alignment_confirmed = false WHERE alignment_confirmed IS NULL")


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column('reviews', name)
