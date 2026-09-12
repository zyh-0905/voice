"""Deterministic ingestion helpers shared by upload and validation endpoints."""
import csv, io, re
from collections import Counter

REDACTION_VERSION = "v1"
MAX_XLSX_ROWS = 100_000
MAX_XLSX_COLUMNS = 256
_PATTERNS = [("email", re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")), ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")), ("order_id", re.compile(r"\b(?:ORD|ORDER)[-_]?\d{6,}\b", re.I))]

def redact_text(text: str) -> dict:
    hits = Counter(); out = text
    for kind, pattern in _PATTERNS:
        def sub(m): hits[kind] += 1; return f"<{kind.upper()}_REDACTED>"
        out = pattern.sub(sub, out)
    return {"text": out, "hits": dict(hits), "version": REDACTION_VERSION}

# 标识这一行、不属于反馈正文的字段名(与 feedback.py 的取值键一致)
IDENTITY_KEYS = ('feedback_id', 'id')


def row_text(row) -> str:
    """把治理后的一行拼成反馈正文——逐值脱敏,并排除标识字段。

    排除标识字段是有意的:它们标识这一行,不是用户说的话。拼进正文会让 ID 进入
    向量、主题引语与证据摘录,用户会看到引文以 "fb_xxx" 开头。
    代价是:若来源表真有一列名为 `id` 且承载业务内容,那段内容不会被分析。
    这与取值逻辑一致——`feedback_id` / `id` 在本仓库本来就被当作标识。
    """
    return ' '.join(
        redact_text(str(value))['text']
        for key, value in row.items()
        if str(key) not in IDENTITY_KEYS and value is not None
    )


def iter_run_feedback(run) -> list[tuple[str, dict]]:
    """遍历一个 run 输入集合里的反馈,返回 (feedback_id, 原始行)。

    feedback_id 的派生规则集中在这里:行内显式 id 优先,否则 `fb_{dataset_id}_{行号}`。
    流水线与复盘计算都依赖它——两处各拼一套的话,主题证据和复盘分子会指向不同的
    反馈集合,而且不会有任何报错。
    """
    items: list[tuple[str, dict]] = []
    for dataset in (run or {}).get('datasets') or []:
        preview = dataset.get('preview') or {}
        for index, row in enumerate(preview.get('rows') or []):
            if not isinstance(row, dict):
                continue
            feedback_id = str(row.get('feedback_id') or f"fb_{dataset.get('id', 'ds')}_{index}")
            items.append((feedback_id, row))
    return items


def redact_row(row: dict) -> dict:
    """逐值脱敏一行。

    逐值而不是先拼成整串,避免相邻字段接出本不存在的模式(例如一列以数字结尾、
    下一列以数字开头,拼起来会被电话号码规则命中)。
    """
    return {str(key): redact_text(str(value))['text'] for key, value in row.items()}


def classify_rows(rows: list[dict], time_field: str | None = None) -> dict:
    seen = set(); valid = invalid = duplicate = redacted = missing_time = 0; preview = []
    for row in rows:
        key = tuple(sorted((str(k), str(v)) for k,v in row.items()))
        if key in seen: duplicate += 1
        seen.add(key); clean = {}; row_redacted = False
        for k,v in row.items():
            r = redact_text(str(v)); clean[k] = r['text']; row_redacted |= bool(r['hits'])
        redacted += row_redacted
        if time_field and not str(row.get(time_field, '')).strip(): missing_time += 1
        if any(str(v).strip() for v in row.values()): valid += 1
        else: invalid += 1
        if len(preview) < 5: preview.append(clean)
    return {"total": len(rows), "valid": valid, "invalid": invalid, "duplicate": duplicate, "redacted": redacted, "missing_time": missing_time, "preview": preview}

def parse_csv_text(text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text, newline=''))
    headers = reader.fieldnames or []
    if not headers or any(not str(h).strip() for h in headers):
        raise ValueError('CSV header is missing or contains an empty field')
    rows = []
    for row in reader:
        line_no = reader.line_num
        if None in row:
            raise ValueError(f'CSV row {line_no} has more fields than the header')
        missing = [header for header, value in row.items() if value is None]
        if missing:
            raise ValueError(f'CSV row {line_no} has fewer fields than the header: {", ".join(missing)}')
        rows.append(row)
    # 持久业务正文只保留脱敏结果(工程计划 7.2/6.2):rows 是下游(流水线、看板、
    # 导出、证据源)唯一的取数来源,原始行不出这个函数。stats 必须基于**原始行**
    # 统计,否则「脱敏命中数」会恒为 0。
    stats = classify_rows(rows)
    return {"headers": headers, "rows": [redact_row(row) for row in rows], "stats": stats}

def parse_xlsx_bytes(data: bytes) -> dict:
    """Parse the first worksheet of an XLSX workbook with bounded dimensions."""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0] if wb.worksheets else None
        if ws is None: raise ValueError("workbook has no worksheets")
        values = ws.iter_rows(values_only=True)
        try: raw_headers = next(values)
        except StopIteration: return {"headers": [], "rows": [], "stats": classify_rows([])}
        headers = [str(v).strip() if v is not None else "" for v in raw_headers]
        if len(headers) > MAX_XLSX_COLUMNS: raise ValueError(f"column limit exceeded ({MAX_XLSX_COLUMNS})")
        rows = []
        for idx, vals in enumerate(values, 1):
            if idx > MAX_XLSX_ROWS: raise ValueError(f"row limit exceeded ({MAX_XLSX_ROWS})")
            row = {h: ("" if v is None else str(v)) for h, v in zip(headers, vals)}
            rows.append(row)
        # 同 CSV:落库即脱敏,stats 仍按原始行统计
        stats = classify_rows(rows)
        return {"headers": headers, "rows": [redact_row(row) for row in rows], "stats": stats}
    except ValueError: raise
    except Exception as exc:
        raise ValueError(f"invalid or corrupted xlsx file: {exc}") from exc
