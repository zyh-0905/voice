"""工程计划 5.2 最后三张表:analysis_stages / risk_findings / model_calls。

`risk_findings` 落地时**取代**了 `risks`:那张表不在 5.2 的清单里,而且少了
feedback_id / rule_id / policy_version / evidence_offsets 四列——代码一直在设这几个
字段,SQL 仓储按列过滤时把它们静默丢掉,内存仓储照收。所以这里先钉住「命中位置
真的落库了」,再钉住删除顺序(候选引用 feedback,顺序反了 PostgreSQL 会拒绝)。
"""
from uuid import uuid4

import pytest

import app.main as main
from app.main import repository
from app.risk_service import findings_to_entities, risk_entity_id
from app.segments import split_redacted
from support.client import make_client

client = make_client()


def _project(prefix='rt'):
    project_id = f'{prefix}_{uuid4().hex[:8]}'
    created = client.post('/api/v1/projects',
                          json={'name': f'测试项目 {project_id}', 'timezone': 'Asia/Shanghai'})
    assert created.status_code == 201, created.text
    return created.json()['id']


def _seed_feedback(project_id, dataset_id='ds_rt', contents=('重复扣款了两次',)):
    rows = [{'id': f'fb_{dataset_id}_{i}', 'event_key': f'k-{project_id}-{i}',
             'content_redacted': text, 'content_hash': f'h{i}', 'source_row': i,
             'channel': 'unknown', 'product': 'unknown', 'time_quality': 'missing',
             'identity_quality': 'source_id', 'redaction_version': 'v1'}
            for i, text in enumerate(contents)]
    repository.save_feedback_rows(project_id, dataset_id, rows)
    return [row['id'] for row in rows]


def _finding(project_id, feedback_id, rule_id='duplicate_charge', policy='v1', **extra):
    """一条候选。

    `feedback_id=None` 时 id 用哨兵拼——`risk_entity_id` 的输入必须是字符串,
    而演示种子那种没有来源反馈的候选本来也不走它(它由 `findings_to_entities` 之外的
    路径写入)。
    """
    identity = feedback_id if feedback_id is not None else 'seed'
    return {
        'id': risk_entity_id(project_id, identity, rule_id, policy),
        'feedback_id': feedback_id, 'source_row': 0, 'rule_id': rule_id,
        'policy_version': policy, 'severity': 'HIGH', 'reason': '订单被重复扣款',
        'evidence_offsets': {'start': 0, 'end': 6}, **extra,
    }


# —— 命中位置必须真的落库(这正是旧 schema 丢掉的那一列) ——

def test_evidence_offsets_survive_the_round_trip():
    project_id = _project('off')
    feedback_id = _seed_feedback(project_id)[0]

    repository.save_risk_findings(project_id, 'run_x', [_finding(project_id, feedback_id)])

    stored = repository.list_risk_findings(project_id)
    assert len(stored) == 1
    assert stored[0]['evidence_offsets'] == {'start': 0, 'end': 6}
    assert stored[0]['rule_id'] == 'duplicate_charge'
    assert stored[0]['policy_version'] == 'v1'
    assert stored[0]['feedback_id'] == feedback_id


def test_risk_view_exposes_rule_parts_and_hit_location():
    """前端契约:rule 由 rule_id 与策略版本拼回,命中位置与来源反馈一并给到。"""
    project_id = _project('view')
    feedback_id = _seed_feedback(project_id)[0]
    repository.save_risk_findings(project_id, 'run_y', [_finding(project_id, feedback_id)])

    body = client.get(f'/api/v1/projects/{project_id}/risks').json()
    item = body['items'][0]
    assert item['rule'] == 'duplicate_charge · v1'
    assert item['title'] == '订单被重复扣款'
    assert item['feedbackId'] == feedback_id
    assert item['evidenceOffsets'] == {'start': 0, 'end': 6}


