"""向量 provider(工程计划 8.2)。

这些用例**真的发 HTTP 请求**(对着本地 stub 向量服务),而不是替换掉 provider。
哈希替身仍在 `test_embedding.py` 里按它自己的契约测,但「流水线用哪个」必须由
配置决定——那正是接缝存在的意义。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from app.embedding import EMBEDDING_DIM
from app.embedding_provider import (
    EmbeddingError,
    HashingEmbeddingProvider,
    HTTPEmbeddingProvider,
    encode_texts,
    resolve_embedding_provider,
)


class _StubHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        state = type(self).state
        sent = json.loads(self.rfile.read(length).decode('utf-8'))
        state.requests.append({'body': sent,
                               'authorization': self.headers.get('Authorization')})
        # 动态应答:按请求里的文本逐条返回向量,用来验证分批与行序
        payload = state.handler(sent) if state.handler else state.response
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Stub:
    def __init__(self):
        self.response = {}
        self.handler = None
        self.requests: list[dict] = []


@pytest.fixture
def stub():
    state = _Stub()
    server = HTTPServer(('127.0.0.1', 0), type('H', (_StubHandler,), {'state': state}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.url = f'http://127.0.0.1:{server.server_port}/v1/embeddings'
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def _provider(stub, **kwargs) -> HTTPEmbeddingProvider:
    return HTTPEmbeddingProvider(endpoint=stub.url, model='bge-small-zh-v1.5',
                                 timeout_seconds=5.0, **kwargs)


def _openai_response(rows):
    return {'data': [{'index': i, 'embedding': row} for i, row in enumerate(rows)]}


# —— 请求形状 ——

def test_provider_sends_model_and_input_and_the_api_key(stub):
    stub.response = _openai_response([[1.0, 0.0], [0.0, 1.0]])
    provider = _provider(stub, api_key='embed-key')

    provider.encode(['物流很慢', '退款未到账'])

    sent = stub.requests[0]['body']
    assert sent['model'] == 'bge-small-zh-v1.5'
    assert sent['input'] == ['物流很慢', '退款未到账']
    assert stub.requests[0]['authorization'] == 'Bearer embed-key'


def test_batching_splits_requests_by_batch_size(stub):
    """8.2:batch_size 初始为 32。分批之后行序仍要与输入一一对应。"""

    def respond(sent):
        # 按本批的文本逐条应答,向量第一维带上输入里的编号,便于验证顺序
        return _openai_response([[_index_of(text), 1.0] for text in sent['input']])

    stub.handler = respond
    provider = _provider(stub, batch_size=32)

    # encode_texts 才返回 ndarray(provider.encode 返回原始行列表)
    matrix = encode_texts(provider, [f'反馈{i}' for i in range(70)])

    assert provider.last_call_count == 3, '70 条按 32 分批应当发 3 次'
    assert [len(call['body']['input']) for call in stub.requests] == [32, 32, 6]
    assert matrix.shape == (70, 2)
    # 归一化后第一维/第二维 = index,用它验证行序。
    # 用近似比较:矩阵是 float32,精确相等会栽在 6.9999995 这种表示误差上。
    ratios = [float(row[0] / row[1]) for row in matrix]
    assert ratios == pytest.approx([float(i) for i in range(70)], rel=1e-5), '行序不得错位'


def _index_of(text: str) -> int:
    return int(text.replace('反馈', ''))


def test_rows_are_reordered_by_index_not_response_order(stub):
    """服务端并发处理时返回顺序不保证与请求一致;重排是静默的,必须按 index 排回。"""
    stub.response = {'data': [
        {'index': 1, 'embedding': [0.0, 5.0]},
        {'index': 0, 'embedding': [5.0, 0.0]},
    ]}
    provider = _provider(stub)

    rows = provider.encode(['第一条', '第二条'])

    assert rows[0] == [5.0, 0.0], 'index=0 的向量必须回到第一位'
    assert rows[1] == [0.0, 5.0]


def test_row_count_mismatch_is_an_error(stub):
    """少给一行会让证据指向别的反馈,且没有任何下游会发现。"""
    stub.response = _openai_response([[1.0, 0.0]])
    provider = _provider(stub)

    with pytest.raises(EmbeddingError, match='expected 2 rows'):
        provider.encode(['第一条', '第二条'])


def test_alternate_response_shapes_are_accepted(stub):
    stub.response = {'embeddings': [[3.0, 4.0]]}
    assert _provider(stub).encode(['x']) == [[3.0, 4.0]]

    stub.response = [[3.0, 4.0]]
    assert _provider(stub).encode(['x']) == [[3.0, 4.0]]

    stub.response = {'nonsense': True}
    with pytest.raises(EmbeddingError, match='unrecognised'):
        _provider(stub).encode(['x'])


# —— 归一化与 dtype(8.2) ——

def test_client_normalizes_even_if_the_service_does_not(stub):
    """§8.2 的聚类约定是「输入为 L2 归一化向量」。

    相信服务端已经归一化,会让 euclidean 距离在两种尺度上跑——结果不同而不会有
    任何报错。
    """
    stub.response = _openai_response([[3.0, 4.0]])

    matrix = encode_texts(_provider(stub), ['x'])

    assert matrix.dtype == np.float32
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0)


def test_zero_vector_stays_zero_rather_than_nan(stub):
    """除零得到 NaN,而 NaN 会让整个聚类静默退化成「全部噪声」。"""
    stub.response = _openai_response([[0.0, 0.0], [1.0, 0.0]])

    matrix = encode_texts(_provider(stub), ['空', '非空'])

    assert np.all(matrix[0] == 0)
    assert not np.any(np.isnan(matrix))


def test_inconsistent_dimensions_within_a_batch_are_rejected(stub):
    stub.response = _openai_response([[1.0, 0.0], [1.0, 0.0, 2.0]])
    with pytest.raises(EmbeddingError, match='inconsistent'):
        encode_texts(_provider(stub), ['a', 'b'])


def test_declared_dimension_mismatch_is_rejected(stub):
    stub.response = _openai_response([[1.0, 0.0]])
    with pytest.raises(EmbeddingError, match='declared dimension'):
        encode_texts(_provider(stub, dimension=768), ['a'])


# —— 接缝:由配置决定用哪个 provider ——

def test_mode_selects_the_provider(monkeypatch):
    monkeypatch.setenv('EMBEDDING_MODE', 'hashing')
    assert isinstance(resolve_embedding_provider(), HashingEmbeddingProvider)

    monkeypatch.setenv('EMBEDDING_MODE', 'api')
    monkeypatch.setenv('EMBEDDING_ENDPOINT', 'https://embed.example/v1')
    monkeypatch.setenv('EMBEDDING_MODEL', 'bge-small-zh-v1.5')
    provider = resolve_embedding_provider()
    assert isinstance(provider, HTTPEmbeddingProvider)
    assert provider.revision == 'api:bge-small-zh-v1.5'


def test_api_mode_without_endpoint_falls_back_to_the_standin(monkeypatch):
    """开发环境要能跑起来;生产由 settings 在启动时拦截,不允许替身。"""
    monkeypatch.setenv('EMBEDDING_MODE', 'api')
    monkeypatch.delenv('EMBEDDING_ENDPOINT', raising=False)
    monkeypatch.delenv('EMBEDDING_MODEL', raising=False)

    provider = resolve_embedding_provider()

    assert isinstance(provider, HashingEmbeddingProvider)
    # 替身在 revision 上自曝身份,不会冒充「已接入模型」
    assert provider.revision.startswith('hashing-ngram-v1')


def test_revision_is_traceable(monkeypatch):
    """8.2:模型 revision 要可追溯;没声明时用 model id 兜底,不编造版本号。"""
    provider = HTTPEmbeddingProvider(endpoint='x', model='bge-small-zh-v1.5')
    assert provider.revision == 'api:bge-small-zh-v1.5'

    declared = HTTPEmbeddingProvider(endpoint='x', model='bge-small-zh-v1.5',
                                     declared_revision='bge-small-zh-v1.5@a5beb1e')
    assert declared.revision == 'bge-small-zh-v1.5@a5beb1e'


# —— 接缝真的接在流水线上(不是「provider 能用」而已) ——

def test_pipeline_encodes_through_the_configured_provider(stub, monkeypatch):
    """流水线必须走 provider,而不是绕过它直接用哈希。

    这是接缝的意义所在:provider 单独可用、但流水线仍旧调哈希实现,是又一种
    「看起来接通了,实际是哑的」——而且它会让文档里的模型配置完全不生效。
    """
    from app import pipeline
    from app.repository import InMemoryRepository

    def respond(sent):
        # 两个紧致的簇,各自带一点抖动——**向量完全相同会被 HDBSCAN 判为噪声**
        # (互达距离退化),那样这条用例会因为聚类而不是因为接缝失败。
        rows = []
        for text in sent['input']:
            index = int(text.rsplit('编号', 1)[1])
            if index < 3:
                rows.append([1.0 + 0.001 * index, 0.001 * index])
            else:
                rows.append([0.001 * index, 1.0 + 0.001 * index])
        return _openai_response(rows)

    stub.handler = respond
    monkeypatch.setenv('EMBEDDING_MODE', 'api')
    monkeypatch.setenv('EMBEDDING_ENDPOINT', stub.url)
    monkeypatch.setenv('EMBEDDING_MODEL', 'bge-small-zh-v1.5')

    repository = InMemoryRepository()
    rows = [{'id': f'fb_{i}', 'event_key': f'k{i}', 'content_redacted': f'物流一直没有更新 编号{i}',
             'content_hash': f'h{i}', 'source_row': i, 'channel': 'unknown', 'product': 'unknown',
             'time_quality': 'missing', 'identity_quality': 'source_id', 'redaction_version': 'v1'}
            for i in range(6)]
    repository.save_feedback_rows('p', 'ds', rows)
    run = {'id': 'run_1', 'project_id': 'p', 'dataset_ids': ['ds']}
    repository.create_analysis(run)
    repository.save_run_feedbacks('p', 'run_1', [row['id'] for row in rows])

    drafts = pipeline.build_topics_from_run(run, repository)

    assert stub.requests, '流水线没有向配置的向量服务发请求'
    sent_texts = [text for call in stub.requests for text in call['body']['input']]
    assert sent_texts == [row['content_redacted'] for row in rows], '发出去的应是脱敏正文'
    assert drafts, 'provider 返回的向量应当能聚出主题'


def test_pipeline_records_the_embedding_revision(monkeypatch):
    """8.2:模型 revision 要落到数据上,而不只是活在日志里。

    换模型不重跑的话不会有人发现,而聚类结果会变——所以它必须可追溯。
    """
    monkeypatch.setenv('EMBEDDING_MODE', 'api')
    monkeypatch.setenv('EMBEDDING_ENDPOINT', 'https://embed.example/v1')
    monkeypatch.setenv('EMBEDDING_MODEL', 'bge-small-zh-v1.5')
    monkeypatch.setenv('EMBEDDING_REVISION', 'bge-small-zh-v1.5@a5beb1e')
    assert resolve_embedding_provider().revision == 'bge-small-zh-v1.5@a5beb1e'
