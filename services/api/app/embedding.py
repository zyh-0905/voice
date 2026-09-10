"""W07 CPU 向量:离线确定性特征哈希嵌入。

不下载网络模型,编码只依赖锁定配置(EMBEDDING_REVISION);
同一输入在任何进程得到同一向量,行与输入一一对应,L2 归一化 float32。
后续可整体替换为本地预训练模型,revision 保证可追溯。
"""
from __future__ import annotations

import hashlib

import numpy as np

EMBEDDING_REVISION = 'hashing-ngram-v1:dim=256'
EMBEDDING_DIM = 256
_NGRAM_MIN, _NGRAM_MAX = 1, 3


def _bucket(token: str) -> int:
    digest = hashlib.md5(f'0:{token}'.encode('utf-8')).digest()
    return int.from_bytes(digest[:4], 'big') % EMBEDDING_DIM


def _sign(token: str) -> float:
    digest = hashlib.md5(f'1:{token}'.encode('utf-8')).digest()
    return 1.0 if digest[4] & 1 else -1.0


def _ngrams(text: str):
    for n in range(_NGRAM_MIN, _NGRAM_MAX + 1):
        for i in range(len(text) - n + 1):
            yield text[i:i + n]


def encode_segments(texts: list[str]) -> np.ndarray:
    """返回 shape=(len(texts), EMBEDDING_DIM) 的 L2 归一化 float32 矩阵。

    空文本对应全零行;行 i 对应输入 texts[i],一一对应不重排。
    """
    matrix = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
    for row, text in enumerate(texts):
        if not text:
            continue
        vector = matrix[row]
        for gram in _ngrams(text):
            vector[_bucket(gram)] += _sign(gram)
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        matrix[row] = vector
    return matrix
