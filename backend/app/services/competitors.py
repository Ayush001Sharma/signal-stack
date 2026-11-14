"""Dynamic competitor / substitute discovery.

Nothing is hard-coded. The pipeline:
1. Build category queries from the researched profile (industry + top keyphrases).
2. Search robots-permitted news indexes; extract organisation-like names from headlines.
3. Count co-mentions across distinct articles; drop the company itself, publishers, places and generic words.
4. Validate each candidate with its own news coverage: semantic similarity between the candidate's coverage
   and the company profile (and, if available, a local-LLM classification grounded on those headlines).
5. Resolve an official website only when a fetched page's title/meta actually contains the candidate's name.
Every saved competitor carries evidence links and the reason it was included.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Competitor
from app.services import nlp
from app.services.fetcher import FetchError, PoliteFetcher, RobotsDisallowed, get_fetcher
from app.services.llm import get_llm
from app.services.research import profile_text
from app.services.search import news_search

log = logging.getLogger(__name__)

GENERIC_ENTITY = re.compile(
    r"^(visa|visas|students?|study|abroad|university|universities|college|edtech|fintech|startup|startups|government|ministry|report|series|"
    r"funding|budget|policy|rules?|news|today|week|top|best|new|india|indian|uk|us|usa|canada|australia|global|international|education|"
    r"payments?|bank|banks|rbi|sebi|ai|genai|ipo|crore|million|billion|inc|ltd|the|ceo|founder|cofounder|co-founder|exclusive|explained|business|limited|company|pvt|pvt ltd|private limited|group|technology|forum|motion|english|copy|led|opportunities|senior vice president|director|chairman|saas|paas|cloud|startup|software|database|postgres sql)$",
    re.I,
)


SIM_THRESHOLD = 0.38


def ranked_keywords(company: Company) -> list[str]:
    """Multi-word keyphrases ordered by specificity to the company's industry/positioning (+ meta keywords)."""
    p = company.profile or {}
    kws = [k for k in (company.keywords or []) if len(k.split()) >= 2][:12]
    industry = (company.industry or p.get("industry") or "").split("/")[-1].strip()
    core = " ".join([industry, p.get("positioning") or "", " ".join(p.get("meta_keywords", [])[:6]), company.business_context or ""])
    if kws and core.strip():
        sims = nlp.get_embedder().similarity(core, kws)
        meta = {m.lower() for m in p.get("meta_keywords", [])}
        ctx = {k for k in nlp.keyphrases([company.business_context], top_k=8)} if company.business_context else set()
        kws = [k for _, k in sorted(((s + (0.2 if k in meta else 0) + (0.4 if k in ctx else 0), k) for s, k in zip(sims, kws)), reverse=True)]
    return kws


def core_terms(company: Company) -> list[str]:
    """Most specific category terms: multi-word keyphrases closest to the company's industry/positioning."""
    p = company.profile or {}
    kws = [k for k in (company.keywords or []) if len(k.split()) >= 2][:12]
    industry = (company.industry or p.get("industry") or "").split("/")[-1].strip()
    core = " ".join([industry, p.get("positioning") or "", " ".join(p.get("meta_keywords", [])[:6]), company.business_context or ""])
    if kws and core.strip():
        sims = nlp.get_embedder().similarity(core, kws)
        meta = {m.lower() for m in p.get("meta_keywords", [])}
        kws = [k for _, k in sorted(((s + (0.2 if k in meta else 0), k) for s, k in zip(sims, kws)), reverse=True)]
    out = kws[:2]
    if industry and industry.lower() not in [k.lower() for k in out]:
        out.append(industry)
    return out or [company.name]


