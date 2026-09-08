"""Deterministic ingestion helpers shared by upload and validation endpoints."""
import csv, io, re
from collections import Counter

REDACTION_VERSION = "v1"
_PATTERNS = [("email", re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")), ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")), ("order_id", re.compile(r"\b(?:ORD|ORDER)[-_]?\d{6,}\b", re.I))]

def redact_text(text: str) -> dict:
    hits = Counter()
    out = text
    for kind, pattern in _PATTERNS:
        def sub(m): hits[kind] += 1; return f"<{kind.upper()}_REDACTED>"
        out = pattern.sub(sub, out)
    return {"text": out, "hits": dict(hits), "version": REDACTION_VERSION}

def classify_rows(rows: list[dict], time_field: str | None = None) -> dict:
    seen = set(); valid = invalid = duplicate = redacted = missing_time = 0
    preview = []
    for row in rows:
        key = tuple(sorted((str(k), str(v)) for k,v in row.items()))
        if key in seen: duplicate += 1
        seen.add(key)
        clean = {}
        row_redacted = False
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
