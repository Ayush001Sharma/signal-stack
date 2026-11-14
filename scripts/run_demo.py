"""Reproducible end-to-end demo driver. Uses ONLY the public REST API.

Steps per company: create (or reuse) → wait for setup (research → competitors → interview → source discovery)
→ answer interview as demo operator (labelled, never as founder) → approve recommended sources
→ upload labelled synthetic internal files → run weekly brief (crawl → analyse → rank → brief)
→ run monthly audit → export Markdown/PDF reports to docs/reports/.

Usage:  python scripts/run_demo.py [--api http://localhost:8000] [--only MeetUniversity] [--skip-setup]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def wait_job(c: httpx.Client, job_id: int, label: str, timeout: int = 5400) -> dict:
    t0 = time.time()
    while True:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            print(f"  [{label}] {j['status']}: {j.get('message')}")
            return j
        if time.time() - t0 > timeout:
            raise TimeoutError(label)
        time.sleep(10)


def latest_job(c, cid, job_type):
    items = c.get("/api/jobs", params={"company_id": cid, "job_type": job_type, "page_size": 1}).json()["items"]
    return items[0] if items else None


def run(api: str, only: str | None, skip_setup: bool, crawl: bool = True, audit: bool = True):
    cfg = json.loads((ROOT / "demo/companies.json").read_text())
    out_dir = ROOT / "docs/reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(base_url=api, timeout=600)
    existing = {x["name"]: x for x in c.get("/api/companies").json()}
    for comp in cfg["companies"]:
        if only and comp["name"] != only:
            continue
        print(f"=== {comp['name']}")
        if comp["name"] in existing:
            cid = existing[comp["name"]]["id"]
        else:
            cid = c.post("/api/companies", json={"name": comp["name"], "website": comp["website"], "run_setup": True}).json()["id"]
        if not skip_setup:
            j = latest_job(c, cid, "setup")
            if j and j["status"] in ("queued", "running"):
                wait_job(c, j["id"], "setup")
        # Review step: reject obviously wrong suggestions (reasons are recorded in demo/companies.json)
        comps = {x["name"]: x for x in c.get(f"/api/companies/{cid}/competitors").json()}
        for rj in comp.get("review_reject", []):
            if rj["name"] in comps and comps[rj["name"]]["status"] == "suggested":
                c.patch(f"/api/companies/{cid}/competitors/{comps[rj['name']]['id']}", json={"status": "rejected"})
                srcs = [s for s in c.get(f"/api/companies/{cid}/sources").json() if s["competitor_id"] == comps[rj["name"]]["id"]]
                for s in srcs:
                    c.patch(f"/api/companies/{cid}/sources/{s['id']}", json={"approval_status": "rejected"})
                print(f"  rejected competitor {rj['name']}: {rj['why']} ({len(srcs)} sources rejected)")
        # Interview (demo operator answers; follow-ups get an honest 'unknown' or are skipped)
        for _ in range(30):
            st = c.get(f"/api/companies/{cid}/interview").json()
            q = st["next"]
            if not q:
                break
            if q["is_followup"]:
                body = {"skip": True, "confidential": True}
            else:
                ans = comp["answers"].get(q["topic"], "SKIP")
                body = {"skip": True, "confidential": True} if ans == "SKIP" else {"answer": ans, "answered_by": "demo_operator"}
            r = c.post(f"/api/companies/{cid}/interview/questions/{q['id']}/answer", json=body)
            r.raise_for_status()
            print(f"  Q{q['position']}{'(follow-up)' if q['is_followup'] else ''} [{q['topic']}] {'skipped' if body.get('skip') else 'answered'}")
        # Approve recommended sources
        r = c.post(f"/api/companies/{cid}/sources/bulk", json={"action": "approve_recommended"}).json()
        print(f"  approved recommended sources: {r['updated']}")
        # Uploads
        have = {d["filename"] for d in c.get(f"/api/companies/{cid}/documents").json()}
        for up in comp.get("uploads", []):
            p = ROOT / up["path"]
            if p.name in have:
                continue
            r = c.post(f"/api/companies/{cid}/documents", files={"file": (p.name, p.read_bytes())}, data={"description": up["description"]})
            print(f"  uploaded {p.name}: {r.status_code} {r.json().get('status')} records={r.json().get('record_count')}")
        # Weekly brief (crawl + analysis + ranking + brief)
        jid = c.post(f"/api/companies/{cid}/briefs", json={"crawl": crawl}).json()["job_run_id"]
        j = wait_job(c, jid, "weekly brief")
        # Monthly audit
        if audit:
            aid = c.post(f"/api/companies/{cid}/audits").json()["job_run_id"]
            wait_job(c, aid, "monthly audit")
        brief = c.get(f"/api/companies/{cid}/briefs/latest").json()
        slug = comp["name"].lower().replace(" ", "-")
        (out_dir / f"{slug}-monday-brief.md").write_text(brief["markdown"])
        (out_dir / f"{slug}-monday-brief.pdf").write_bytes(c.get(f"/api/companies/{cid}/briefs/{brief['id']}/pdf").content)
        audit = c.get(f"/api/companies/{cid}/audits").json()[0]
        (out_dir / f"{slug}-source-audit.md").write_text(audit["markdown"])
        print(f"  saved reports for {comp['name']} (brief #{brief['id']}, stats={brief['stats']})")
        # Context-change stress test: see scripts/context_stress_test.py


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--only")
    ap.add_argument("--skip-setup", action="store_true")
    ap.add_argument("--no-crawl", action="store_true", help="regenerate briefs from stored evidence only")
    ap.add_argument("--no-audit", action="store_true")
    a = ap.parse_args()
    run(a.api, a.only, a.skip_setup, crawl=not a.no_crawl, audit=not a.no_audit)
    sys.exit(0)