def home_country(company: Company) -> str | None:
    p = company.profile or {}
    if p.get("home_country"):
        return p["home_country"]
    tld = nlp.domain_of(company.website).rsplit(".", 1)[-1]
    cc = {"in": "India", "uk": "United Kingdom", "ca": "Canada", "au": "Australia", "de": "Germany", "sg": "Singapore"}
    if tld in cc:
        return cc[tld]
    phone = " ".join(map(str, (company.research_summary or {}).get("phone_codes", [])))
    codes = {"91": "India", "44": "United Kingdom", "1": "United States", "61": "Australia", "65": "Singapore", "49": "Germany", "971": "United Arab Emirates"}
    for code, country in codes.items():
        if phone.strip() == code:
            return country
    geos = p.get("geographies", [])
    return "India" if "India" in geos else None


def category_queries(company: Company) -> list[str]:
    terms = core_terms(company)
    country = home_country(company)
    suffixes = ["startup", "platform", "raises funding", "launches", "acquires", "competitors", "rivals", "app", "consultants", "company", "market leader"]
    queries = []
    for i, term in enumerate(terms):
        for suf in suffixes[: (11 if i == 0 else 5)]:
            queries.append(f"{term} {suf}")
        if country:
            queries.append(f"{term} {country}")
            queries.append(f"{term} {country} startup funding")
    queries += [f'"{company.name}" competitors', f'"{company.name}" alternatives', f'"{company.name}" vs']
    seen, out = set(), []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:28]


NON_COMPANY = re.compile(r"\b(university|universities|college|institute|school|ministry|department|government|council|commission|embassy|court|parliament|police|association|federation|board|authority|office)\b", re.I)


def _llm_extract_orgs(items: list[dict]) -> dict[str, set[str]]:
    """Grounded extraction: LLM lists company/brand names; only names appearing verbatim in the text are kept."""
    llm = get_llm()
    out: dict[str, set[str]] = defaultdict(set)
    if not llm.available:
        return out
    for start in range(0, len(items), 10):
        batch = items[start : start + 10]
        text = "\n".join(f"[{i}] {it['title']}. {(it.get('snippet') or '')[:220]}" for i, it in enumerate(batch))
        prompt = (
            "From the numbered news items below, list companies or commercial brands (NOT universities, schools, governments, "
            "regulators, media outlets or people) that are mentioned. Copy names exactly as written. Return JSON: "
            '{"items": [{"i": <item number>, "names": ["..."]}]}\n\n' + text
        )
        data = llm.generate_json(prompt, max_tokens=350)
        if not isinstance(data, dict):
            continue
        for row in data.get("items", []) or []:
            try:
                idx = int(row.get("i"))
            except (TypeError, ValueError):
                continue
            if not 0 <= idx < len(batch):
                continue
            blob = batch[idx]["title"] + " " + (batch[idx].get("snippet") or "")
            for name in row.get("names", []) or []:
                if isinstance(name, str) and 2 < len(name) < 60 and name in blob:
                    out[batch[idx]["url"]].add(name.strip())
    return out


def _resolve_website(name: str, articles: list[dict], fetcher: PoliteFetcher) -> tuple[str | None, str | None]:
    key = nlp.name_key(name)
    # 1) an article URL on the candidate's own domain
    for a in articles:
        dom = nlp.domain_of(a["url"])
        if key and key in nlp.name_key(dom.split(".")[0]):
            return f"https://{dom}", None
    # 2) try common domains, accept only if page title/meta contains the name
    for tld in (".com", ".in", ".io"):
        url = f"https://{key}{tld}"
        try:
            r = fetcher.get(url, use_cache=True)
        except (FetchError, RobotsDisallowed):
            continue
        soup = BeautifulSoup(r.text[:200000], "lxml")
        title = (soup.title.get_text() if soup.title else "") + " " + " ".join(m.get("content", "") for m in soup.find_all("meta", attrs={"property": "og:site_name"}))
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if key in nlp.name_key(title):
            return f"https://{nlp.domain_of(r.final_url)}", nlp.clean_text(desc_tag.get("content")) if desc_tag and desc_tag.get("content") else None
    return None, None


