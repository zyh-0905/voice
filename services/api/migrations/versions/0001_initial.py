from alembic import op
from sqlalchemy import String, DateTime, Integer, JSON, Text, Column

revision = '0001_initial'; down_revision = None; branch_labels = None; depends_on = None
def upgrade():
    from app.models import Project, Dataset, AnalysisRun, AuditEvent
    for table in (Project.__table__, Dataset.__table__, AnalysisRun.__table__, AuditEvent.__table__):
        table.create(op.get_bind(), checkfirst=True)
def downgrade():
    for name in ('audit_events','analysis_runs','datasets','projects'): op.drop_table(name)
