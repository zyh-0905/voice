"""W07 向量契约:CPU 真实编码、行一一对应、L2 归一化、确定性、revision 可追溯。"""
import numpy as np

from app.embedding import EMBEDDING_DIM, EMBEDDING_REVISION, encode_segments


def test_rows_correspond_one_to_one_with_inputs():
    texts = ["物流很慢", "退款未到账", ""]
    matrix = encode_segments(texts)
    assert matrix.shape == (len(texts), EMBEDDING_DIM)
    assert matrix.dtype == np.float32


def test_empty_text_yields_zero_row():
    matrix = encode_segments(["", "物流很慢"])
    assert np.all(matrix[0] == 0)
    assert np.any(matrix[1] != 0)


def test_rows_are_l2_normalized():
    matrix = encode_segments(["物流很慢", "客服响应及时", "包装破损"])
    norms = np.linalg.norm(matrix, axis=1)
    assert np.allclose(norms, 1.0)


def test_encoding_is_deterministic_across_calls():
    texts = ["物流很慢", "退款未到账"]
    assert np.array_equal(encode_segments(texts), encode_segments(texts))


def test_similar_texts_are_closer_than_dissimilar():
    a = encode_segments(["物流信息一直没有更新"])
    b = encode_segments(["物流信息更新不及时"])
    c = encode_segments(["退款一直没有到账"])
    sim_ab = float(np.dot(a[0], b[0]))
    sim_ac = float(np.dot(a[0], c[0]))
    assert sim_ab > sim_ac


def test_revision_is_traceable():
    assert EMBEDDING_REVISION
    assert EMBEDDING_REVISION.startswith('hashing-ngram-v1')