def _llm_classify(company: Company, name: str, headlines: list[str]) -> dict | None:
    llm = get_llm()
    if not llm.available:
        return None
    prompt = (
        f"Company A: {company.name} — {(company.profile or {}).get('one_liner', '')}\n"
        f"Candidate: {name}\nHeadlines that mention the candidate (the ONLY evidence you may use):\n- "
        + "\n- ".join(headlines[:8])
        + "\n\nBased only on these headlines, answer JSON with keys: is_organisation (bool), relationship "
        "('direct_competitor' | 'substitute' | 'not_competitor' | 'unclear'), description (<=20 words, what the candidate does per the headlines)."
    )
    data = llm.generate_json(prompt, max_tokens=120)
    return data if isinstance(data, dict) else None


def discover_competitors(db: Session, company: Company, fetcher: PoliteFetcher | None = None, max_competitors: int = 10, use_llm: bool = True) -> list[Competitor]:
    fetcher = fetcher or get_fetcher()
    queries = category_queries(company)
    mentions: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    evidence: dict[str, list[dict]] = defaultdict(list)
    publishers = set()
    own = nlp.name_key(company.name)
    all_items: list[dict] = []
    seen_urls: set[str] = set()
    for q in queries:
        for item in news_search(q, fetcher)[:40]:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            item["query"] = q
            all_items.append(item)
            if item.get("publisher"):
                publishers.add(nlp.name_key(item["publisher"]))
    llm_names = _llm_extract_orgs(all_items[:40]) if use_llm else {}
    trace: list[dict] = []
    for item in all_items:
        title_brands = {e for e in nlp.candidate_entities(item["title"]) if re.search(r"[a-z][A-Z]", e) or (item.get("snippet") and e in item["snippet"])}
        ents = title_brands | set(nlp.candidate_entities(item.get("snippet") or "")) | llm_names.get(item["url"], set())
        for ent in ents:
            key = nlp.name_key(ent)
            if not key or len(key) < 3 or key == own or own in key or GENERIC_ENTITY.match(ent) or key in publishers or NON_COMPANY.search(ent):
                continue
            if ent.split()[0] in nlp.ENTITY_STOP or len(ent.split()) > 4 or (ent.isupper() and len(ent) > 4) or nlp.find_countries(ent) or ent.endswith((".", ",")):
                continue
            if item["url"] not in mentions[key]:
                mentions[key].add(item["url"])
                evidence[key].append({"title": item["title"], "url": item["url"], "publisher": item.get("publisher"), "date": item["published"].date().isoformat() if item.get("published") else None, "query": item["query"]})
            if key not in display or ent in llm_names.get(item["url"], set()):
                display[key] = ent
    # merge keys that are prefixes of each other ("leap" vs "leapscholar")
    ranked = sorted(mentions.items(), key=lambda kv: -len(kv[1]))
    candidates = [(k, v) for k, v in ranked if (len(v) >= 2 or (len(v) == 1 and any(display.get(k) in n for n in llm_names.values()) and False)) and k not in publishers and nlp.domain_of(company.website).split(".")[0] not in k][:24]
    log.info("competitor candidates", extra={"company_id": company.id})

    ptext = profile_text(company)
    emb = nlp.get_embedder()
    existing = {c.name_key: c for c in db.scalars(select(Competitor).where(Competitor.company_id == company.id))}
    results: list[tuple[float, Competitor]] = []
    queue = list(candidates)
    evaluated: set[str] = set()
    terms = core_terms(company)
    while queue and len(evaluated) < 32:
        key, urls = queue.pop(0)
        if key in evaluated:
            continue
        evaluated.add(key)
        name = display[key]
        own_cov = news_search(f'"{name}"', fetcher)[:20]
        own_cov = [a for a in own_cov if key in nlp.name_key(a["title"] + " " + (a.get("snippet") or ""))]
        if len(own_cov) < 2:
            trace.append({"name": name, "co_mentions": len(urls), "own_coverage": len(own_cov), "similarity": None, "llm": None, "decision": "rejected: fewer than 2 independent news items about this name"})
            continue
        texts = [f"{a['title']} {a.get('snippet') or ''}" for a in own_cov]
        person_pat = re.compile(re.escape(name) + r",? (the )?(co-?founder|founder|ceo|cto|coo|chairman|director|head|president|managing director|md)\b|\bsaid " + re.escape(name) + r"\b|\b(mr|ms|mrs|dr)\.? " + re.escape(name) + r"|\b(appoints?|appointed|names?|hires?|elevates?) " + re.escape(name) + r"\b|" + re.escape(name) + r" (as|joins|has joined|appointed)\b", re.I)
        if len(name.split()) in (2, 3) and sum(1 for tx in texts if person_pat.search(tx)) >= 1:
            trace.append({"name": name, "co_mentions": len(urls), "own_coverage": len(own_cov), "similarity": None, "llm": None, "decision": "rejected: evidence describes a person (founder/executive), not an organisation"})
            continue
        if any(key.startswith(r.name_key) or r.name_key.startswith(key) for _, r in results):
            trace.append({"name": name, "co_mentions": len(urls), "own_coverage": len(own_cov), "similarity": None, "llm": None, "decision": "merged: variant of an accepted competitor name"})
            continue
        sims = emb.similarity(ptext, texts)
        sim = sum(sorted(sims, reverse=True)[:5]) / max(1, min(5, len(sims)))
        llm_view = _llm_classify(company, name, [a["title"] for a in own_cov] + [e["title"] for e in evidence[key]]) if use_llm else None
        t = {"name": name, "co_mentions": len(urls), "own_coverage": len(own_cov), "similarity": round(float(sim), 3), "llm": llm_view}
        trace.append(t)
        kind = "direct"
        method = "news_cooccurrence+semantic_validation"
        if llm_view:
            method += "+llm_grounded_classification"
            rel = str(llm_view.get("relationship", "unclear"))
            # The small local LLM is advisory only: it labels kind/description but cannot veto evidence-based candidates,
            # except obvious non-organisations whose coverage is also only weakly related.
            if llm_view.get("is_organisation") is False and sim < 0.6:
                t["decision"] = "rejected: not an organisation (LLM, grounded on headlines) and weak category similarity"
                continue
            kind = "substitute" if rel == "substitute" else "direct"
        if sim < SIM_THRESHOLD:
            # Second chance only for names the grounded LLM judged to be competing organisations: is the name
            # active *in this category*? (ambiguous brand words like "Leap" have unrelated generic coverage)
            ok = False
            if sim >= 0.2 and (llm_view.get("is_organisation") is True) if llm_view else bool(re.search(r"[a-z][A-Z]|\b(Edu|Education|Pay|Labs|Tech|AI|Global|Abroad|Scholar|Cloud|Bank)\b", name)):
                ctx_cov = [a for a in news_search(f'"{name}" {terms[0]}', fetcher)[:20] if key in nlp.name_key(a["title"] + " " + (a.get("snippet") or ""))]
                if len(ctx_cov) >= 2:
                    csims = emb.similarity(ptext, [f"{a['title']} {a.get('snippet') or ''}" for a in ctx_cov])
                    csim = sum(sorted(csims, reverse=True)[:5]) / min(5, len(csims))
                    t["contextual_similarity"] = round(float(csim), 3)
                    if csim >= 0.45:
                        ok, sim, own_cov = True, csim, ctx_cov
                        method += "+contextual_validation"
            if not ok:
                t["decision"] = f"rejected: coverage similarity {sim:.2f} < {SIM_THRESHOLD}"
                continue
        t["decision"] = "accepted"
        # Snowball: organisations co-mentioned in an accepted competitor's own coverage become new candidates
        for a in own_cov:
            for ent in set(nlp.candidate_entities(a.get("snippet") or "")):
                k2 = nlp.name_key(ent)
                if not k2 or len(k2) < 3 or k2 in evaluated or k2 == own or own in k2 or k2 == key or GENERIC_ENTITY.match(ent) or NON_COMPANY.search(ent) or nlp.find_countries(ent) or ent.split()[0] in nlp.ENTITY_STOP or k2 in publishers:
                    continue
                if a["url"] not in mentions[k2]:
                    mentions[k2].add(a["url"])
                    evidence[k2].append({"title": a["title"], "url": a["url"], "publisher": a.get("publisher"), "date": a["published"].date().isoformat() if a.get("published") else None, "query": f'"{name}" (snowball)'})
                display.setdefault(k2, ent)
                if len(mentions[k2]) == 1 and (re.search(r"[a-z][A-Z]|\b(Edu|Education|Pay|Labs|Tech|AI|Global|Abroad|Scholar|Cloud|Bank|Ltd|Inc)\b", ent) or len(ent.split()) >= 2):
                    queue.append((k2, mentions[k2]))
        website, site_desc = _resolve_website(name, own_cov, fetcher)
        confidence = round(min(1.0, 0.45 * sim + 0.08 * len(urls) + (0.15 if website else 0) + (0.1 if llm_view else 0)), 2)
        role_text = " ".join([(llm_view or {}).get("description") or ""] + texts[:5])
        if re.search(re.escape(name) + r"[^.]{0,40}\b(led the round|led by|venture capital|investment firm|invested in|backed)\b|\b(led by|backed by|investors? (including|such as)?) " + re.escape(name), role_text, re.I) or re.search(r"\b(investment firm|venture capital|vc fund|private equity)\b", (llm_view or {}).get("description") or "", re.I):
            t["decision"] = "rejected: evidence describes an investor, not a competitor"
            continue
        description = (llm_view or {}).get("description") or site_desc or (own_cov[0]["title"] if own_cov else evidence[key][0]["title"])
        ev = evidence[key][:4] + [{"title": a["title"], "url": a["url"], "publisher": a.get("publisher"), "date": a["published"].date().isoformat() if a.get("published") else None, "query": f'"{name}"'} for a in own_cov[:4]]
        reason = (
            f"Co-mentioned in {len(urls)} news articles found for category searches ({', '.join(sorted({e['query'] for e in evidence[key]})[:3])}); "
            f"its own news coverage is {sim:.0%} semantically similar to {company.name}'s profile."
        )
        comp = existing.get(key)
        if comp is None:
            comp = Competitor(company_id=company.id, name=name, name_key=key)
            db.add(comp)
        if comp.status == "rejected":
            continue
        comp.website = comp.website or website
        comp.description = description
        comp.kind = kind
        comp.reason = reason
        comp.evidence = ev
        comp.discovery_method = method
        comp.mention_count = len(urls) + len(own_cov)
        comp.confidence = confidence
        results.append((confidence, comp))
        if len(results) >= max_competitors + 4:
            break
    results.sort(key=lambda t: -t[0])
    summary = dict(company.research_summary or {})
    summary["competitor_discovery"] = {"queries": queries, "articles_scanned": len(all_items), "candidates": trace}
    company.research_summary = summary
    keep = [c for _, c in results[:max_competitors]]
    for _, c in results[max_competitors:]:
        if c.id is None:
            db.expunge(c)
    db.flush()
    return keep


def add_founder_competitor(db: Session, company: Company, name: str, source_note: str) -> Competitor:
    key = nlp.name_key(name)
    comp = db.scalar(select(Competitor).where(Competitor.company_id == company.id, Competitor.name_key == key))
    if comp is None:
        comp = Competitor(company_id=company.id, name=name.strip(), name_key=key, discovery_method="founder_interview", reason=source_note, confidence=0.9, evidence=[])
        db.add(comp)
    comp.status = "confirmed"
    if comp.discovery_method != "founder_interview" and "founder" not in (comp.reason or ""):
        comp.reason = (comp.reason or "") + " Confirmed by founder in interview."
    db.flush()
    return comp
