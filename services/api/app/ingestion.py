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
    reader = csv.DictReader(io.StringIO(text)); rows = list(reader)
    return {"headers": reader.fieldnames or [], "rows": rows, "stats": classify_rows(rows)}

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
        return {"headers": headers, "rows": rows, "stats": classify_rows(rows)}
    except ValueError: raise
    except Exception as exc:
        raise ValueError(f"invalid or corrupted xlsx file: {exc}") from exc
