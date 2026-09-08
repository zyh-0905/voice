import pytest
from app.llm_provider import MockStructuredProvider, validate_structured_output


def test_mock_provider_returns_strict_schema():
    result = MockStructuredProvider().analyze([{"text": "hello"}])
    assert set(result) == {"topics", "summary", "evidence"}
    assert isinstance(result["topics"], list)


def test_schema_rejects_invalid_evidence():
    with pytest.raises(ValueError, match="offset"):
        validate_structured_output({"topics": [], "summary": "ok", "evidence": [{"keyword": "x", "text": "x", "row_index": 0}]})
