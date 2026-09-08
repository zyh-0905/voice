from alembic import op
import sqlalchemy as sa

revision = '0003_domain_entities'
down_revision = '0002_dataset_event_key'
branch_labels = None
depends_on = None

def upgrade():
    for name, cols in {
        'risks': [('id', sa.String(64)), ('project_id', sa.String(64)), ('title', sa.String(255)), ('severity', sa.String(32)), ('status', sa.String(32)), ('evidence_count', sa.Integer())],
        'tasks': [('id', sa.String(64)), ('project_id', sa.String(64)), ('title', sa.String(255)), ('owner', sa.String(128)), ('status', sa.String(32)), ('priority', sa.String(32))],
        'reviews': [('id', sa.String(64)), ('project_id', sa.String(64)), ('run_id', sa.String(64)), ('status', sa.String(32)), ('finding', sa.Text()), ('confirmed_by', sa.String(128)), ('confirmed_at', sa.DateTime())],
    }.items():
        op.create_table(name, *[sa.Column(c, t, primary_key=(c == 'id'), nullable=(c in ('id','project_id','title','finding'))) for c,t in cols])
        op.create_index(f'ix_{name}_project_id', name, ['project_id'])

def downgrade():
    for name in ('reviews','tasks','risks'):
        op.drop_index(f'ix_{name}_project_id', table_name=name)
        op.drop_table(name)
