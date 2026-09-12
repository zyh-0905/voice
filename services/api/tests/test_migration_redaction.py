"""迁移 0011:存量 JSON 列就地脱敏(工程计划 7.2)。

读取侧已经会兜底,这层保证的是**静态数据本身**不含原始值——生产部署会把修复前
写入的行带过来,不能靠「请清库」来解决。
"""
import importlib.util
import json
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AnalysisRun, Dataset

_MIGRATION_PATH = (Path(__file__).resolve().parents[1]
                   / 'migrations' / 'versions' / '0011_redact_stored_rows.py')


def _load_migration():
    spec = importlib.util.spec_from_file_location('migration_0011', _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(engine, raw_row):
    """按历史形状写入:行数据、校验预览、规则扫描证据、已发布引文都带原始值。"""
    with Session(engine) as session:
        session.add(Dataset(
            id='ds_mig', project_id='p1', filename='批次.csv', status='uploaded',
            governance={'preview': {'rows': [dict(raw_row)]},
                        'validation': {'preview': {'rows': [dict(raw_row)]}}},
        ))
        session.add(AnalysisRun(
            id='run_mig', project_id='p1', dataset_id='ds_mig', status='done',
            result={
                'datasets': [{'id': 'ds_mig', 'preview': {'rows': [dict(raw_row)]}}],
                'analysis': {'evidence': [{'text': 'stored@example.com 13800009999'}]},
                'evidence_by_topic': {'t1': [{'quote': 'stored@example.com',
                                              'quote_start': 0, 'quote_end': 18}]},
            },
        ))
        session.commit()


RAW_ROW = {'email': 'stored@example.com', 'phone': '13800009999'}


def test_migration_redacts_every_stored_copy(tmp_path):
    engine = sa.create_engine(f'sqlite:///{tmp_path}/mig.db')
    Base.metadata.create_all(engine)
    _seed(engine, RAW_ROW)

    module = _load_migration()
    with engine.begin() as conn:
        assert module.redact_persisted_rows(conn) == 2, '数据集与 run 各应改写一行'

    with Session(engine) as session:
        dataset = session.get(Dataset, 'ds_mig')
        run = session.get(AnalysisRun, 'run_mig')

    blob = json.dumps({'d': dataset.governance, 'r': run.result}, ensure_ascii=False)
    assert 'stored@example.com' not in blob, '静态数据里仍有原始邮箱'
    assert '13800009999' not in blob, '静态数据里仍有原始手机号'
    # preview / validation.preview / 规则扫描证据 / 发布引文 四处副本都要覆盖
    assert blob.count('<EMAIL_REDACTED>') >= 4
    assert '<PHONE_REDACTED>' in blob


def test_migration_leaves_clean_rows_untouched(tmp_path):
    """已脱敏的行不该被改写——迁移必须可重复执行且不空转写库。"""
    engine = sa.create_engine(f'sqlite:///{tmp_path}/mig2.db')
    Base.metadata.create_all(engine)
    _seed(engine, RAW_ROW)

    module = _load_migration()
    with engine.begin() as conn:
        assert module.redact_persisted_rows(conn) == 2
    with engine.begin() as conn:
        assert module.redact_persisted_rows(conn) == 0, '第二次执行应是空操作'


def test_migration_skips_null_and_missing_columns(tmp_path):
    engine = sa.create_engine(f'sqlite:///{tmp_path}/mig3.db')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Dataset(id='ds_null', project_id='p1', filename='空的.csv',
                            status='uploaded', governance=None))
        session.commit()

    module = _load_migration()
    with engine.begin() as conn:
        assert module.redact_persisted_rows(conn) == 0
