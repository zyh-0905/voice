"""真实主题命名 provider(工程计划 8.5 / 10.5)。

这些用例**真的发 HTTP 请求**(对着一个本地 stub 服务器),而不是替换掉 provider
本身。此前 `HTTPStructuredProvider` 零调用方、流水线恒用 mock 命名——那种「看起来
接通了」的状态,只有把请求真的发出去才能证伪。

stub 服务器同时充当反面教材:它可以返回坏 JSON、超时、或记录收到的请求体供断言。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import pytest

from app.llm import BudgetExceededError, LLMTimeoutError, MockTopicProvider, make_namer, resolve_naming_mode
from app.topic_provider import BudgetGuard, CallUsage, HTTPTopicProvider

VALID_CANDIDATE = {
    'topic_name': '退款进度',
    'summary': '反馈集中在退款到账时间与进度查询。',
    'severity': 'medium',
    'department': '客服',
    'evidence_ids': [],
    'claims': [],
    'suggested_action': '核对退款流程时效',
    'needs_review': True,
    'limitations': [],
}


class _StubHandler(BaseHTTPRequestHandler):
    """按脚本响应;把收到的请求体留在 `State.requests` 供断言。"""

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler 的接口)
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length).decode('utf-8')
        type(self).state.requests.append({
            'body': json.loads(raw),
            'authorization': self.headers.get('Authorization'),
        })
        script = type(self).state
        if script.mode == 'timeout':
            # 不响应也不关闭:让客户端自己超时
            import time
            time.sleep(script.timeout_seconds + 1.0)
            return
        payload = script.response
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静音:测试输出里不需要访问日志
        pass


class _Stub:
    def __init__(self):
        self.mode = 'ok'
        self.response = {}
        self.requests: list[dict] = []
        self.timeout_seconds = 1.0


@pytest.fixture
def stub():
    state = _Stub()
    handler = type('Handler', (_StubHandler,), {'state': state})
    server = HTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f'http://127.0.0.1:{server.server_port}/v1/name'
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def _provider(stub, **kwargs) -> HTTPTopicProvider:
    budget = kwargs.pop('budget', BudgetGuard(daily_limit=100.0, price_in=0.000001, price_out=0.000002))
    kwargs.setdefault('timeout_seconds', 1.0)
    return HTTPTopicProvider(endpoint=stub.url, model='stub-model', budget=budget, **kwargs)


EVIDENCE = [{'evidence_id': 'fb_1', 'text': '退款一直没有到账'},
            {'evidence_id': 'fb_2', 'text': '退款进度查询不清晰'}]


def _valid_response():
    return {**VALID_CANDIDATE, 'evidence_ids': ['fb_1'],
            'claims': [{'evidence_id': 'fb_1', 'quote': '退款一直没有到账', 'claim': '到账延迟'}]}


# —— 请求真的发出去,且形状符合 8.5 ——

def test_provider_sends_the_frozen_prompt_and_evidence_as_data(stub):
    """8.5:提示词单独作为 system;反馈正文是**数据**,不参与指令。"""
    stub.response = _valid_response()
    provider = _provider(stub, api_key='secret-key')

    output = provider.name_topic(EVIDENCE)

    assert len(stub.requests) == 1
    sent = stub.requests[0]['body']
    assert sent['model'] == 'stub-model'
    assert '仅返回符合 schema 的 JSON' in sent['system'], '必须使用冻结的提示词'
    assert sent['input']['evidence'] == EVIDENCE, '证据按结构化字段传,不拼进提示词'
    assert stub.requests[0]['authorization'] == 'Bearer secret-key'
    assert output['topic_name'] == '退款进度'


def test_provider_parses_openai_style_choices(stub):
    """常见网关把结构化输出放在 choices[0].message.content 里(内容本身是 JSON 串)。"""
    stub.response = {
        'id': 'req_123',
        'choices': [{'message': {'content': json.dumps(_valid_response())}}],
        'usage': {'prompt_tokens': 120, 'completion_tokens': 45},
    }
    provider = _provider(stub)

    output = provider.name_topic(EVIDENCE)

    assert output['topic_name'] == '退款进度'
    assert provider.last_usage.tokens_in == 120
    assert provider.last_usage.tokens_out == 45
    assert provider.last_usage.provider_request_id == 'req_123'
    # 有价格配置时按 tokens 估算:120*0.000001 + 45*0.000002
    assert provider.last_usage.cost_estimated == pytest.approx(0.00021)


# —— 8.5:输出契约与证据校验由调用方执行 ——

def test_invalid_schema_output_falls_back_and_records_the_call(stub):
    """结构失败是一次**真实发生**的调用:用量要记账,否则预算会低估重试开销。"""
    stub.response = {**VALID_CANDIDATE, 'topic_name': '', 'evidence_ids': []}
    namer = make_namer({'fb_1': '退款一直没有到账'}, spent_today=0.0)
    provider = _provider(stub)
    namer.provider = provider
    namer.naming_mode = 'provider'

    candidate = namer.name_topic([EVIDENCE[0]])

    assert candidate.origin == 'rule_fallback'
    assert namer.last_call.state == 'SCHEMA_INVALID'
    assert namer.last_call.provider == 'provider'


def test_fabricated_quote_never_survives(stub):
    """8.5:quote 必须是脱敏正文的精确子串。

    服务层允许修复一次(8.5「结构失败后修复重试一次」),所以「编造引用」的结果
    可能是丢掉坏 claim 后保留命名,也可能是整体降级——**两种都可接受**。
    真正的不变式是:结果里不能留下任何无法在原文中定位的引用。
    """
    text = '退款一直没有到账'
    stub.response = {**VALID_CANDIDATE, 'evidence_ids': ['fb_1'],
                     'claims': [{'evidence_id': 'fb_1', 'quote': '这句话不在原文里', 'claim': 'x'}]}
    namer = make_namer({'fb_1': text}, spent_today=0.0)
    namer.provider = _provider(stub)
    namer.naming_mode = 'provider'

    candidate = namer.name_topic([EVIDENCE[0]])

    for claim in candidate.claims:
        assert claim.quote in text, '引用必须是原文的精确子串'
    assert candidate.origin in ('rule_fallback', 'provider')
    assert namer.last_call.state in ('EVIDENCE_INVALID', 'SUCCESS')


def test_all_foreign_evidence_falls_back(stub):
    """整簇证据都不属于本 run 的输入:必须整体降级,不能保留模型编出来的 id。"""
    stub.response = {**VALID_CANDIDATE, 'evidence_ids': ['fb_ghost'],
                     'claims': [{'evidence_id': 'fb_ghost', 'quote': 'x', 'claim': 'y'}]}
    namer = make_namer({'fb_1': '退款一直没有到账'}, spent_today=0.0)
    namer.provider = _provider(stub)
    namer.naming_mode = 'provider'

    candidate = namer.name_topic([EVIDENCE[0]])

    assert candidate.origin == 'rule_fallback'
    assert namer.last_call.state == 'EVIDENCE_INVALID'
    assert candidate.claims == []


def test_timeout_is_recorded_as_a_timeout_not_a_success(stub):
    stub.mode = 'timeout'
    namer = make_namer({'fb_1': 'x'}, spent_today=0.0)
    namer.provider = _provider(stub, timeout_seconds=0.2)
    namer.naming_mode = 'provider'

    candidate = namer.name_topic([EVIDENCE[0]])

    assert candidate.origin == 'rule_fallback'
    assert namer.last_call.state == 'TIMEOUT'
    assert any('LLMTimeoutError' in line for line in candidate.limitations)


# —— 10.5:预算与付费模式 ——

def test_paid_mode_is_disabled_without_reliable_pricing(stub):
    """10.5:没有可靠价格配置时禁用付费模式,而不是默认为免费。

    关键是**一个请求都不发**——「先调用、事后算不出来」正是要避免的。
    """
    provider = _provider(stub, budget=BudgetGuard(daily_limit=100.0))

    with pytest.raises(BudgetExceededError, match='价格'):
        provider.name_topic(EVIDENCE)
    assert stub.requests == [], '付费模式禁用时不得发出请求'


def test_budget_is_checked_before_the_call(stub):
    """调用前预留:已用尽即拒绝,不发请求。"""
    provider = _provider(stub)

    with pytest.raises(BudgetExceededError, match='预算'):
        provider.name_topic(EVIDENCE, {'spent_today': 100.0})
    assert stub.requests == []


def test_missing_usage_leaves_cost_null_not_zero(stub):
    """供应商没报用量时算不出费用:留 None,不填 0。

    0 会让「免费」和「不知道多少钱」看起来一样,而预算判断依赖这个区别(10.5)。
    """
    stub.response = {'output': _valid_response()}  # 没有 usage 字段
    provider = _provider(stub)

    provider.name_topic(EVIDENCE, {'spent_today': 0.0})

    assert provider.last_usage.tokens_in is None
    assert provider.last_usage.cost_estimated is None


def test_pricing_with_usage_still_produces_an_estimate(stub):
    """配了价格且供应商报了用量时,估算费用才是可算的。"""
    stub.response = {'output': _valid_response(),
                     'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}
    provider = _provider(stub)

    provider.name_topic(EVIDENCE, {'spent_today': 0.0})

    assert provider.last_usage.tokens_in == 10
    assert provider.last_usage.cost_estimated == pytest.approx(10 * 0.000001 + 2 * 0.000002)


# —— 命名模式选择 ——

def test_make_namer_honours_naming_mode(monkeypatch):
    monkeypatch.setenv('NAMING_MODE', 'manual')
    assert resolve_naming_mode() == 'manual'
    namer = make_namer({'fb_1': 'x'})
    assert namer.naming_mode == 'manual'
    assert namer.name_topic([{'evidence_id': 'fb_1', 'text': 'x'}]).origin == 'rule_fallback'
    assert namer.last_call.state == 'SKIPPED_MANUAL'

    monkeypatch.setenv('NAMING_MODE', 'mock')
    assert make_namer({'fb_1': 'x'}).naming_mode == 'mock'

    # 未知值按 mock 处理,不悄悄当成 provider
    monkeypatch.setenv('NAMING_MODE', 'gpt')
    assert resolve_naming_mode() == 'mock'


def test_provider_mode_without_endpoint_degrades_to_manual(monkeypatch):
    """说了用 provider 却没配端点:降级为人工命名并记明原因,不用 mock 冒充已接入。"""
    monkeypatch.setenv('NAMING_MODE', 'provider')
    monkeypatch.delenv('MODEL_ENDPOINT', raising=False)
    monkeypatch.delenv('MODEL_ID', raising=False)

    namer = make_namer({'fb_1': 'x'})

    assert namer.naming_mode == 'manual'
    assert namer.last_call is None or namer.last_call.state != 'SUCCESS'


def test_mock_namer_never_claims_to_have_called_a_model():
    """mock 产出不是模型调用:state 必须说明,不能记成一次成功调用。

    `model_calls` 是预算与成本的口径来源;混进一批从未发生的「成功调用」会让
    这张表不再能回答「到底调了几次模型」。
    """
    namer = make_namer({'fb_1': '退款一直没有到账'})
    namer.naming_mode = 'mock'
    namer.last_call = None
    namer.name_topic([{'evidence_id': 'fb_1', 'text': '退款一直没有到账'}])
    assert namer.last_call.provider == 'mock'
    assert namer.last_call.state == 'MOCK', 'mock 产出不是模型调用,不能记成 SUCCESS'
