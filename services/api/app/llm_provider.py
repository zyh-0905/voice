"""Structured analysis provider boundary.

The default application path remains local and deterministic; this module makes
an external structured provider an explicit, replaceable integration point.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from urllib import error, request


class StructuredLLMProvider(Protocol):
    def analyze(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...


def validate_structured_output(value: Any) -> dict[str, Any]:
    """Validate and normalize the provider contract, raising ValueError clearly."""
    if not isinstance(value, dict):
        raise ValueError("structured output must be an object")
    if not isinstance(value.get("summary"), str):
        raise ValueError("structured output summary must be a string")
    topics = value.get("topics")
    evidence = value.get("evidence")
    if not isinstance(topics, list) or not isinstance(evidence, list):
        raise ValueError("structured output requires topics and evidence arrays")
    checked_topics: list[dict[str, Any]] = []
    for i, topic in enumerate(topics):
        if not isinstance(topic, dict) or not isinstance(topic.get("name"), str):
            raise ValueError(f"topic[{i}].name must be a string")
        if not isinstance(topic.get("count"), int) or isinstance(topic["count"], bool) or topic["count"] < 0:
            raise ValueError(f"topic[{i}].count must be a non-negative integer")
        ratio = topic.get("ratio")
        if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not 0 <= ratio <= 1:
            raise ValueError(f"topic[{i}].ratio must be between 0 and 1")
        checked_topics.append({"name": topic["name"], "count": topic["count"], "ratio": float(ratio)})
    checked_evidence: list[dict[str, Any]] = []
    for i, item in enumerate(evidence):
        if not isinstance(item, dict) or not isinstance(item.get("keyword"), str) or not isinstance(item.get("text"), str):
            raise ValueError(f"evidence[{i}] requires keyword and text strings")
        if not isinstance(item.get("row_index"), int) or item["row_index"] < 0:
            raise ValueError(f"evidence[{i}].row_index must be a non-negative integer")
        offset = item.get("offset")
        if not isinstance(offset, dict) or not isinstance(offset.get("start"), int) or not isinstance(offset.get("end"), int) or offset["start"] < 0 or offset["end"] < offset["start"]:
            raise ValueError(f"evidence[{i}].offset is invalid")
        checked_evidence.append({"row_index": item["row_index"], "keyword": item["keyword"], "offset": {"start": offset["start"], "end": offset["end"]}, "text": item["text"]})
    return {"topics": checked_topics, "summary": value["summary"], "evidence": checked_evidence}


@dataclass
class MockStructuredProvider:
    def analyze(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        output = {"topics": [], "summary": f"Analyzed {len(rows)} feedback rows.", "evidence": []}
        return validate_structured_output(output)


@dataclass
class HTTPStructuredProvider:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 20.0

    def analyze(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        payload = json.dumps({"model": self.model, "rows": list(rows)}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with request.urlopen(request.Request(self.base_url, data=payload, headers=headers, method="POST"), timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"structured provider request failed: {exc}") from exc
        return validate_structured_output(body)
