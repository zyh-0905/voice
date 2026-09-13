"""真实主题命名 provider(工程计划 8.5 / 10.5)。

这是命名阶段真正对接外部模型的地方。此前 `llm_provider.HTTPStructuredProvider`
零调用方、流水线恒用 mock 命名——「可替换的结构化 provider」是一句注释,不是一条
能走通的路径。本模块实现的是 `llm.TopicProvider` 契约(命名阶段),而不是那套
已经死掉的 `analyze(rows)` 契约。

三条硬约束来自计划:

- 8.5:只用冻结的提示词与 `contracts/llm_topic.schema.json`;输出先过 schema,
  再验证据引用。本模块只负责取回原始输出,校验在调用方。
- 8.5:反馈正文是不可信数据,不具有修改系统指令的权限——所以正文作为**数据**放在
  结构化字段里,提示词单独作为 system,不拼接成一段自由文本。
- 10.5:单调用超时 30 秒;没有可靠价格配置时禁用付费模式,而不是默认为免费。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Mapping, Sequence
from urllib import error, request

# 超时与预算的异常放在这里定义,`llm` 再导出:provider 要抛它们,
# 而 `llm` 要知道怎么接——两边各定义一份的话,`except` 会漏接。
class LLMTimeoutError(RuntimeError):
    """供应商超时(10.5:单调用 30 秒)。"""


class BudgetExceededError(RuntimeError):
    """预算耗尽;调用前预留失败,不发起请求。"""


DEFAULT_TIMEOUT_SECONDS = 30.0
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'topic_v1.txt')


def load_system_prompt() -> str:
    """读冻结的提示词文件。

    不内联一份副本:提示词是发布版本的一部分(8.5 要求记录提示模板版本),
    内联之后改文件不会生效,而没人会发现。
    """
    with open(_PROMPT_PATH, encoding='utf-8') as handle:
        return handle.read().strip()


@dataclass
class CallUsage:
    """一次调用的记账信息,供 `model_calls` 落库(10.5)。"""

    provider: str
    model: str | None = None
    state: str = 'SUCCESS'
    tokens_in: int | None = None
    tokens_out: int | None = None
    provider_request_id: str | None = None
    cost_estimated: float | None = None
    cost_actual: float | None = None


@dataclass
class BudgetGuard:
    """每日/项目预算(10.5)。

    `paid_enabled` 是关键的那条:没有可靠价格配置时**禁用付费模式**,而不是默认
    为免费——后者会让一个没配价格的部署悄悄花钱,而且事后算不出花了多少。
    """

    daily_limit: float | None = None
    price_in: float | None = None
    price_out: float | None = None

    @classmethod
    def from_env(cls) -> 'BudgetGuard':
        def _float(name: str) -> float | None:
            raw = os.getenv(name)
            if raw is None or not raw.strip():
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        return cls(daily_limit=_float('DAILY_MODEL_BUDGET'),
                   price_in=_float('MODEL_PRICE_IN'),
                   price_out=_float('MODEL_PRICE_OUT'))

    @property
    def paid_enabled(self) -> bool:
        return self.price_in is not None and self.price_out is not None

    def estimate(self, tokens_in: int | None, tokens_out: int | None) -> float | None:
        if not self.paid_enabled:
            return None
        if tokens_in is None and tokens_out is None:
            # 供应商没报用量时算不出费用。返回 0.0 会让「免费」和「不知道多少钱」
            # 看起来一样,而预算判断正依赖这个区别(10.5)。
            return None
        return ((tokens_in or 0) * float(self.price_in)
                + (tokens_out or 0) * float(self.price_out))

    def check(self, spent_today: float | None) -> None:
        """调用前预留:超限即拒绝,不发请求。"""
        if self.daily_limit is None:
            return
        if (spent_today or 0.0) >= self.daily_limit:
            raise BudgetExceededError(
                f'每日预算已用尽({spent_today:.6f} >= {self.daily_limit})')


@dataclass
class HTTPTopicProvider:
    """向外部模型请求一次主题命名;输出原样返回,由调用方按 schema 校验。

    `last_usage` 在每次调用后更新——包括失败的那次。10.5 要求 UNKNOWN 调用也有
    记录:只统计成功调用的话,预算会低估超时与结构失败重试掉的那些钱。
    """

    endpoint: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    origin: str = 'provider'
    budget: BudgetGuard = field(default_factory=BudgetGuard)
    system_prompt: str = field(default_factory=load_system_prompt)
    last_usage: CallUsage | None = None

    @classmethod
    def from_env(cls) -> 'HTTPTopicProvider | None':
        """按 14.1 的配置键构造;缺必要项返回 None(调用方据此判断能否走付费模式)。"""
        endpoint = (os.getenv('MODEL_ENDPOINT') or '').strip()
        model = (os.getenv('MODEL_ID') or '').strip()
        if not endpoint or not model:
            return None
        provider = (os.getenv('MODEL_PROVIDER') or 'http').strip() or 'http'
        try:
            timeout = float(os.getenv('MODEL_TIMEOUT_SECONDS') or DEFAULT_TIMEOUT_SECONDS)
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(endpoint=endpoint, model=model,
                   api_key=(os.getenv('MODEL_API_KEY') or '').strip() or None,
                   timeout_seconds=timeout, origin=provider,
                   budget=BudgetGuard.from_env())

    def name_topic(self, evidence: Sequence[Mapping[str, str]],
                   context: Mapping[str, object] | None = None) -> object:
        self.budget.check(float(context.get('spent_today') or 0.0) if context else 0.0)
        if not self.budget.paid_enabled:
            # 10.5:没有可靠价格配置时禁用付费模式。抛出去让调用方降级并记一笔,
            # 而不是「先调用、事后算不出来」。
            raise BudgetExceededError('未配置可靠价格,付费模式已禁用')
        payload = json.dumps({
            'model': self.model,
            # 提示词单独作为 system;证据是数据,不参与指令
            'system': self.system_prompt,
            'input': {
                'evidence': [{'evidence_id': str(row['evidence_id']),
                              'text': str(row['text'])} for row in evidence],
            },
            'response_format': 'json',
        }).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        self.last_usage = CallUsage(provider=self.origin, model=self.model)
        try:
            with request.urlopen(
                request.Request(self.endpoint, data=payload, headers=headers, method='POST'),
                timeout=self.timeout_seconds,
            ) as response:
                body = json.loads(response.read().decode('utf-8'))
        except TimeoutError as exc:
            self.last_usage.state = 'TIMEOUT'
            raise LLMTimeoutError(f'provider timed out after {self.timeout_seconds}s') from exc
        except error.URLError as exc:
            self.last_usage.state = 'ERROR'
            # socket 超时被 urlopen 包成 URLError;两者对调用方的含义相同
            if isinstance(getattr(exc, 'reason', None), TimeoutError):
                self.last_usage.state = 'TIMEOUT'
                raise LLMTimeoutError('provider timed out') from exc
            raise RuntimeError(f'provider request failed: {exc}') from exc
        except json.JSONDecodeError as exc:
            self.last_usage.state = 'INVALID_JSON'
            raise RuntimeError('provider returned non-JSON body') from exc

        self._record_usage(body)
        return _extract_candidate(body)

    def _record_usage(self, body: object) -> None:
        """把 usage 写进 last_usage;缺字段就留 None,不猜。"""
        if not isinstance(body, dict):
            return
        usage = body.get('usage') if isinstance(body.get('usage'), dict) else {}
        self.last_usage.tokens_in = _int_or_none(usage.get('prompt_tokens') or usage.get('input_tokens'))
        self.last_usage.tokens_out = _int_or_none(usage.get('completion_tokens') or usage.get('output_tokens'))
        self.last_usage.provider_request_id = str(body.get('id') or '') or None
        self.last_usage.cost_estimated = self.budget.estimate(
            self.last_usage.tokens_in, self.last_usage.tokens_out)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _extract_candidate(body: object) -> object:
    """从响应体取出待校验的候选。

    支持三种常见形状,顺序固定:显式 `output` 字段 → OpenAI 风格
    `choices[0].message.content`(内容本身是 JSON 字符串)→ 整个 body。
    最后一种兜底是给自建网关用的;形状不认识就让 schema 校验去拒绝,
    而不是在这里猜一个「看起来像主题」的对象出来。
    """
    if not isinstance(body, dict):
        return body
    if isinstance(body.get('output'), (dict, list)):
        return body['output']
    choices = body.get('choices')
    if isinstance(choices, list) and choices:
        message = choices[0].get('message') if isinstance(choices[0], dict) else None
        content = message.get('content') if isinstance(message, dict) else None
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
    return body
