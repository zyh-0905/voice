"""W07 分块契约:offset 复原、超长拒绝、空文本、emoji、中英混合、重叠去重。"""
import pytest

from app.segments import SegmentSpan, count_chars, dedup_overlap, split_redacted


def test_offsets_reconstruct_redacted_text():
    text = "包装破损。客服很久没有回复。" * 30
    spans = split_redacted(text, tokenizer=count_chars, max_tokens=64, overlap=8)
    assert len(spans) > 1
    assert all(text[s.start:s.end] == s.text for s in spans)
    # 全部 span 覆盖完整文本(首段从头,末段到尾)
    assert spans[0].start == 0
    assert spans[-1].end == len(text)


def test_empty_text_returns_no_spans():
    assert split_redacted("") == []


def test_overlong_single_sentence_is_rejected():
    with pytest.raises(ValueError, match='segment too long'):
        split_redacted("这是一个没有句号的长句" * 10, tokenizer=count_chars, max_tokens=16)


def test_emoji_offsets_are_unicode_safe():
    text = "反馈:😀👍 问题已解决。继续观察。"
    spans = split_redacted(text, tokenizer=count_chars, max_tokens=32)
    assert all(text[s.start:s.end] == s.text for s in spans)
    assert any("😀" in s.text for s in spans)


def test_mixed_chinese_english():
    text = "Delivery was slow。物流很慢,望改进。Refund pending, waiting."
    spans = split_redacted(text, tokenizer=count_chars, max_tokens=24)
    assert all(text[s.start:s.end] == s.text for s in spans)
    assert len(spans) >= 2


def test_overlap_region_repeats_and_dedup_reconstructs():
    text = "第一句完整。第二句完整。第三句完整。第四句完整。"
    spans = split_redacted(text, tokenizer=count_chars, max_tokens=12, overlap=4)
    assert len(spans) > 1
    # 相邻段存在重叠区间
    assert any(spans[i + 1].start < spans[i].end for i in range(len(spans) - 1))
    # 跳过重叠前缀后无损复原
    assert dedup_overlap(spans) == text


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        split_redacted("文本", max_tokens=0)
    with pytest.raises(ValueError):
        split_redacted("文本", overlap=-1)
    with pytest.raises(ValueError):
        split_redacted("文本", max_tokens=4, overlap=4)


def test_no_overlap_spans_are_contiguous():
    text = "句子一。句子二。句子三。"
    spans = split_redacted(text, tokenizer=count_chars, max_tokens=100)
    assert len(spans) == 1
    assert spans[0] == SegmentSpan(start=0, end=len(text), text=text)
