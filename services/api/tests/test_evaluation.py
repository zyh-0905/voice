"""离线评估必须跑**真实路径**(工程计划 13.3)。

这个脚本此前调用 `app.analysis.analyze_feedback`——一个词频统计函数,而流水线
走的是分块 → 向量 → 聚类 → 命名 → 发布,从不经过它。于是「评估通过」证明的是
一件生产上不会发生的事。现在它跑 `build_topics_from_run`,与流水线同一个函数。
"""
import json
from pathlib import Path

from services.api.evaluation.evaluate_analysis import evaluate


def _report():
    path = Path(__file__).parents[1] / 'evaluation' / 'fixtures.json'
    return evaluate(json.loads(path.read_text(encoding='utf-8-sig')))


def test_evaluation_runs_the_real_topic_path():
    report = _report()
    # 夹具两条高度相似的反馈,真实聚类应该产出至少一个主题
    assert report['topic_count'] >= 1, '真实路径没有产出主题,评估等于没跑'
    assert report['valid_rows'] == report['fixtures']
    # 聚出来的主题必须真的被命名过,而不是全部降级成占位名
    assert report['named_topic_count'] >= 1


def test_evaluation_reports_counts_alongside_ratios():
    """13.3:夹具规模远小于独立标注集,百分比必须与原始计数一起给出。"""
    report = _report()
    # 夹具只是路径冒烟,不是 13.1 要求的人工标注集(约 300 条)
    assert report['fixtures'] < 300
    assert report['evidence_refs'] >= 1
    assert report['note'] and report['limitations'], '必须写明口径与局限'
    # 断言的是「没有把 F1 当指标报出来」,不是字面不含这两个字符——
    # limitations 里正应该写明「不报告主题一致性 F1」。
    assert not any('f1' in key.lower() for key in report), \
        '聚类标签无金标准映射,不得把它换算成 F1 报出'


def test_evaluation_evidence_quotes_match_the_source_text():
    """引用精确匹配率衡量的是「quote 是否为对应正文的精确子串」。"""
    report = _report()
    assert report['evidence_refs_exact'] == report['evidence_refs']
    assert report['quote_exact_match_rate'] == 1.0
