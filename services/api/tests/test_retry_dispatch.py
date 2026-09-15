"""retry 端点的派发行为:compose 栈上 run 永远停在 queued 的那个缺陷。

此前 retry 只改状态不派发:USE_CELERY 分支没有任何注入方(恒 false),compose
也不设 RUN_WORKER_INLINE,而 outbox 里没有新事件、relay 只认 analysis.created——
重试的 run 从此停在 queued。这里的用例钉住「retry 必须落一条 relay 认识并
真的会派发的事件」,以及 inline 分支与 409 分支的行为。
"""
import pytest

from app.main import analyses, repository
from app.outbox_relay import OutboxRelay
from support.client import make_client

client = make_client()


@pytest.fixture(autouse=True)
def _settle_runs():
    """用例前后都把遗留的 queued/running run 置为终态。

    测试里 POST /analyses 不会真正执行(无 worker、无 inline),run 停在 queued;
    而每项目只允许一个活跃分析(4.1)——别的文件留下的 queued run 会挡住本文件
    的用例(单跑通过、顺序跑 409),本文件留下的也会挡住后面的文件。
    """
    def _cancel_active():
        for run in analyses.values():
            if run.get('status') in ('queued', 'running'):
                run.update(status='cancelled', stage='cancelled')
    _cancel_active()
    yield
    _cancel_active()

# 6 行数据:分块/聚类在单行上退化为纯噪声,给流水线一点可用的输入。
# 每次内容唯一:同字节重传会被 4.4 的去重并回同一批次(返回 200 而非 201)。
_seq = iter(range(10_000))


def _unique_csv() -> bytes:
    n = next(_seq)
    rows = ['hello', 'world', 'foo', 'bar', 'baz', f'unique-row-{n}']
    return ('x\n' + '\n'.join(rows) + '\n').encode()


def _drain_outbox() -> None:
    """把 pending 事件全部派发掉并标记 published,让后续观察只属于本用例。"""
    OutboxRelay(repo=repository, publisher=lambda *_: None).publish_pending()
    assert repository.list_pending_outbox() == []


def _make_error_run() -> str:
    """上传→治理→建 run(留 queued),再就地推到 error:被测的是 retry,不是错误路径。"""
    r = client.post('/api/v1/projects/p/datasets',
                    files={'file': (f'a-{next(_seq)}.csv', _unique_csv())},
                    data={'consent': 'true'})
    assert r.status_code == 201, r.text
    did = r.json()['id']
    assert client.post(f'/api/v1/projects/p/datasets/{did}/validate', json={}).status_code == 202
    r = client.post('/api/v1/projects/p/analyses', json={'dataset_ids': [did]})
    assert r.status_code == 202
    aid = r.json()['id']
    analyses[aid].update(status='error', stage='error', error='boom')
    return aid


def _retry_events():
    return [e for e in repository.list_pending_outbox()
            if e.get('event_type') == 'analysis.retry']


def test_retry_leaves_a_relay_dispatchable_event(monkeypatch):
    monkeypatch.delenv('RUN_WORKER_INLINE', raising=False)
    aid = _make_error_run()
    _drain_outbox()

    response = client.post(f'/api/v1/projects/p/analyses/{aid}/retry')
    assert response.status_code == 200
    assert response.json()['status'] == 'queued'

    # retry 必须落事件:没有这一条,relay 无从派发,run 就停在 queued(原缺陷)。
    events = _retry_events()
    assert [e['payload'].get('analysis_id') for e in events] == [aid]

    # relay 认识这种事件:用记录型 publisher 证明真的派发了,且派发后不再 pending。
    dispatched = []
    OutboxRelay(repo=repository, publisher=dispatched.append).publish_pending()
    assert dispatched == [aid]
    assert _retry_events() == []


def test_repeated_retries_use_fresh_event_keys(monkeypatch):
    """outbox_events.event_key 有唯一约束:两次重试必须两把不同的钥匙。"""
    monkeypatch.delenv('RUN_WORKER_INLINE', raising=False)
    aid = _make_error_run()
    _drain_outbox()

    client.post(f'/api/v1/projects/p/analyses/{aid}/retry')
    first = [e['event_key'] for e in _retry_events()]
    assert len(first) == 1

    analyses[aid].update(status='error', stage='error', error='boom-again')
    client.post(f'/api/v1/projects/p/analyses/{aid}/retry')
    second = [e['event_key'] for e in _retry_events()]
    assert len(second) == 2
    assert set(first).isdisjoint(second[1:])


def test_retry_runs_inline_when_configured(monkeypatch):
    """本地/测试路径(RUN_WORKER_INLINE):retry 同步执行到终态,不留待派发事件。"""
    monkeypatch.setenv('RUN_WORKER_INLINE', '1')
    aid = _make_error_run()
    _drain_outbox()

    response = client.post(f'/api/v1/projects/p/analyses/{aid}/retry')
    assert response.status_code == 200
    assert response.json()['status'] == 'done'
    assert _retry_events() == []


def test_retry_rejects_non_retryable_states():
    """只有 error/cancelled 可重试;queued 状态重试应 409(此前零覆盖)。"""
    aid = _make_error_run()
    # _make_error_run 建出的 run 被推到 error 前是 queued——这里重建一个并保持 queued。
    r = client.post('/api/v1/projects/p/datasets',
                    files={'file': (f'b-{next(_seq)}.csv', _unique_csv())},
                    data={'consent': 'true'})
    did = r.json()['id']
    client.post(f'/api/v1/projects/p/datasets/{did}/validate', json={})
    r = client.post('/api/v1/projects/p/analyses', json={'dataset_ids': [did]})
    queued_id = r.json()['id']
    assert analyses[queued_id].get('status') == 'queued'

    response = client.post(f'/api/v1/projects/p/analyses/{queued_id}/retry')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'analysis_not_retryable'
    assert aid  # 上面那个 error run 只用于对照存在,防止误删变量
