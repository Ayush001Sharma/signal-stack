"""Company research: crawl the public website + public news, build a provenance-tracked profile.

Each extracted statement becomes a ProfileFact with a status:
  verified           – quoted from the company's own website (URL + snippet) or stated by founder/user
  unverified         – third-party report (news) not confirmed by the company
  assumption         – inferred by rules or AI (e.g. business model from wording cues)
  needs_confirmation – important information that is not publicly available
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Company, FactStatus, ProfileFact
from app.services import nlp
from app.services.fetcher import FetchError, PoliteFetcher, RobotsDisallowed, get_fetcher
from app.services.llm import get_llm
from app.services.search import discover_feed_links, news_search

log = logging.getLogger(__name__)

PAGE_PRIORITY = [
    ("about", 10), ("company", 6), ("product", 9), ("service", 9), ("solution", 8), ("pricing", 9), ("plans", 7),
    ("feature", 7), ("platform", 6), ("how-it-works", 6), ("customers", 6), ("case-stud", 5), ("industries", 5),
    ("press", 5), ("news", 5), ("blog", 4), ("careers", 4), ("partners", 5), ("why", 3), ("contact", 2),
]
GENERIC_HEADINGS = re.compile(
    r"^(why choose us|testimonials?|faqs?|frequently asked|contact( us)?|get started|our (team|blog)|latest (news|posts|blogs?)|subscribe|follow us|"
    r"quick links|useful links|newsletter|about us|what (we|do we) offer|our services|services|products|reviews?|success stories|"
    r"know more about us|let'?s talk|get in touch|read more|learn more|sign up|login|menu|home)$",
    re.I,
)


def _page_info(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    meta = {}
    for m in soup.find_all("meta"):
        k = m.get("name") or m.get("property")
        if k and m.get("content"):
            meta[k.lower()] = nlp.clean_text(m["content"])
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        t = nlp.clean_text(tag.get_text(" "))
        if 2 <= len(t) <= 120:
            headings.append((tag.name, t))
    links = []
    for a in soup.find_all("a", href=True):
        links.append((nlp.clean_text(a.get_text(" "))[:80], urljoin(url, a["href"].strip())))
    feeds = discover_feed_links(html, url)
    text = nlp.html_to_text(html)
    return {
        "url": url,
        "title": nlp.clean_text(soup.title.get_text()) if soup.title else "",
        "meta": meta,
        "headings": headings,
        "links": links,
        "feeds": feeds,
        "text": text,
    }


def _snippet_around(text: str, phrase: str, width: int = 110) -> str | None:
    idx = text.lower().find(phrase.lower())
    if idx < 0:
        return None
    return nlp.clean_text(text[max(0, idx - width) : idx + len(phrase) + width])


def crawl_site(website: str, fetcher: PoliteFetcher, max_pages: int = 8) -> tuple[list[dict], list[str]]:
    pages: list[dict] = []
    errors: list[str] = []
    try:
        home = fetcher.get(website)
    except (FetchError, RobotsDisallowed) as exc:
        return [], [f"homepage: {exc}"]
    home_info = _page_info(home.final_url, home.text)
    pages.append(home_info)
    host = nlp.domain_of(home.final_url)
    candidates: dict[str, int] = {}
    for text, link in home_info["links"]:
        if nlp.domain_of(link) != host or link.startswith("mailto") or "#" in link.split("/")[-1][:1]:
            continue
        path = urlparse(link).path.lower().strip()
        if not path or path == "/" or re.search(r"\.(pdf|jpg|png|zip)$", path):
            continue
        score = 1
        for kw, w in PAGE_PRIORITY:
            if kw in path or kw in text.lower():
                score = max(score, w)
        clean = link.split("#")[0].strip()
        candidates[clean] = max(candidates.get(clean, 0), score)
    for link, _ in sorted(candidates.items(), key=lambda kv: -kv[1])[: max_pages - 1]:
        try:
            r = fetcher.get(link)
            if "html" not in r.headers.get("content-type", "html"):
                continue
            info = _page_info(r.final_url, r.text)
            if "404" in info["title"] and len(pages) > 0 and info["text"][:200] == pages[0]["text"][:200]:
                continue
            pages.append(info)
        except (FetchError, RobotsDisallowed) as exc:
            errors.append(f"{link}: {exc}")
    return pages, errors


def _offering_headings(pages: list[dict], company_name: str) -> list[tuple[str, str, str]]:
    """Headings that look like product/service names: (heading, url, snippet)."""
    out: list[tuple[str, str, str]] = []
    seen = set()
    cname = company_name.lower()
    for p in pages:
        is_offer_page = any(k in p["url"].lower() for k in ("product", "service", "solution", "feature", "platform", "pricing"))
        for level, h in p["headings"]:
            words = h.split()
            if not (2 <= len(words) <= 8) or GENERIC_HEADINGS.match(h.strip(" :.!")) or h.endswith("?"):
                continue
            if cname in h.lower() and len(words) < 4:
                continue
            if level == "h1" and not is_offer_page:
                continue
            key = h.lower()
            if key in seen:
                continue
            seen.add(key)
            snippet = _snippet_around(p["text"], h, 160) or h
            # Prefer headings followed by descriptive text (feature blocks)
            out.append((h, p["url"], snippet))
    # rank: headings on offering pages first, then those containing offering nouns
    noun_re = re.compile(r"(support|process|planning|preparation|selection|application|payments?|api|platform|analytics|management|insurance|loans?|courses?|program|software|tool|service|solution|app|gateway|card|delivery|consult|visa|scholarship|admission|hosting|database|checkout|payroll|billing|banking)", re.I)
    out.sort(key=lambda t: (0 if noun_re.search(t[0]) else 1))
    return out[:10]


def classify_industry(text: str) -> tuple[str, float]:
    emb = nlp.get_embedder()
    labels = list(nlp.INDUSTRY_TAXONOMY.keys())
    descs = [f"{k}: {v}" for k, v in nlp.INDUSTRY_TAXONOMY.items()]
    sims = emb.similarity(text[:3000], descs)
    best = max(range(len(labels)), key=lambda i: sims[i])
    return labels[best], float(sims[best])


def _add(db: Session, company: Company, field: str, value: str, status: FactStatus, origin: str, url: str | None = None, evidence: str | None = None):
    db.add(ProfileFact(company_id=company.id, field=field, value=value[:2000], status=status.value, origin=origin, source_url=url, evidence=(evidence or "")[:1500] or None))


def research_company(db: Session, company: Company, fetcher: PoliteFetcher | None = None, use_llm: bool = True) -> dict:
    fetcher = fetcher or get_fetcher()
    company.status = "researching"
    db.flush()
    # Replace previous research-derived facts; keep founder/user facts.
    db.execute(delete(ProfileFact).where(ProfileFact.company_id == company.id, ProfileFact.origin.in_(["research", "news", "ai"])))

    pages, errors = crawl_site(company.website, fetcher)
    all_text = " ".join(p["text"] for p in pages)
    home = pages[0] if pages else None
    summary: dict = {"pages_crawled": [p["url"] for p in pages], "errors": errors, "feeds_found": sorted({f for p in pages for f in p["feeds"]})}

    # -- Positioning (verified quotes from the website)
    positioning = None
    if home:
        desc = home["meta"].get("description") or home["meta"].get("og:description")
        if desc:
            positioning = desc
            _add(db, company, "positioning", desc, FactStatus.verified, "research", home["url"], f'Meta description on homepage: "{desc}"')
        h1 = next((h for lvl, h in home["headings"] if lvl == "h1"), None)
        if h1 and (not desc or h1.lower() not in desc.lower()):
            _add(db, company, "positioning", f'Homepage headline: "{h1}"', FactStatus.verified, "research", home["url"], h1)
            positioning = positioning or h1

    # -- Products / services
    offerings = _offering_headings(pages, company.name)
    for h, url, snip in offerings:
        _add(db, company, "products", h, FactStatus.verified, "research", url, snip)
    meta_kw = [k.strip() for k in (home["meta"].get("keywords", "") if home else "").split(",") if k.strip()]

    # -- Customer segments
    segs_all = nlp.find_segments(all_text)
    seg_counts = {s: sum(len(re.findall(r"\b" + re.escape(w) + r"\b", all_text.lower())) for w in nlp.SEGMENT_LEXICON[s]) for s in segs_all}
    segs = {s: v for s, v in segs_all.items() if seg_counts[s] >= 2}
    for seg, snip in sorted(segs.items(), key=lambda kv: -seg_counts.get(kv[0], 0))[:6]:
        _add(db, company, "customer_segments", f"{seg} (addressed on website)", FactStatus.verified, "research", home["url"] if home else None, snip)
    if segs:
        _add(db, company, "customer_segments", "Which of these segments generates the most revenue is not public", FactStatus.needs_confirmation, "research")

    # -- Geographies
    countries = nlp.find_countries(all_text)
    for c, snip in list(countries.items())[:10]:
        _add(db, company, "geographies", f"{c} (mentioned on website)", FactStatus.verified, "research", home["url"] if home else None, snip)
    phone_cc = re.findall(r"(?:tel:|\+)\s?(\d{1,3})[\s-]?\d{3,}", " ".join(link for p in pages for _, link in p["links"] if link.startswith("tel:")))
    summary["phone_codes"] = sorted(set(phone_cc))
    if phone_cc:
        _add(db, company, "geographies", f"Contact phone uses country code +{phone_cc[0]}", FactStatus.verified, "research", home["url"] if home else None, f"tel: +{phone_cc[0]}…")
    if countries:
        _add(db, company, "geographies", "Whether mentioned countries are operating markets or target/destination markets", FactStatus.needs_confirmation, "research")

    # -- Business model (assumption from wording cues)
    cues = {m: h for m, h in nlp.business_model_cues(all_text).items() if len(h) >= 2 or m in ("Subscription / SaaS", "Services / consulting fees") and len(h) >= 1}
    cues = dict(sorted(cues.items(), key=lambda kv: -len(kv[1])))
    pricing_page = next((p for p in pages if "pricing" in p["url"].lower() or "plans" in p["url"].lower()), None)
    for model, hits in sorted(cues.items(), key=lambda kv: -len(kv[1]))[:3]:
        _add(db, company, "business_model", model, FactStatus.assumption, "research", home["url"] if home else None, "Inferred from website wording: " + ", ".join(f'"{h}"' for h in hits[:5]))
    if not pricing_page:
        _add(db, company, "business_model", "No public pricing page found — pricing and revenue model need founder confirmation", FactStatus.needs_confirmation, "research")
    else:
        _add(db, company, "business_model", "Public pricing page exists", FactStatus.verified, "research", pricing_page["url"], nlp.truncate(pricing_page["text"], 300))
    _add(db, company, "revenue_streams", "Revenue streams and their mix are not publicly disclosed", FactStatus.needs_confirmation, "research")

    # -- Industry
    if company.industry:
        industry, ind_score = company.industry, 1.0
        _add(db, company, "industry", company.industry, FactStatus.verified, "user", None, "Provided during company setup")
    else:
        industry, ind_score = classify_industry((company.business_context or "") + " " + " ".join(meta_kw) + " " + all_text)
        _add(db, company, "industry", industry, FactStatus.assumption, "research", None, f"Classified by semantic similarity to website text (score {ind_score:.2f})")
    if company.business_context:
        _add(db, company, "business_context", company.business_context, FactStatus.verified, "user", None, "Provided during company setup")

    # -- Contact / organisation facts
    emails = sorted({link[7:] for p in pages for _, link in p["links"] if link.startswith("mailto:")})
    for e in emails[:2]:
        _add(db, company, "contact", f"Public contact email: {e}", FactStatus.verified, "research", home["url"] if home else None, e)

    # -- Keywords: candidates from headings/meta/title (high-signal zones), weighted by body frequency
    company.keywords = company_keywords(pages, meta_kw, company)

    # -- Public developments (third-party news; unverified)
    developments = []
    profile_text = " ".join([company.name, positioning or "", industry, " ".join(company.keywords[:15])])
    seen_titles = set()
    for q in (f'"{company.name}"', f'"{nlp.domain_of(company.website)}"'):
        for item in news_search(q, fetcher)[:25]:
            blob = f"{item['title']} {item.get('snippet') or ''}"
            if nlp.name_key(company.name) not in nlp.name_key(blob) and nlp.domain_of(company.website) not in blob.lower():
                continue
            tk = nlp.title_key(item["title"])
            if tk in seen_titles:
                continue
            seen_titles.add(tk)
            developments.append(item)
    if developments:
        sims = nlp.get_embedder().similarity(profile_text, [f"{d['title']} {d.get('snippet') or ''}" for d in developments])
        kept, rejected = [], []
        for d, s in zip(developments, sims):
            (kept if s >= 0.35 else rejected).append((d, s))
        for d, s in kept[:10]:
            date = d["published"].date().isoformat() if d.get("published") else "date unknown"
            _add(db, company, "developments", f"{d['title']} ({d.get('publisher') or 'news'}, {date})", FactStatus.unverified, "news", d["url"], d.get("snippet") or d["title"])
        summary["developments_found"] = len(kept)
        summary["name_collisions_excluded"] = [{"title": d["title"], "url": d["url"], "similarity": round(s, 2)} for d, s in rejected[:10]]
    else:
        summary["developments_found"] = 0
        _add(db, company, "developments", "No third-party news coverage found in robots-permitted news indexes", FactStatus.needs_confirmation, "news")

    # -- Optional AI one-line summary (clearly labelled as assumption)
    one_liner = None
    llm = get_llm()
    if use_llm and llm.available and all_text:
        prompt = (
            "Using ONLY the website text below, write one neutral sentence (max 35 words) describing what the company does, "
            "for whom, and how it likely makes money. If revenue model is not stated, say 'revenue model not stated'.\n\n"
            f"Company: {company.name}\nWebsite text:\n{all_text[:3500]}"
        )
        one_liner = llm.generate(prompt, max_tokens=90)
        if one_liner:
            _add(db, company, "summary", one_liner, FactStatus.assumption, "ai", None, f"AI-generated by local model {llm.model} from crawled website text; not a verified fact")
    if not one_liner:
        offer_txt = ", ".join(h for h, _, _ in offerings[:3]) or "its services"
        seg_txt = ", ".join(list(segs.keys())[:2]).lower() or "its customers"
        one_liner = f"{company.name} appears to offer {offer_txt.lower()} to {seg_txt} (rule-based summary from website headings)."
        _add(db, company, "summary", one_liner, FactStatus.assumption, "research", None, "Rule-based summary from website headings and segment cues")

    company.profile = {
        "one_liner": one_liner,
        "industry": industry,
        "industry_confidence": round(ind_score, 2),
        "positioning": positioning,
        "products": [h for h, _, _ in offerings],
        "customer_segments": list(segs.keys()),
        "geographies": list(countries.keys()),
        "business_model": list(cues.keys())[:3],
        "meta_keywords": meta_kw[:20],
        "site_feeds": summary["feeds_found"],
    }
    summary["method"] = {"llm": llm.status() if use_llm else {"available": False}, "embeddings": nlp.get_embedder().backend}
    company.research_summary = summary
    company.research_error = "; ".join(errors[:3]) if not pages else None
    company.status = "researched" if pages else "error"
    company.profile_version = (company.profile_version or 0) + 1
    db.flush()
    return summary


NOISE_WORDS = re.compile(r"\b(floor|road|nagar|east|west|north|south|pradesh|sector|street|suite|com|touch|links?|quick|cookie|copyright|login|monday|tuesday|wednesday|thursday|friday|saturday|sunday|pvt|private limited|limited|llp|inc)\b")


def company_keywords(pages: list[dict], meta_kw: list[str], company: Company, top_k: int = 30) -> list[str]:
    zones = []
    for p in pages:
        zones.append(p["title"])
        zones.append(p["meta"].get("description", ""))
        zones.extend(h for _, h in p["headings"])
    zones.append(company.business_context or "")
    body = " ".join(p["text"] for p in pages).lower()
    cands = nlp.keyphrases(zones, top_k=120, boost=meta_kw[:25])
    name_tokens = {t for t in re.split(r"\W+", company.name.lower()) if t} | {nlp.name_key(company.name)}
    scored = []
    for c in cands:
        if any(ch.isdigit() for ch in c) or NOISE_WORDS.search(c):
            continue
        toks = c.split()
        ck = nlp.name_key(c)
        if ck in name_tokens or nlp.name_key(company.name) in ck or (len(toks) == 1 and toks[0] in name_tokens):
            continue
        freq = body.count(c)
        bonus = 3 if c in [m.lower() for m in meta_kw] else 0
        scored.append((freq + bonus + 0.5 * len(toks), c))
    if not scored:
        return []
    # Re-rank by specificity: semantic similarity to the company's core description (title/meta/industry)
    core = " ".join([pages[0]["title"], pages[0]["meta"].get("description", ""), " ".join(meta_kw[:10]), company.business_context or "", company.industry or ""]) if pages else (company.business_context or "")
    cand = [c for _, c in sorted(scored, reverse=True)[:60]]
    freq = {c: f for f, c in scored}
    maxf = max(freq.values()) or 1
    sims = nlp.get_embedder().similarity(core, cand) if core.strip() else [0.5] * len(cand)
    meta_set = {m.lower() for m in meta_kw}
    final = sorted(((0.45 * freq[c] / maxf + 0.55 * s + (0.15 if len(c.split()) > 1 else 0) + (0.3 if c in meta_set else 0) - (0.2 if len(c.split()) == 1 else 0), c) for c, s in zip(cand, sims)), reverse=True)
    out = []
    if company.business_context:
        out = [k for k in nlp.keyphrases([company.business_context], top_k=8) if not any(ch.isdigit() for ch in k)]
    for _, c in final:
        if c not in out:
            out.append(c)
    return out[:top_k]


def profile_text(company: Company, facts: list[ProfileFact] | None = None) -> str:
    """Single text representation of the company used for relevance scoring."""
    p = company.profile or {}
    parts = [
        company.name,
        company.industry or p.get("industry") or "",
        company.business_context or "",
        p.get("one_liner") or "",
        p.get("positioning") or "",
        "Products: " + ", ".join(p.get("products", [])[:8]),
        "Segments: " + ", ".join(p.get("customer_segments", [])[:5]),
        "Markets: " + ", ".join(p.get("geographies", [])[:8]),
        "Keywords: " + ", ".join((company.keywords or [])[:20]),
    ]
    if facts:
        parts += [f.value for f in facts if f.origin == "interview" and f.status == FactStatus.verified.value][:20]
    return ". ".join(x for x in parts if x)


def facts_by_field(db: Session, company_id: int) -> dict[str, list[ProfileFact]]:
    out: dict[str, list[ProfileFact]] = {}
    for f in db.scalars(select(ProfileFact).where(ProfileFact.company_id == company_id).order_by(ProfileFact.id)):
        out.setdefault(f.field, []).append(f)
    return out


def word_counts(text: str) -> Counter:
    return Counter(re.findall(r"[a-z]{3,}", text.lower()))
