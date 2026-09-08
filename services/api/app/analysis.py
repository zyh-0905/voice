"""Deterministic, local feedback analysis used by the demo worker.

The implementation deliberately has no network or LLM dependency.  Its output
is stable for a given set of rows, making it suitable for audit evidence and
unit tests while leaving room for a production analyzer to replace it.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}")
_STOP = {"this", "that", "with", "from", "have", "反馈", "客户", "服务"}


def analyze_feedback(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    evidence: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        text = " ".join(str(v) for v in row.values() if v is not None)
        tokens = [t.lower() for t in _WORD.findall(text) if t.lower() not in _STOP]
        counts.update(tokens)
        for token in sorted(set(tokens)):
            start = text.lower().find(token)
            if start >= 0:
                evidence.append({"row_index": row_index, "keyword": token,
                                 "offset": {"start": start, "end": start + len(token)},
                                 "text": text})
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    total = sum(counts.values()) or 1
    topics = [{"name": word, "count": count, "ratio": round(count / total, 4)}
              for word, count in ranked[:10]]
    evidence.sort(key=lambda item: (item["row_index"], item["offset"]["start"], item["keyword"]))
    top = ", ".join(f"{name} ({count})" for name, count in ranked[:3])
    summary = f"识别到 {len(rows)} 条反馈，主要主题：{top}。" if top else f"未识别到 {len(rows)} 条反馈中的明确主题。"
    return {"topics": topics, "summary": summary, "evidence": evidence}
