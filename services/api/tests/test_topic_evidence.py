"""W11 集成:主题证据只返回本项目记录;版本不匹配/外项目路径 404;列表优先已发布。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_topic_returns_only_own_evidence(topic_case):
    c = topic_case
    response = client.get(
        f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}/evidence",
        params={"topic_version_id": c.topic_version_id},
    )
    assert response.status_code == 200
    ids = {item["feedback_id"] for item in response.json()["items"]}
    assert c.feedback_id in ids
    assert c.foreign_feedback_id not in ids


def test_revision_mismatch_returns_404(topic_case):
    c = topic_case
    response = client.get(
        f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}/evidence",
        params={"topic_version_id": 999},
    )
    assert response.status_code == 404


def test_foreign_project_returns_only_its_own_evidence(topic_case):
    # 双向隔离:外项目查询只返回自己的记录,本项目 feedback 不泄漏到外项目
    c = topic_case
    response = client.get(
        f"/api/v1/projects/{c.other_project_id}/topics/{c.topic_id}/evidence",
        params={"topic_version_id": c.topic_version_id},
    )
    assert response.status_code == 200
    ids = {item["feedback_id"] for item in response.json()["items"]}
    assert c.foreign_feedback_id in ids
    assert c.feedback_id not in ids


def test_list_topics_prefers_published_revision(topic_case):
    c = topic_case
    response = client.get(f"/api/v1/projects/{c.project_id}/topics")
    assert response.status_code == 200
    names = {item["title"] for item in response.json()["items"]}
    assert "物流体验" in names
    # 外项目同名主题不出现
    assert "外项目主题" not in names


def test_evidence_items_carry_source_row_and_quote(topic_case):
    c = topic_case
    response = client.get(
        f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}/evidence",
        params={"topic_version_id": c.topic_version_id},
    )
    item = response.json()["items"][0]
    assert item["source_row"] == 0
    assert item["quote"] == "物流信息一直没有更新"
