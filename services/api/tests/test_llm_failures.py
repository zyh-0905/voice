"""W10 降级契约:非法 JSON/缺字段、一次修复、超时、预算耗尽、manual 模式、origin 记录。"""
import pytest

from app.llm import (
    FALLBACK_TOPIC_NAME,
    BudgetExceededError,
    LLMTimeoutError,
    MockTopicProvider,
    TopicNamer,
)


@pytest.fixture
def evidence():
    return [
        {'evidence_id': 'fb_1', 'text': '物流信息一直没有更新,等待了三天。'},
        {'evidence_id': 'fb_2', 'text': '申请退款后,希望看到预计到账时间。'},
    ]


@pytest.fixture
def allowed(evidence):
    return {row['evidence_id']: row['text'] for row in evidence}


def test_invalid_json_degrades_to_rule_fallback(evidence, allowed):
    class BrokenProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            return '{not valid json'

    namer = TopicNamer(BrokenProvider(), allowed)
    candidate = namer.name_topic(evidence)
    assert candidate.origin == 'rule_fallback'
    assert candidate.topic_name == FALLBACK_TOPIC_NAME
    assert candidate.needs_review is True
    assert candidate.claims == []


def test_missing_fields_degrades(evidence, allowed):
    class BadSchemaProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            return {'topic_name': '只有名字'}

    namer = TopicNamer(BadSchemaProvider(), allowed)
    candidate = namer.name_topic(evidence)
    assert candidate.origin == 'rule_fallback'
    assert any('契约' in line for line in candidate.limitations)


def test_single_invalid_claim_repaired_once(evidence, allowed):
    class MostlyGoodProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            return {
                'topic_name': '物流体验', 'summary': 's', 'severity': 'medium', 'department': '',
                'evidence_ids': ['fb_1', 'fb_2'],
                'claims': [
                    {'evidence_id': 'fb_1', 'quote': '物流信息一直没有更新', 'claim': '物流延迟'},
                    {'evidence_id': 'fb_foreign', 'quote': '编造的引用', 'claim': 'x'},
                ],
                'suggested_action': '', 'needs_review': True, 'limitations': [],
            }

    namer = TopicNamer(MostlyGoodProvider(), allowed)
    candidate = namer.name_topic(evidence)
    assert candidate.origin == 'provider'
    assert candidate.topic_name == '物流体验'
    assert len(candidate.claims) == 1


def test_unrepairable_evidence_list_degrades(evidence, allowed):
    class ForeignEvidenceProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            return {
                'topic_name': '物流体验', 'summary': 's', 'severity': 'medium', 'department': '',
                'evidence_ids': ['fb_foreign'],
                'claims': [],
                'suggested_action': '', 'needs_review': True, 'limitations': [],
            }

    namer = TopicNamer(ForeignEvidenceProvider(), allowed)
    candidate = namer.name_topic(evidence)
    assert candidate.origin == 'rule_fallback'
    assert candidate.topic_name == FALLBACK_TOPIC_NAME


def test_timeout_degrades(evidence, allowed):
    class SlowProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            raise LLMTimeoutError('provider timed out')

    namer = TopicNamer(SlowProvider(), allowed)
    candidate = namer.name_topic(evidence)
    assert candidate.origin == 'rule_fallback'
    assert any('LLMTimeoutError' in line for line in candidate.limitations)


def test_budget_exhausted_degrades(evidence, allowed):
    class ExpensiveProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            raise BudgetExceededError('budget exhausted')

    candidate = TopicNamer(ExpensiveProvider(), allowed).name_topic(evidence)
    assert candidate.origin == 'rule_fallback'
    assert candidate.topic_name == FALLBACK_TOPIC_NAME


def test_mock_provider_records_origin_and_valid_quotes(evidence, allowed):
    candidate = TopicNamer(MockTopicProvider(), allowed).name_topic(evidence)
    assert candidate.origin == 'mock'
    assert candidate.topic_name == '物流体验'
    assert candidate.claims


def test_manual_mode_skips_provider(evidence, allowed):
    calls = []

    class CountingProvider:
        origin = 'provider'

        def name_topic(self, evidence, context):
            calls.append(1)
            raise LLMTimeoutError('should not be called')

    namer = TopicNamer(CountingProvider(), allowed, naming_mode='manual')
    candidate = namer.name_topic(evidence)
    assert calls == []
    assert candidate.origin == 'rule_fallback'
    assert candidate.topic_name == FALLBACK_TOPIC_NAME
