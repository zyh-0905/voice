from alembic import op
import sqlalchemy as sa

revision = '0002_dataset_event_key'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('datasets', sa.Column('event_key', sa.String(length=64), nullable=True))
    op.create_index('ix_datasets_event_key', 'datasets', ['event_key'], unique=True)

def downgrade():
    op.drop_index('ix_datasets_event_key', table_name='datasets')
    op.drop_column('datasets', 'event_key')
