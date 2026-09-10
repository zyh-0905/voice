"""W07 分块:句段优先、token 预算控制、重叠上下文。

SegmentSpan 的 start/end 是原始脱敏文本的 Unicode 字符 offset,
任意 span 均满足 text[start:end] == span.text;重叠区间通过回退实现,
去重后可以无损复原原文(见 tests/test_segments.py)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

_SENTENCE_RE = re.compile(r'[^。！？!?；;\n]+[。！？!?；;\n]*')

TokenCounter = Callable[[str], int]


def count_chars(text: str) -> int:
    """默认 token 计数:按 Unicode 字符计,对中文即近似单字 token。"""
    return len(text)


def _token_count(tokenizer: TokenCounter, text: str) -> int:
    count = tokenizer(text)
    if count < 0:
        raise ValueError('tokenizer must not return negative counts')
    return count


def _split_sentences(text: str) -> list[tuple[int, int, str]]:
    """按句末标点/换行切分,保留分隔符,覆盖全部字符(含前导标点)。"""
    parts: list[tuple[int, int, str]] = []
    pos = 0
    for match in _SENTENCE_RE.finditer(text):
        if match.start() != pos:
            parts.append((pos, match.start(), text[pos:match.start()]))
        parts.append((match.start(), match.end(), match.group()))
        pos = match.end()
    if pos != len(text):
        parts.append((pos, len(text), text[pos:]))
    return parts


@dataclass(frozen=True)
class SegmentSpan:
    start: int
    end: int
    text: str


def split_redacted(
    text: str,
    tokenizer: TokenCounter | None = None,
    max_tokens: int = 256,
    overlap: int = 0,
) -> list[SegmentSpan]:
    """把脱敏文本切成 token 预算内的段;offset 为 Unicode 字符索引。

    - 空文本返回 []。
    - 单个句子超过 max_tokens 时拒绝(ValueError),不做无法复原的硬切。
    - overlap > 0 时,后续段起点回退 overlap 个字符,形成上下文重叠;
      重叠区在相邻 span 中重复出现,按「跳过重叠前缀」可无损复原。
    """
    if not text:
        return []
    if max_tokens < 1:
        raise ValueError('max_tokens must be positive')
    if overlap < 0:
        raise ValueError('overlap must be non-negative')
    if overlap >= max_tokens:
        raise ValueError('overlap must be smaller than max_tokens')
    tokenizer = tokenizer or count_chars

    sentences = _split_sentences(text)
    for _start, _end, part in sentences:
        if _token_count(tokenizer, part) > max_tokens:
            raise ValueError(f'segment too long for max_tokens={max_tokens}')

    spans: list[SegmentSpan] = []
    i = 0
    prev_end = 0
    while i < len(sentences):
        sent_start, sent_end, _ = sentences[i]
        # 重叠回退下限是上一块起点(重叠不超过前块长度),允许切入句子内部;
        # 切片仍满足 text[start:end] == span.text,去重后无损复原
        start = sent_start if not spans else max(spans[-1].start, prev_end - overlap)
        end = sent_end
        j = i
        while j + 1 < len(sentences):
            _next_start, next_end, _ = sentences[j + 1]
            if _token_count(tokenizer, text[start:next_end]) <= max_tokens:
                j += 1
                end = next_end
            else:
                break
        spans.append(SegmentSpan(start=start, end=end, text=text[start:end]))
        prev_end = end
        i = j + 1
    return spans


def dedup_overlap(spans: Iterable[SegmentSpan]) -> str:
    """跳过相邻 span 的重叠前缀,无损拼接复原原文。"""
    pieces: list[str] = []
    prev_end: int | None = None
    for span in spans:
        skip = max(0, (prev_end or span.start) - span.start)
        pieces.append(span.text[skip:])
        prev_end = span.end
    return ''.join(pieces)
