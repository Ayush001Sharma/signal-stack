"""Internal Intelligence: secure upload handling and extraction of patterns from CSV/XLSX/PDF/TXT.

Records are split into rows (tabular) or paragraphs/sentences (documents), labelled by lexicon rules
(objection, lost deal, product request, recurring problem, operational risk, sales pattern) and grouped
into recurring themes by lexical similarity. Each theme with ≥2 records — or an explicit lost-deal
reason — becomes an ``internal`` Signal citing the document and verbatim quotes.
All queries are scoped by company_id; files live under ``<upload_dir>/<company_id>/``.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, InternalDocument, RawItem, Signal, utcnow
from app.services import nlp

log = logging.getLogger(__name__)

ALLOWED = {
    "csv": {"text/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"},
    "pdf": {"application/pdf", "application/octet-stream"},
    "txt": {"text/plain", "application/octet-stream"},
}
MAGIC = {"xlsx": b"PK\x03\x04", "pdf": b"%PDF"}

LABELS = {
    "objection": r"\b(too expensive|expensive|price|pricing|cost|budget|not sure|concern\w*|hesitat\w*|objection|trust|worried|afraid|competitor (is )?cheaper|no time)\b",
    "lost_deal": r"\b(lost|churn\w*|cancel\w*|went with|chose (another|a competitor)|closed[- ]lost|did not convert|dropped out|no[- ]show|refund)\b",
    "product_request": r"(\b(feature request|would like|wish|request\w*|please add|need(s|ed)? (a|an|more)|missing|integration|support for|can you add|(can|could) (we|you) add)\b|\basked\b[^.]{0,25}\badd\b|\badd (a|an|more)\b)",
    "recurring_problem": r"\b(delay\w*|slow|bug|error|issue|problem|complain\w*|confus\w*|unclear|late|stuck|not working|broken|poor)\b",
    "operational_risk": r"\b(compliance|legal|visa (refus|reject)\w*|rejected|policy change|staff(ing)? shortage|attrition|outage|backlog|capacity|dependency|vendor|regulat\w*)\b",
}
LABEL_TITLES = {
    "objection": "Recurring customer objection",
    "lost_deal": "Lost-deal pattern",
    "product_request": "Repeated product/service request",
    "recurring_problem": "Recurring customer/operational problem",
    "operational_risk": "Emerging operational risk",
    "sales_pattern": "Sales pattern",
}
LABEL_ACTION = {
    "objection": ("Objections recur in sales conversations and suppress conversion.", "Create a scripted response and proof points for this objection; review with the sales team this week."),
    "lost_deal": ("Repeated lost-deal reasons point to a fixable gap in offer, price or process.", "Review the lost deals behind this pattern and decide one change (offer, price or follow-up) to test."),
    "product_request": ("Repeated requests signal unmet demand that could become a new revenue line.", "Size the request (how many customers, potential revenue) and decide whether to build, partner or decline."),
    "recurring_problem": ("A recurring problem damages customer experience and referrals.", "Assign an owner to root-cause the problem and track it to resolution."),
    "operational_risk": ("This could disrupt delivery or compliance if it escalates.", "Assess likelihood/impact and define a mitigation owner."),
    "sales_pattern": ("Quantified pattern from the uploaded sales data.", "Use the pattern to re-prioritise pipeline focus this week."),
}


class UploadError(ValueError):
    pass


def validate_upload(filename: str, content_type: str | None, data: bytes) -> str:
    s = get_settings()
    if not filename or "." not in filename:
        raise UploadError("File must have an extension (.csv, .xlsx, .pdf, .txt)")
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED:
        raise UploadError(f"Unsupported file type .{ext}; allowed: csv, xlsx, pdf, txt")
    if len(data) == 0:
        raise UploadError("File is empty")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise UploadError(f"File exceeds {s.max_upload_mb} MB limit")
    if ext in MAGIC and not data.startswith(MAGIC[ext]):
        raise UploadError(f"File content does not match .{ext} format")
    if ext in ("csv", "txt"):
        try:
            data[:200000].decode("utf-8")
        except UnicodeDecodeError:
            try:
                data[:200000].decode("latin-1")
            except UnicodeDecodeError as exc:
                raise UploadError("Text file is not valid UTF-8/Latin-1") from exc
        if b"\x00" in data[:4096]:
            raise UploadError("Binary content in text file")
    return ext


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def extract_records(ext: str, data: bytes) -> tuple[list[dict], list[dict]]:
    """Return (records, rows). records: [{text, ref}]; rows: list of dicts for tabular files."""
    rows: list[dict] = []
    if ext == "csv":
        reader = csv.DictReader(io.StringIO(_decode(data)))
        rows = [dict(r) for r in reader]
    elif ext == "xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(next(it, []) or [])]
        for r in it:
            if r and any(v is not None for v in r):
                rows.append({header[i] if i < len(header) else f"col{i}": ("" if v is None else str(v)) for i, v in enumerate(r)})
    if rows:
        text_cols = [c for c in rows[0].keys() if c and any(len(str(r.get(c) or "")) > 25 for r in rows[:50])]
        records = []
        for i, r in enumerate(rows, start=2):
            parts = [str(r.get(c) or "").strip() for c in text_cols if str(r.get(c) or "").strip()]
            if parts:
                records.append({"text": " | ".join(parts), "ref": f"row {i}", "row": r})
        return records, rows
    if ext == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:200])
    else:
        text = _decode(data)
    paras = [nlp.clean_text(p) for p in re.split(r"\n\s*\n|\r\n\r\n|(?<=[.!?])\s+(?=[A-Z])", text) if len(nlp.clean_text(p)) > 25]
    return [{"text": p[:1500], "ref": f"passage {i}"} for i, p in enumerate(paras, start=1)], []


def label_record(text: str) -> list[str]:
    return [lab for lab, pat in LABELS.items() if re.search(pat, text, re.I)]


def _find_col(rows: list[dict], *names: str) -> str | None:
    if not rows:
        return None
    for c in rows[0].keys():
        lc = (c or "").lower()
        if any(n in lc for n in names):
            return c
    return None


def sales_patterns(rows: list[dict]) -> list[dict]:
    """Quantified patterns from CRM-like tables (stage/status/outcome, segment/source, lost reason)."""
    out = []
    status_col = _find_col(rows, "status", "stage", "outcome", "result")
    seg_col = _find_col(rows, "segment", "source", "channel", "country", "destination", "program", "product", "plan")
    reason_col = _find_col(rows, "lost reason", "lost_reason", "reason", "objection")
    if status_col:
        statuses = Counter((r.get(status_col) or "").strip().lower() for r in rows)
        won = sum(v for k, v in statuses.items() if any(w in k for w in ("won", "closed won", "enrolled", "converted", "paid", "success")))
        lost = sum(v for k, v in statuses.items() if any(w in k for w in ("lost", "dropped", "churn", "cancel")))
        if won + lost:
            out.append({"label": "sales_pattern", "title": f"Win rate {won / (won + lost):.0%} across {won + lost} closed records", "detail": f"Won {won}, lost {lost} (column '{status_col}').", "count": won + lost})
        if seg_col and won + lost >= 6:
            by = defaultdict(lambda: [0, 0])
            for r in rows:
                st = (r.get(status_col) or "").lower()
                seg = (r.get(seg_col) or "unknown").strip() or "unknown"
                if any(w in st for w in ("won", "enrolled", "converted", "paid", "success")):
                    by[seg][0] += 1
                elif any(w in st for w in ("lost", "dropped", "churn", "cancel")):
                    by[seg][1] += 1
            rates = [(seg, w / (w + l), w + l) for seg, (w, l) in by.items() if w + l >= 3]
            if len(rates) >= 2:
                rates.sort(key=lambda t: -t[1])
                best, worst = rates[0], rates[-1]
                out.append({"label": "sales_pattern", "title": f"'{best[0]}' converts best ({best[1]:.0%}, n={best[2]}) vs '{worst[0]}' ({worst[1]:.0%}, n={worst[2]})",
                            "detail": f"Conversion by '{seg_col}' among closed records.", "count": best[2] + worst[2]})
    if reason_col:
        reasons = Counter(nlp.clean_text(r.get(reason_col) or "").lower() for r in rows if (r.get(reason_col) or "").strip())
        for reason, n in reasons.most_common(3):
            if n >= 2:
                out.append({"label": "lost_deal", "title": f"Lost-deal reason: “{reason}” ({n} records)", "detail": f"From column '{reason_col}'.", "count": n})
    return out


def cluster_records(records: list[dict], label: str) -> list[list[dict]]:
    items = [r for r in records if label in r["labels"]]
    if not items:
        return []
    texts = [r["text"] for r in items]
    sims = nlp.tfidf_similarity_matrix(texts, texts)
    clusters: list[list[int]] = []
    assigned = set()
    for i in range(len(items)):
        if i in assigned:
            continue
        group = [i] + [j for j in range(i + 1, len(items)) if j not in assigned and sims[i][j] >= 0.22]
        assigned.update(group)
        clusters.append(group)
    clusters.sort(key=len, reverse=True)
    return [[items[i] for i in g] for g in clusters]


def save_upload(db: Session, company: Company, filename: str, content_type: str | None, data: bytes, description: str | None = None) -> InternalDocument:
    ext = validate_upload(filename, content_type, data)
    s = get_settings()
    folder = Path(s.upload_dir) / str(company.id)
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)[:120]
    stored = folder / f"{uuid.uuid4().hex}.{ext}"
    stored.write_bytes(data)
    doc = InternalDocument(company_id=company.id, filename=safe, stored_path=str(stored), content_type=content_type or "application/octet-stream", file_type=ext,
                           size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), description=description, status="processing")
    db.add(doc)
    db.flush()
    try:
        process_document(db, company, doc, data)
    except Exception as exc:
        log.exception("document processing failed")
        doc.status, doc.error = "error", f"{type(exc).__name__}: {exc}"[:1000]
    db.flush()
    return doc


def process_document(db: Session, company: Company, doc: InternalDocument, data: bytes) -> list[Signal]:
    from app.services.analysis import AREA, OWNER  # noqa: F401  (owner mapping reused by briefs)

    records, rows = extract_records(doc.file_type, data)
    for r in records:
        r["labels"] = label_record(r["text"])
    doc.record_count = len(records)
    themes = []
    for label in LABELS:
        for group in cluster_records(records, label):
            if len(group) >= 2 or (label in ("lost_deal", "operational_risk") and len(group) == 1 and len(records) <= 30):
                kp = nlp.keyphrases([g["text"] for g in group], top_k=3)
                themes.append({"label": label, "title": f"{LABEL_TITLES[label]}: {', '.join(kp[:2]) or 'see quotes'} ({len(group)} mention{'s' if len(group) > 1 else ''})",
                               "count": len(group), "quotes": [{"text": nlp.truncate(g["text"], 300), "ref": g["ref"]} for g in group[:5]]})
    for p in sales_patterns(rows):
        themes.append({**p, "quotes": [{"text": p["detail"], "ref": "aggregate"}]})
    themes.sort(key=lambda t: -t["count"])
    label_counts = Counter(lab for r in records for lab in r["labels"])
    doc.insights = {"labels": dict(label_counts), "themes": themes[:25], "unlabelled_records": sum(1 for r in records if not r["labels"])}
    signals = []
    total = max(1, len(records))
    for t in themes[:15]:
        share = t["count"] / total
        quotes = " / ".join(f"“{q['text']}” ({q['ref']})" for q in t["quotes"][:3])
        raw = RawItem(company_id=company.id, document_id=doc.id, url=f"internal://documents/{doc.id}", url_hash=nlp.sha256(f"doc{doc.id}:{t['title']}"), title=t["title"], content=quotes,
                      snippet=nlp.truncate(quotes, 500), publisher=f"Internal upload: {doc.filename}", published_at=None, date_source="upload", content_hash=nlp.sha256(quotes + t["title"]),
                      title_key=nlp.title_key(t["title"])[:300], item_type="internal_record", extra={"label": t["label"], "count": t["count"]})
        db.add(raw)
        db.flush()
        why, action = LABEL_ACTION[t["label"]]
        impact = min(1.0, 0.45 + 0.5 * share + (0.1 if t["label"] in ("lost_deal", "operational_risk") else 0))
        relevance = 0.9  # company's own data is relevant by construction
        urgency = 0.5 + (0.2 if t["label"] in ("operational_risk", "lost_deal") else 0)
        comps = {"relevance": relevance, "impact": round(impact, 3), "urgency": urgency, "credibility": 0.75, "recency": 0.8, "novelty": 1.0}
        from app.services.analysis import HIGH, MEDIUM, WEIGHTS

        score = round(100 * sum(WEIGHTS[k] * comps[k] for k in WEIGHTS), 1)
        sig = Signal(company_id=company.id, raw_item_id=raw.id, document_id=doc.id, category="internal", signal_type=t["label"], title=t["title"], what_happened=f"{t['title']}. Evidence: {nlp.truncate(quotes, 400)}",
                     event_date=None, discovered_at=utcnow(), evidence_url=f"internal://documents/{doc.id}", evidence_snippet=nlp.truncate(quotes, 600), publisher=f"Internal upload: {doc.filename}",
                     verification_status="internal_document", source_reliability=0.75, evidence_strength=round(min(1.0, 0.5 + 0.1 * t["count"]), 3), relevance=relevance, impact=comps["impact"],
                     urgency=urgency, novelty=1.0, recency=0.8, priority_score=score, priority="high" if score >= HIGH else ("medium" if score >= MEDIUM else "low"),
                     score_breakdown={"weights": WEIGHTS, "components": comps, "reasons": {"relevance": "company's own internal data", "impact": f"{t['count']} of {total} records ({share:.0%}) share this theme", "urgency": t["label"], "credibility": "internal document (unaudited)", "recency": "uploaded data; record dates not parsed", "novelty": "first occurrence"},
                                      "formula": "100 × (0.30·relevance + 0.25·impact + 0.15·urgency + 0.10·credibility + 0.10·recency + 0.10·novelty)"},
                     polarity="threat" if t["label"] in ("lost_deal", "operational_risk", "objection", "recurring_problem") else "opportunity", business_area={"objection": "Sales & Marketing", "lost_deal": "Sales & Marketing", "product_request": "Product", "recurring_problem": "Customer Experience", "operational_risk": "Compliance & Operations", "sales_pattern": "Sales & Marketing"}[t["label"]],
                     why_it_matters=why, recommended_action=action, is_meaningful=True, materiality="material", corroboration_count=1, status="new", interpretation_method="rules", cluster_key=nlp.title_key(t["title"])[:300])
        db.add(sig)
        signals.append(sig)
    doc.status = "processed"
    db.flush()
    return signals
