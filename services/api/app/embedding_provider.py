"""向量 provider(工程计划 8.2 的接入点)。

计划冻结的是 `BAAI/bge-small-zh-v1.5` 的**本地 CPU** 模型(「模型启动预加载」、
「模型文件作为部署前置缓存」)。本模块把它做成一个**接缝**:

- `HTTPEmbeddingProvider` —— 用户自行配置 endpoint 与 key 的远端向量服务;
- `HashingEmbeddingProvider` —— 原有的哈希替身,只作开发/演示用,生产禁止。

这样「用哪个模型」由配置决定,而不是编进流水线。要换回计划里的本地模型时,只需
按同一个 `EmbeddingProvider` 协议再加一个实现,流水线与聚类都不用动。

**必须说清的一处规格偏离:** §8.2 选本地 CPU 有一个未写明但真实的效果——脱敏正文
不出机器。改用远端 API 意味着正文要外发给第三方服务。计划 §10.2 要求「真实数据
外发前先确认条件」,所以这不是一个纯技术替换,部署方需要先确认这条。代码里把它
做成显式配置,不设默认指向外部的路径。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol, Sequence
from urllib import error, request

import numpy as np

from .embedding import EMBEDDING_DIM, EMBEDDING_REVISION, encode_segments

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_BATCH_SIZE = 32  # 8.2:CPU batch_size 初始为 32


class EmbeddingError(RuntimeError):
    """向量服务返回了不可用的结果。"""


class EmbeddingProvider(Protocol):
    """把一批文本编码成向量行。

    实现必须保证**行与输入一一对应且不重排**——聚类只拿到矩阵,行序错了不会有
    任何报错,只会让主题的证据指向别的反馈。
    """

    revision: str
    dimension: int | None

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass
class HashingEmbeddingProvider:
    """本地哈希替身(离线、确定性),仅开发与演示。

    `revision` 与旧实现一致,便于历史数据对得上;生产环境由 settings 拦截。
    """

    revision: str = EMBEDDING_REVISION
    dimension: int | None = EMBEDDING_DIM

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return encode_segments(list(texts)).tolist()


@dataclass
class HTTPEmbeddingProvider:
    """远端向量服务。

    请求体按 OpenAI embeddings 的形状(`model` + `input`),响应支持三种常见形状:
    `data[].embedding`、`embeddings[][]`、裸二维数组。**带 `index` 时按 index 排回
    输入顺序**——服务端并发处理时返回顺序不保证与请求一致,而重排是静默的。
    """

    endpoint: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    batch_size: int = DEFAULT_BATCH_SIZE
    dimension: int | None = None
    declared_revision: str | None = None
    last_call_count: int = 0

    @property
    def revision(self) -> str:
        """8.2 要求模型 revision 可追溯;未声明时用 model id 兜底,不编造版本号。"""
        return self.declared_revision or f'api:{self.model}'

    @classmethod
    def from_env(cls) -> 'HTTPEmbeddingProvider | None':
        endpoint = (os.getenv('EMBEDDING_ENDPOINT') or '').strip()
        model = (os.getenv('EMBEDDING_MODEL') or '').strip()
        if not endpoint or not model:
            return None
        return cls(
            endpoint=endpoint, model=model,
            api_key=(os.getenv('EMBEDDING_API_KEY') or '').strip() or None,
            timeout_seconds=_float_env('EMBEDDING_TIMEOUT_SECONDS', DEFAULT_TIMEOUT_SECONDS),
            batch_size=int(_float_env('EMBEDDING_BATCH_SIZE', DEFAULT_BATCH_SIZE)),
            declared_revision=(os.getenv('EMBEDDING_REVISION') or '').strip() or None,
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        self.last_call_count = 0
        for start in range(0, len(texts), max(1, self.batch_size)):
            chunk = list(texts[start:start + max(1, self.batch_size)])
            vectors.extend(self._encode_batch(chunk))
            self.last_call_count += 1
        return vectors

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({'model': self.model, 'input': texts,
                              'encoding_format': 'float'}).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        try:
            with request.urlopen(
                request.Request(self.endpoint, data=payload, headers=headers, method='POST'),
                timeout=self.timeout_seconds,
            ) as response:
                body = json.loads(response.read().decode('utf-8'))
        except error.URLError as exc:
            raise EmbeddingError(f'embedding request failed: {exc}') from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingError('embedding service returned non-JSON body') from exc

        rows = _extract_vectors(body)
        if len(rows) != len(texts):
            # 少给或多给一行都必须报错:错位不会被任何下游发现,只会让主题的证据
            # 指向别的反馈。
            raise EmbeddingError(
                f'expected {len(texts)} rows, got {len(rows)}')
        return rows


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


def _extract_vectors(body: object) -> list[list[float]]:
    """取出向量行;带 index 时按 index 排回输入顺序。"""
    if isinstance(body, dict):
        data = body.get('data')
        if isinstance(data, list):
            indexed = []
            for position, item in enumerate(data):
                if not isinstance(item, dict) or not isinstance(item.get('embedding'), list):
                    raise EmbeddingError('data[].embedding must be a list of numbers')
                index = item.get('index')
                indexed.append((int(index) if isinstance(index, int) else position,
                                [float(value) for value in item['embedding']]))
            indexed.sort(key=lambda pair: pair[0])
            return [row for _index, row in indexed]
        embedded = body.get('embeddings')
        if isinstance(embedded, list):
            return [[float(value) for value in row] for row in embedded]
    if isinstance(body, list) and all(isinstance(row, list) for row in body):
        return [[float(value) for value in row] for row in body]
    raise EmbeddingError('unrecognised embedding response shape')


def resolve_embedding_provider() -> EmbeddingProvider:
    """按 EMBEDDING_MODE 选 provider;缺配置时退回哈希替身并让配置可见。

    没有 `local` 档:计划要的本地模型需要一个重量级依赖,而那是一个部署决策
    (镜像体积、预缓存)。接缝已经就位,补一个实现即可,不必现在假装它存在。
    """
    mode = (os.getenv('EMBEDDING_MODE') or 'hashing').strip().lower()
    if mode == 'api':
        provider = HTTPEmbeddingProvider.from_env()
        if provider is not None:
            return provider
        # 说了用 api 却没配端点:退回替身,但生产环境由 settings 在启动时拦截——
        # 这里不抛异常是因为开发环境需要能跑起来,而替身会在 revision 上自曝身份。
        return HashingEmbeddingProvider()
    return HashingEmbeddingProvider()


def encode_texts(provider: EmbeddingProvider, texts: Sequence[str]) -> np.ndarray:
    """编码成 shape=(len(texts), dim) 的 **L2 归一化 float32** 矩阵。

    归一化在客户端做,而不是相信服务端已经归一化:§8.2 的聚类约定是「输入为 L2
    归一化向量」,服务端是否归一化是实现细节,不检查就变成 HDBSCAN 的 euclidean
    距离在两种尺度上跑——结果不同而不会有任何报错。对已归一化的向量是幂等的。
    """
    rows = provider.encode(list(texts))
    if not rows:
        return np.zeros((0, provider.dimension or 0), dtype=np.float32)

    widths = {len(row) for row in rows}
    if len(widths) != 1:
        raise EmbeddingError(f'inconsistent vector dimensions within one batch: {sorted(widths)}')
    width = widths.pop()
    if provider.dimension is not None and width != provider.dimension:
        raise EmbeddingError(
            f'provider declared dimension {provider.dimension} but returned {width}')

    matrix = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # 零向量保持为零行(与哈希实现一致):除零会得到 NaN,而 NaN 会让整个聚类
    # 静默退化成「全部噪声」。
    np.divide(matrix, norms, out=matrix, where=norms > 0)
    return matrix