def test_rescan_does_not_overwrite_a_human_decision():
    """6.4:已裁决的候选只保留——每跑一次分析就把人的判断冲掉是不可接受的。"""
    project_id = _project('human')
    feedback_id = _seed_feedback(project_id)[0]
    finding = _finding(project_id, feedback_id)
    repository.save_risk_findings(project_id, 'run_z', [finding])
    repository.update_risk_finding(project_id, finding['id'], {
        'review_state': 'excluded', 'review_reason': '已核对,是两笔正常订单',
        'reviewer_id': 'demo-user', 'version': 2})

    result = repository.save_risk_findings(project_id, 'run_z2', [
        {**finding, 'severity': 'CRITICAL', 'reason': '换了策略后的新理由'}])

    assert result['human_decided'] == 1 and result['created'] == 0
    stored = repository.get_risk_finding(project_id, finding['id'])
    assert stored['review_state'] == 'excluded'
    assert stored['severity'] == 'HIGH', '已裁决的候选不该被重新扫描改写'


def test_findings_to_entities_skips_rows_missing_identity():
    """缺 feedback_id / rule_id / policy_version 的条目跳过:那不是一条可复核的候选。"""
    rows = findings_to_entities('p', [
        {'feedback_id': 'fb_1', 'rule_id': 'r', 'policy_version': 'v1'},
        {'feedback_id': '', 'rule_id': 'r', 'policy_version': 'v1'},
        {'feedback_id': 'fb_2', 'rule_id': '', 'policy_version': 'v1'},
    ])
    assert len(rows) == 1 and rows[0]['feedback_id'] == 'fb_1'


# —— 删除顺序:候选引用 feedback,先删候选再删反馈 ——

def test_dataset_deletion_removes_its_findings_before_the_feedback(schema_session_factory):
    """顺序反了 PostgreSQL 会直接拒绝删除(复合外键)。

    在真库上验证:这是「内存仓储不校验外键、于是排序错了也全绿」的那类缺陷。
    """
    from app.deletions import execute_deletion
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('delorder')
    repo.create_project({'id': project_id, 'name': '删除顺序'})
    repo.save_feedback_rows(project_id, 'ds_d', [
        {'id': 'fb_d_0', 'event_key': 'k-d', 'content_redacted': '重复扣款了两次',
         'content_hash': 'hd', 'source_row': 0, 'channel': 'unknown', 'product': 'unknown',
         'time_quality': 'missing', 'identity_quality': 'source_id', 'redaction_version': 'v1'}])
    repo.save_risk_findings(project_id, 'run_d', [_finding(project_id, 'fb_d_0')])
    repo.create_dataset({'id': 'ds_d', 'project_id': project_id, 'name': '批次', 'rows': 1,
                         'preview': {'rows': []}})

    receipt = execute_deletion(repo, project_id, 'dataset', 'ds_d', '批次', 'job_d', 'demo-user')

    assert repo.list_feedback(project_id, ['ds_d']) == []
    assert repo.list_risk_findings(project_id) == []
    assert receipt['removed']['risks'] == 1


def test_project_deletion_removes_findings_that_have_no_feedback(schema_session_factory):
    """演示种子那种没有 feedback_id 的候选也要随项目走,不能留下孤儿行。"""
    from app.deletions import execute_deletion
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('delproj')
    repo.create_project({'id': project_id, 'name': '整项目'})
    repo.save_risk_findings(project_id, None, [_finding(project_id, None, rule_id='R-204')])

    execute_deletion(repo, project_id, 'project', project_id, '整项目', 'job_p', 'demo-user')
    assert repo.list_risk_findings(project_id) == []


# —— 阶段与模型调用:流水线真的写它们 ——

