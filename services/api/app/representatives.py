"""W09 代表选择:确定性策略,固定输入可重现,不依赖随机采样。"""
from __future__ import annotations

import numpy as np


def select_representatives(cluster_segments, vectors, limit: int = 8) -> list[str]:
    """按到质心的距离由近及远选择代表;距离并列按 segment_id 字典序裁定。

    cluster_segments[i] 对应 vectors[i] 行;返回选中的 segment_id 列表,
    数量不超过 limit 且不超过输入数。全零/全并列输入也确定可重现。
    """
    ids = [str(s) for s in cluster_segments]
    vectors = np.asarray(vectors, dtype=np.float32)
    if limit <= 0:
        return []
    if vectors.shape[0] != len(ids):
        raise ValueError('cluster_segments and vectors must have matching lengths')
    if vectors.shape[0] == 0:
        return []
    if vectors.ndim != 2:
        raise ValueError('vectors must be a 2D array')
    centroid = vectors.mean(axis=0)
    distances = np.linalg.norm(vectors - centroid, axis=1)
    order = sorted(range(len(ids)), key=lambda i: (float(distances[i]), ids[i]))
    return [ids[i] for i in order[:limit]]
