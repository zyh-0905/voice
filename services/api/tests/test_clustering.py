"""W09 聚类契约:样本不足全部待归类、NaN 拒绝、空输入、可重现、>24 簇不丢内容。"""
import numpy as np
import pytest

from app.clustering import cluster_embeddings


def test_too_few_segments_remain_unassigned():
    vectors = np.eye(3, dtype=np.float32)
    result = cluster_embeddings(vectors, 'hdbscan', {'min_cluster_size': 5, 'min_samples': 3})
    assert list(result.labels) == [-1, -1, -1]
    assert set(result.noise_indices) == {0, 1, 2}


def test_nan_and_infinite_rejected():
    with pytest.raises(ValueError, match='NaN'):
        cluster_embeddings(np.array([[1.0, np.nan]], dtype=np.float32))
    with pytest.raises(ValueError, match='NaN'):
        cluster_embeddings(np.array([[1.0, np.inf]], dtype=np.float32))


def test_non_2d_rejected():
    with pytest.raises(ValueError, match='2D'):
        cluster_embeddings(np.array([1.0, 2.0], dtype=np.float32))


def test_empty_vectors_returns_empty_result():
    result = cluster_embeddings(np.empty((0, 8), dtype=np.float32))
    assert len(result.labels) == 0
    assert result.noise_indices == set()


def test_obvious_blobs_separate():
    rng = np.random.default_rng(0)
    a = np.tile(np.array([0.0, 0.0], dtype=np.float32), (12, 1)) + rng.normal(0, 0.01, (12, 2)).astype(np.float32)
    b = np.tile(np.array([5.0, 5.0], dtype=np.float32), (12, 1)) + rng.normal(0, 0.01, (12, 2)).astype(np.float32)
    result = cluster_embeddings(np.vstack([a, b]), 'hdbscan', {'min_cluster_size': 5, 'min_samples': 1})
    assert len(set(result.labels) - {-1}) == 2


def test_fixed_input_reproducible():
    rng = np.random.default_rng(1)
    data = rng.normal(0, 1, (30, 4)).astype(np.float32)
    first = cluster_embeddings(data, 'hdbscan', {'min_cluster_size': 4})
    second = cluster_embeddings(data, 'hdbscan', {'min_cluster_size': 4})
    assert np.array_equal(first.labels, second.labels)
    assert first.noise_indices == second.noise_indices


def test_more_than_24_clusters_not_dropped():
    rng = np.random.default_rng(2)
    blobs = []
    for k in range(25):
        center = np.array([k * 10.0, (k * 7) % 100], dtype=np.float32)
        blobs.append(np.tile(center, (6, 1)) + rng.normal(0, 0.01, (6, 2)).astype(np.float32))
    data = np.vstack(blobs)
    result = cluster_embeddings(data, 'hdbscan', {'min_cluster_size': 4, 'min_samples': 1})
    # 25 个簇全部保留,行数一分不少
    assert len(set(result.labels) - {-1}) == 25
    assert len(result.labels) == data.shape[0]


def test_unknown_method_rejected():
    with pytest.raises(ValueError, match='unsupported'):
        cluster_embeddings(np.eye(2, dtype=np.float32), 'kmeans')
