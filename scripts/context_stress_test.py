"""Context-change stress test: apply a hypothetical business context, record how the Signal Stack is reassessed,
then revert to the original research-only context. Writes docs/reports/<company>-context-change.md."""
import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def wait(c, jid):
    while True:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(10)


def table(cc):
    rows = sorted(cc["relevance_changes"], key=lambda r: r["delta"])
    rows = rows[:12] + rows[-12:] if len(rows) > 24 else rows
    return ["| Source | Before | After | Δ |", "|---|---|---|---|"] + [f"| {r['name']} | {r['before']:.2f} | {r['after']:.2f} | {r['delta']:+.2f} |" for r in rows]


def main(api, name):
    cfg = next(x for x in json.loads((ROOT / "demo/companies.json").read_text())["companies"] if x["name"] == name)
    c = httpx.Client(base_url=api, timeout=600)
    cid = next(x["id"] for x in c.get("/api/companies").json() if x["name"] == name)
    cx = cfg["context_change"]
    print("applying:", wait(c, c.post(f"/api/companies/{cid}/context", json={"industry": cx["industry"], "business_context": cx["business_context"]}).json()["job_run_id"])["message"])
    cc = c.get(f"/api/companies/{cid}/context-changes").json()[0]
    new_ids = set(cc["new_source_ids"])
    proposals = [s for s in c.get(f"/api/companies/{cid}/sources").json() if s["id"] in new_ids and s["approval_status"] == "pending"]
    lines = [f"# Context-change stress test — {name}", "", f"*{cx.get('_label', 'Hypothetical context')}*", "", "## What changed", "", cc["summary"], "",
             f"- **Before:** industry `{cc['old_context']['industry']}`, context `{cc['old_context']['business_context']}`",
             f"- **After:** industry `{cc['new_context']['industry']}`, context: “{cc['new_context']['business_context']}”",
             f"- **New themes leading discovery:** {', '.join(cc['added_keywords'])}", "",
             "## Approved sources flagged as no longer useful", ""] + ([f"- {f['name']} — {f['why']}" for f in cc["flagged_sources"]] or ["- None"]) + [
             "", "## Relevance re-scored (largest losses and gains)", ""] + table(cc) + [
             "", f"## New sources proposed for the new context ({len(proposals)})", ""] + [f"- **{s['name']}** ({s['category']}, expected relevance {s['expected_relevance']:.0%}, {'recommended' if s['recommended'] else 'not recommended'}) — {s['reason']}" for s in proposals]
    print("reverting:", wait(c, c.post(f"/api/companies/{cid}/context", json={"industry": "", "business_context": ""}).json()["job_run_id"])["message"])
    rv = c.get(f"/api/companies/{cid}/context-changes").json()[0]
    lines += ["", "## Revert to the original (research-only) context", "", rv["summary"], "", "Retired themes: " + ", ".join(rv["removed_keywords"][:15])]
    if proposals:  # proposals made only for the hypothetical context must not enter the real Signal Stack
        c.post(f"/api/companies/{cid}/sources/bulk", json={"action": "reject", "source_ids": [s["id"] for s in proposals]})
        lines.append(f"\nThe {len(proposals)} sources proposed for the hypothetical context were rejected after the revert.")
    out = ROOT / "docs/reports" / f"{name.lower()}-context-change.md"
    out.write_text("\n".join(lines) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--company", default="Supabase")
    a = ap.parse_args()
    main(a.api, a.company)
