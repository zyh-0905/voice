from app.analysis import analyze_feedback

def evaluate(rows):
    result = analyze_feedback(rows)
    topics = result.get('topics', [])
    evidence_ok = all(0 <= e['start'] <= e['end'] for t in topics for e in t.get('evidence', []))
    passed = int(bool(topics) and bool(result.get('summary')) and evidence_ok)
    return {'fixtures': 1, 'passed': passed, 'failed': 1 - passed, 'topic_count': len(topics), 'summary_nonempty': bool(result.get('summary')), 'evidence_offsets_valid': evidence_ok}

if __name__ == '__main__':
    import json
    print(json.dumps(evaluate([{'text': '退款流程太慢，客服没有及时回复'}]), ensure_ascii=False))
