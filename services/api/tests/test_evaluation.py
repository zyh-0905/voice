import json
from pathlib import Path

from services.api.evaluation.evaluate_analysis import evaluate


def test_fixtures_meet_quality_gates():
    path = Path(__file__).parents[1] / "evaluation" / "fixtures.json"
    report = evaluate(json.loads(path.read_text(encoding="utf-8-sig")))
    assert report["failed"] == 0
    assert report["passed"] == report["fixtures"]
