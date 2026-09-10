"""W09 代表选择契约:确定性、质心最近优先、limit 上限、id 平局裁定。"""
import numpy as np
import pytest

from app.representatives import select_representatives


def test_closest_to_centroid_first():
    ids = ['a', 'b', 'c']
    # 质心 [2.167, 2.333]:a 距离最小,应首先入选
    vectors = np.array([[1.0, 1.0], [0.5, 1.0], [5.0, 5.0]], dtype=np.float32)
    picked = select_representatives(ids, vectors, limit=2)
    assert picked[0] == 'a'


def test_limit_respected():
    ids = [f's{i}' for i in range(10)]
    vectors = np.eye(10, dtype=np.float32)
    assert len(select_representatives(ids, vectors, limit=3)) == 3


def test_never_exceeds_input():
    ids = ['x', 'y']
    vectors = np.eye(2, dtype=np.float32)
    assert select_representatives(ids, vectors, limit=8) == ['x', 'y']


def test_tie_break_by_id_is_deterministic():
    vectors = np.zeros((3, 4), dtype=np.float32)
    ids = ['c', 'a', 'b']
    assert select_representatives(ids, vectors, limit=2) == ['a', 'b']
    assert select_representatives(ids, vectors, limit=2) == ['a', 'b']


def test_empty_and_non_positive_limit():
    assert select_representatives([], np.empty((0, 4), dtype=np.float32)) == []
    assert select_representatives(['a'], np.eye(1, dtype=np.float32), limit=0) == []


def test_length_mismatch_rejected():
    with pytest.raises(ValueError, match='matching'):
        select_representatives(['a', 'b'], np.eye(1, dtype=np.float32))
