from alembic import op
import sqlalchemy as sa

revision = '0002_dataset_event_key'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def _dataset_index_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    names = {index['name'] for index in inspector.get_indexes('datasets')}
    names |= {constraint['name'] for constraint in inspector.get_unique_constraints('datasets')}
    return {name for name in names if name}


def upgrade():
    # 0001 按**当前**模型定义建表,`datasets.event_key` 已经在里面了。这里必须守卫,
    # 否则全新库 upgrade 会以 DuplicateColumn 失败(0008/0010/0012 同款做法)。
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('datasets')}
    if 'event_key' not in existing:
        op.add_column('datasets', sa.Column('event_key', sa.String(length=64), nullable=True))
    if 'ix_datasets_event_key' not in _dataset_index_names():
        op.create_index('ix_datasets_event_key', 'datasets', ['event_key'], unique=True)


def downgrade():
    if 'ix_datasets_event_key' in _dataset_index_names():
        op.drop_index('ix_datasets_event_key', table_name='datasets')
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('datasets')}
    if 'event_key' in existing:
        op.drop_column('datasets', 'event_key')
