"""W09 真实聚类:固定输入可重现;噪声(离群)保留为待归类,不按预标签回填主题。

使用 hdbscan 真实算法(min_cluster_size/min_samples 由 config 传入);
向量校验拒绝 NaN/无限值与非二维输入;空输入返回空结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, eq=False)
class ClusterResult:
    labels: np.ndarray          # 与输入行一一对应,-1 表示噪声/待归类
    noise_indices: frozenset[int]
    method: str
    config: dict = field(default_factory=dict)


def _validate(vectors) -> np.ndarray:
    if not isinstance(vectors, np.ndarray):
        vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2:
        raise ValueError('vectors must be a 2D array')
    if vectors.dtype.kind != 'f':
        vectors = vectors.astype(np.float32)
    if not np.isfinite(vectors).all():
        raise ValueError('vectors must not contain NaN or infinite values')
    return vectors


def cluster_embeddings(vectors, method: str = 'hdbscan', config: dict | None = None) -> ClusterResult:
    """按 method 聚类;labels[i] 为 vectors[i] 的簇标签,噪声为 -1。"""
    cfg = dict(config or {})
    vectors = _validate(vectors)
    if method != 'hdbscan':
        raise ValueError(f'unsupported clustering method: {method}')
    if vectors.shape[0] == 0:
        return ClusterResult(
            labels=np.empty(0, dtype=int),
            noise_indices=frozenset(),
            method=method,
            config=cfg,
        )
    # 样本不足(<2 无法聚类):全部保留为待归类,不产生簇
    if vectors.shape[0] < 2:
        return ClusterResult(
            labels=np.full(vectors.shape[0], -1, dtype=int),
            noise_indices=frozenset(range(vectors.shape[0])),
            method=method,
            config=cfg,
        )
    # scikit-learn >=1.3 内置 HDBSCAN,参数语义与 hdbscan 包一致;
    # 惰性导入,未安装时仅聚类路径报错
    from sklearn.cluster import HDBSCAN
    clusterer = HDBSCAN(
        min_cluster_size=int(cfg.get('min_cluster_size', 5)),
        min_samples=int(cfg.get('min_samples', 3)),
        metric='euclidean',
    )
    labels = np.asarray(clusterer.fit_predict(vectors), dtype=int)
    noise = frozenset(int(i) for i in np.flatnonzero(labels == -1))
    return ClusterResult(labels=labels, noise_indices=noise, method=method, config=cfg)