def test_pipeline_records_stages_and_model_calls():
    """5.2:阶段与模型调用必须由流水线真的写入,不是两张空表。

    阶段回答「跑到哪一步、重试几次、产物哈希」,模型调用回答「预算花了多少」——
    两张表此前都不存在,于是 6.2 的恢复与 10.5 的预算都没有落脚点。
    """
    pytest.importorskip('sklearn')
    project_id = _project('stages')
    # 至少要让聚类产出**一个簇**,否则命名阶段根本不会被调用,模型调用记录自然为空
    # (那会让这个用例变成在验证「空表也是空表」)。
    lines = [f'重复扣款了两次请核查 编号{i}' for i in range(6)]
    lines += [f'物流信息一直没有更新 编号{i}' for i in range(6)]
    upload = client.post(
        f'/api/v1/projects/{project_id}/datasets',
        files={'file': ('a.csv', ('content\n' + '\n'.join(lines) + '\n').encode())},
        data={'consent': 'true'})
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()['id']
    validated = client.post(f'/api/v1/projects/{project_id}/datasets/{dataset_id}/validate',
                            json={'mapping': {'content': 'content'}})
    assert validated.status_code == 202, validated.text

    run_id = client.post(f'/api/v1/projects/{project_id}/analyses',
                         json={'dataset_ids': [dataset_id]}).json()['id']
    main.worker.run(run_id)

    stages = {row['stage'] for row in repository.list_stages(project_id, run_id)}
    assert {'govern', 'segment', 'cluster', 'publish', 'scan'} <= stages, stages
    assert all(row['state'] == 'DONE' for row in repository.list_stages(project_id, run_id))

    calls = repository.list_model_calls(project_id, run_id)
    assert calls, '命名阶段必须留下模型调用记录'
    # 没有可靠价格配置时留 NULL,不填 0——0 会让「免费」和「不知道多少钱」看起来一样
    assert all(call['cost_actual'] is None and call['cost_estimated'] is None for call in calls)
    assert all(call['provider'] for call in calls)


def test_dataset_deletion_purges_the_runs_stages_and_model_calls(schema_session_factory):
    """数据集删除要清受影响 run 的 stages/model_calls(真库)。

    这两张表没有外键挂在 analysis_runs 上:run 行删掉后,旧实现留下孤儿行,
    而内存仓储不建外键、发现不了——这正是要在真 PG 上钉住的一类。
    """
    from app.deletions import execute_deletion
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('delrundata')
    repo.create_project({'id': project_id, 'name': 'run 数据清理'})
    repo.save_feedback_rows(project_id, 'ds_r', [
        {'id': 'fb_r_0', 'event_key': 'k-r', 'content_redacted': '重复扣款了两次',
         'content_hash': 'hr', 'source_row': 0, 'channel': 'unknown', 'product': 'unknown',
         'time_quality': 'missing', 'identity_quality': 'source_id', 'redaction_version': 'v1'}])
    repo.create_analysis({'id': 'run_r', 'project_id': project_id, 'dataset_ids': ['ds_r'],
                          'datasets': [], 'status': 'done', 'stage': 'completed', 'total': 1})
    repo.save_stages(project_id, 'run_r', [
        {'stage': 'CLUSTERING', 'state': 'SUCCEEDED', 'config_hash': 'h'}])
    repo.save_model_call(project_id, {'id': 'mc_r_1', 'run_id': 'run_r', 'purpose': 'naming',
                                      'provider': 'mock', 'state': 'MOCK', 'model': 'mock'})
    repo.create_dataset({'id': 'ds_r', 'project_id': project_id, 'name': '批次', 'rows': 1,
                         'preview': {'rows': []}})
    assert repo.count_run_data_for_run(project_id, 'run_r') == 2

    receipt = execute_deletion(repo, project_id, 'dataset', 'ds_r', '批次', 'job_r', 'demo-user')

    assert repo.count_run_data_for_run(project_id, 'run_r') == 0
    verify = next(step for step in receipt['steps'] if step['name'] == 'verify')
    assert verify['remaining']['run_data'] == 0
