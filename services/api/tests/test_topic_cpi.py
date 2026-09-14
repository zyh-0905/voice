"""8.6 / QA-24:CPI 必须在真实主题路径上算出来,而不只是单元测试里算得对。

`compute_cpi` 本身有二十来条断言,但在此之前它**只被测试调用**:`GET /topics` 把
`cpiDisplayValue` 和 `evidence.cpi` 都写死成 None,于是界面上永远是「暂无 CPI 数据」,
而那套单元测试全绿。这一条用例把两端接上:走真实发布路径,再从接口读回 CPI。
"""
import pytest

from app.scoring import compute_cpi
from app.main import app  # noqa: F401  确保路由已注册
from support.client import make_client

client = make_client()


def _row(case, topic_id):
    response = client.get(f"/api/v1/projects/{case.project_id}/topics")
    assert response.status_code == 200
    return next(item for item in response.json()["items"] if item["id"] == topic_id)


def test_topics_expose_a_computed_cpi(topic_case):
    """列表里的 CPI 是算出来的,不是占位。

    fixture 的口径:n1=1 条证据、N1=3 条有效反馈、severity=medium。
      V = 100 × min(1, (1/3)/0.20) = 100
      G = null(本接口没有可比前期窗口)
      S = 50(MEDIUM)      B = 50(企业配置缺失,缺省值)
    可用权重 0.25+0.30+0.15 = 0.70,归一化后
      CPI = (100×0.25 + 50×0.30 + 50×0.15) / 0.70 = 67.857… → HALF_UP → 68
    """
    row = _row(topic_case, "t1")
    assert row["cpiDisplayValue"] == "68", "列表列必须显示服务端算出的整数"

    cpi = row["evidence"]["cpi"]
    assert cpi is not None, "证据面板的 CPI 不能是 null——那正是修复前的样子"
    assert cpi["display_value"] == "68"
    assert cpi["coverage"] == 70, "缺了增长分项,覆盖率应是 0.70"
    assert cpi["provisional"] is True, "含缺省假设与缺失分项时必须标暂定"


def test_missing_growth_is_labelled_not_zero(topic_case):
    """缺失的分项写「缺失」,不能写 0。

    0 的意思是「算出来就是 0」,与「这一项没有数据」在界面上长得一样,
    而它们该引发的判断完全不同(一个是没增长,一个是没算)。
    """
    components = {c["label"]: c["displayValue"] for c in _row(topic_case, "t1")["evidence"]["cpi"]["components"]}
    assert components["增长"] == "缺失"
    assert components["数量"] == "100"
    assert components["严重度"] == "50"
    assert components["业务影响"] == "50"


def test_topic_detail_carries_the_same_cpi(topic_case):
    """7.4 要求主题详情给出「分项」;两个接口的分母口径必须一致,
    否则同一个主题在列表和详情里会显示两个数。"""
    c = topic_case
    detail = client.get(f"/api/v1/projects/{c.project_id}/topics/t1").json()
    assert detail["topic"]["cpi"] is not None
    assert detail["topic"]["cpi"] == _row(c, "t1")["evidence"]["cpi"]


@pytest.fixture
def published_topic_factory():
    """按给定 severity 发布一个最小 run,返回 (project_id, run_id)。

    用独立 fixture 而不是去改 topic_case 的行:topic_versions 按 5.2 是
    **不可原地更新**的,能改它反而说明模型没落实。
    """
    from uuid import uuid4
    from app.main import repository
    from app.publishing import EvidenceRef, TopicDraft, publish_revision
    from support.feedback import seed_run_feedback

    def _make(severity: str):
        project_id = f"cpi-sev-{uuid4().hex[:8]}"
        repository.create_project({"id": project_id, "name": "CPI Severity"})
        dataset_id = "ds_sev"
        feedback_id = f"fb_{dataset_id}_0"
        run_id = f"run_cpi_sev_{uuid4().hex[:8]}"
        run = {
            "id": run_id, "project_id": project_id, "dataset_ids": [dataset_id],
            "status": "queued", "stage": "queued", "total": 3,
            "datasets": [{"id": dataset_id, "project_id": project_id, "preview": {"rows": [
                {"content": "物流信息一直没有更新,等待了三天。"}]}}],
        }
        seed_run_feedback(repository, run)
        repository.create_analysis(run)
        publish_revision(repository, run_id, [
            TopicDraft(topic_id="t1", name="物流体验", summary="", severity=severity,
                       evidence=[EvidenceRef(feedback_id, 0, "物流信息一直没有更新", 0, 10)]),
        ], {feedback_id: "物流信息一直没有更新,等待了三天。"}, unassigned_count=2, repository=repository)
        return project_id

    return _make


def test_severity_actually_moves_the_index(published_topic_factory):
    """严重度真的作为 S 分项参与计算,不是一个摆设字段。

    只断言「有 CPI」的话,一个恒返回常数的实现也能过;而「换了输入指数却没动」
    恰恰是接线没接上的典型表现。两个 run 除 severity 外完全同构。
    """
    medium = published_topic_factory("medium")
    critical = published_topic_factory("critical")

    medium_value = next(i for i in client.get(f"/api/v1/projects/{medium}/topics").json()["items"]
                        if i["id"] == "t1")["cpiDisplayValue"]
    critical_value = next(i for i in client.get(f"/api/v1/projects/{critical}/topics").json()["items"]
                          if i["id"] == "t1")["cpiDisplayValue"]

    assert medium_value != critical_value, "severity 变了 CPI 却没变,说明它没参与计算"
    # 两端都与 8.6 的纯函数逐位对齐,确认接口给的就是那个数
    for severity, actual in (("medium", medium_value), ("critical", critical_value)):
        expected = compute_cpi(n1=1, N1=3, n0=None, N0=None, severity=severity, business=None)
        assert actual == str(expected.display_value)
