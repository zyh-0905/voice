"""reviews nullability reconciled with the model (W17)

Revision ID: 0013_reviews_nullable_columns
Revises: 0012_settings_memberships
Create Date: 2026-09-13

`reviews` 的迁移定义(0003)与 ORM 模型在可空性上**双向不一致**:

| 列 | 0003 建出来的 | 模型声明的 |
|---|---|---|
| finding | 可空 | NOT NULL |
| confirmed_by / confirmed_at / run_id | NOT NULL | 可空 |

两个方向都会炸,而且只在真实数据库上炸——内存仓储不校验列约束:

- `create_all` 建的库 finding 是 NOT NULL → 插入复盘 500(finding 是早期「效果复查」
  设计的遗留列,计划 5.2 的 reviews 表里根本没有它,复盘不再写它);
- 纯迁移建的库 confirmed_by/confirmed_at/run_id 是 NOT NULL → 同样插不进去。

这里只做**放宽**(NOT NULL → 可空),不收紧任何约束:方向单一,已有的行不会因此
变得非法。以模型为准,因为模型是应用实际写入的形状。
"""
from alembic import op
import sqlalchemy as sa

from app.models import Review

revision = '0013_reviews_nullable_columns'
down_revision = '0012_settings_memberships'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'reviews' not in set(sa.inspect(bind).get_table_names()):
        return
    existing = {column['name']: column for column in sa.inspect(bind).get_columns('reviews')}

    for column in Review.__table__.columns:
        current = existing.get(column.name)
        # 只放宽:模型允许为空、库里却要求非空,且不是主键
        if current is None or current.get('nullable') or column.primary_key:
            continue
        if column.nullable:
            _relax(column.name, column.type)


def _relax(name: str, type_) -> None:
    if op.get_bind().dialect.name == 'sqlite':
        # SQLite 不支持 ALTER COLUMN,走 batch 重建表
        with op.batch_alter_table('reviews') as batch:
            batch.alter_column(name, existing_type=type_, nullable=True)
    else:
        op.alter_column('reviews', name, existing_type=type_, nullable=True)


def downgrade():
    # 不恢复 NOT NULL:那会让此后写入的复盘行无法通过约束
    pass
