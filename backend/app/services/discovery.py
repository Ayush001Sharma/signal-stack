"""Signal Stack source discovery across Customers, Competitors and Market (Internal = uploads).

Every candidate source is *probed* before it is proposed: it is fetched (robots-permitted only), its items
are parsed, recency/update frequency is measured from real publication dates and expected relevance is
computed as semantic similarity between sample items and the company profile. Sources are stored as
``pending`` with a recommendation flag; a user (or the demo script) approves them.
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, Competitor, Source
from app.services import nlp
from app.services.fetcher import FetchError, PoliteFetcher, RobotsDisallowed, get_fetcher
from app.services.research import profile_text
from app.services.search import (
    bing_news_url,
    discover_feed_links,
    federal_register_url,
    govuk_url,
    hackernews,
    hackernews_url,
    news_search,
    parse_feed,
    stackexchange,
    stackexchange_sites,
    stackexchange_url,
)

log = logging.getLogger(__name__)

GOV_SUFFIXES = (".gov", ".gov.uk", ".gc.ca", ".gov.in", ".nic.in", ".gov.au", ".govt.nz", ".europa.eu", ".gov.sg", "federalregister.gov")
# Generic reference data about publisher tiers (not company-specific).
ESTABLISHED_PUBLISHERS = {
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "apnews.com", "bbc.co.uk", "bbc.com", "nytimes.com", "theguardian.com",
    "economictimes.indiatimes.com", "livemint.com", "business-standard.com", "thehindu.com", "moneycontrol.com", "techcrunch.com",
    "theverge.com", "cnbc.com", "forbes.com", "timesofindia.indiatimes.com", "hindustantimes.com", "indianexpress.com", "financialexpress.com",
    "thehindubusinessline.com", "inc42.com", "entrackr.com", "yourstory.com", "thepienews.com", "monitor.icef.org", "universityworldnews.com",
    "timeshighereducation.com", "insidehighered.com", "theregister.com", "zdnet.com", "wired.com", "arstechnica.com", "venturebeat.com",
}
RELEVANCE_THRESHOLD = 0.42


def is_gov(dom: str) -> bool:
    return any(dom == suf.lstrip(".") or dom.endswith(suf if suf.startswith(".") else "." + suf) for suf in GOV_SUFFIXES)


def credibility_for(url: str, source_type: str, company: Company | None = None, competitor: Competitor | None = None) -> tuple[float, str, str]:
    dom = nlp.domain_of(url)
    if is_gov(dom):
        return 0.95, "official", "Official government/regulator publication (primary source)."
    if source_type == "stackexchange":
        return 0.45, "community", "Moderated community Q&A — authentic user language, but individual posts are anecdotal."
    if source_type == "hackernews":
        return 0.4, "community", "Developer community discussion — useful sentiment, anecdotal and unverified."
    if source_type == "reddit":
        return 0.35, "community", "Community forum posts — authentic customer language, unverified claims."
    if source_type in ("news_search", "gdelt"):
        return 0.6, "aggregated", "News-search feed: items come from many publishers; each item's publisher is stored and weighed individually."
    if competitor and competitor.website and nlp.domain_of(competitor.website) == dom:
        return 0.8, "primary", f"{competitor.name}'s own website — authoritative for its own announcements (self-promotional)."
    if company and nlp.domain_of(company.website) == dom:
        return 0.85, "primary", "Company's own website (primary, self-published)."
    if dom in ESTABLISHED_PUBLISHERS:
        return 0.8, "established_media", "Established news/industry publisher with editorial standards."
    return 0.6, "publisher", "Industry publisher; credibility not independently established — corroboration is checked per signal."


def publisher_reliability(publisher: str | None, url: str | None) -> float:
    dom = nlp.domain_of(url or "")
    if is_gov(dom):
        return 0.95
    if dom in ESTABLISHED_PUBLISHERS or any(p in (publisher or "").lower() for p in ("reuters", "bloomberg", "economic times", "mint", "techcrunch", "business standard", "moneycontrol", "the hindu", "financial express", "pie news", "times of india")):
        return 0.8
    if "reddit" in dom or "ycombinator" in dom or "stackexchange" in dom or "stackoverflow" in dom:
        return 0.4
    if any(x in dom for x in ("prnewswire", "businesswire", "globenewswire", "einpresswire", "openpr")):
        return 0.5  # press releases: primary claims, promotional
    return 0.6


def _frequency(dates: list[datetime]) -> str:
    dates = sorted([d for d in dates if d], reverse=True)
    if len(dates) < 2:
        return "unknown"
    gaps = [(dates[i] - dates[i + 1]).total_seconds() / 86400 for i in range(min(len(dates) - 1, 15))]
    med = statistics.median(gaps)
    if med <= 1:
        return "daily"
    if med <= 4:
        return "several per week"
    if med <= 10:
        return "weekly"
    if med <= 40:
        return "monthly"
    return "irregular"


class Prober:
    def __init__(self, company: Company, fetcher: PoliteFetcher):
        self.company = company
        self.fetcher = fetcher
        self.ptext = profile_text(company)
        self.emb = nlp.get_embedder()
        self.keywords = [k.lower() for k in (company.keywords or [])[:20]]

    def score_items(self, items: list[dict]) -> tuple[float, str]:
        if not items:
            return 0.0, "No items returned."
        texts = [f"{i['title']} {i.get('snippet') or ''}"[:600] for i in items[:25]]
        sims = sorted(self.emb.similarity(self.ptext, texts), reverse=True)
        top = sims[: max(3, len(sims) // 2)]
        rel = sum(top) / len(top)
        hits = Counter(k for t in texts for k in self.keywords if k in t.lower())
        why = f"Sample items average {rel:.0%} semantic similarity to the company profile"
        if hits:
            why += "; matched themes: " + ", ".join(k for k, _ in hits.most_common(4))
        return round(float(rel), 3), why + "."

    def probe(self, url: str, kind: str) -> dict | None:
        try:
            if kind in ("stackexchange", "hackernews"):
                res = self.fetcher.get(url)
                data = res.json()
                if kind == "stackexchange":
                    items = [{"title": q["title"], "snippet": nlp.html_to_text(q.get("body", ""))[:300], "published": datetime.fromtimestamp(q["creation_date"], tz=timezone.utc), "url": q["link"]} for q in data.get("items", [])]
                else:
                    items = [{"title": h.get("title") or h.get("story_title") or "", "snippet": nlp.html_to_text(h.get("comment_text") or "")[:300], "published": nlp.parse_date(h.get("created_at")), "url": ""} for h in data.get("hits", [])]
            elif kind == "web_page":
                res = self.fetcher.get(url)
                text = nlp.html_to_text(res.text)
                items = [{"title": text[:200], "snippet": text[:600], "published": None, "url": url}]
            else:
                res = self.fetcher.get(url)
                items = parse_feed(res.text, "news_search" if kind == "news_search" else "rss")
        except (FetchError, RobotsDisallowed, ValueError) as exc:
            log.info("probe failed %s: %s", url, exc)
            return None
        if not items:
            return {"items": [], "count": 0, "relevance": 0.0, "why": "No items returned.", "latest": None, "frequency": "unknown"}
        rel, why = self.score_items(items)
        dates = [i.get("published") for i in items if i.get("published")]
        latest = max(dates) if dates else None
        return {
            "items": items,
            "count": len(items),
            "relevance": rel,
            "why": why,
            "latest": latest,
            "frequency": _frequency(dates) if kind != "web_page" else "page (change detection)",
            "sample": [{"title": i["title"][:160], "url": i.get("url"), "date": i["published"].date().isoformat() if i.get("published") else None} for i in items[:3]],
        }


class Discovery:
    def __init__(self, db: Session, company: Company, fetcher: PoliteFetcher | None = None, discovered_by: str = "discovery"):
        self.db = db
        self.company = company
        self.fetcher = fetcher or get_fetcher()
        self.prober = Prober(company, self.fetcher)
        self.discovered_by = discovered_by
        self.created: list[Source] = []
        self.skipped: list[dict] = []
        self.notes: list[str] = []
        self.existing = {s.normalized_url: s for s in db.scalars(select(Source).where(Source.company_id == company.id))}

    def add(self, *, name: str, url: str, category: str, source_type: str, description: str, reason: str, probe: dict | None,
            competitor: Competitor | None = None, query: str | None = None, config: dict | None = None, min_relevance: float = RELEVANCE_THRESHOLD) -> Source | None:
        norm = nlp.normalize_url(url)
        if norm in self.existing:
            self.skipped.append({"name": name, "url": url, "why": "duplicate of existing source"})
            return None
        if probe is None:
            self.skipped.append({"name": name, "url": url, "why": "unreachable or disallowed by robots.txt"})
            return None
        cred, label, cred_why = credibility_for(url, source_type, self.company, competitor)
        rel = probe["relevance"]
        if competitor is not None:  # competitor sources are relevant by construction; blend
            rel = max(rel, 0.55 if competitor.status == "confirmed" else 0.5)
        latest = probe.get("latest")
        stale = latest is not None and (nlp.now_utc() - latest).days > 180
        recommended = rel >= min_relevance and cred >= 0.4 and probe["count"] > 0 and not stale
        why_not = []
        if rel < min_relevance:
            why_not.append(f"relevance {rel:.0%} below threshold")
        if probe["count"] == 0:
            why_not.append("no items returned")
        if stale:
            why_not.append(f"latest item {latest.date()} is older than 6 months")
        src = Source(
            company_id=self.company.id,
            competitor_id=competitor.id if competitor else None,
            name=name[:300],
            url=url,
            normalized_url=norm,
            category=category,
            source_type=source_type,
            description=description,
            reason=reason,
            query=query,
            credibility=cred,
            credibility_label=label,
            credibility_rationale=cred_why,
            expected_relevance=round(rel, 3),
            relevance_rationale=probe["why"] + (" Not recommended: " + "; ".join(why_not) + "." if why_not else ""),
            update_frequency=probe["frequency"],
            recommended=recommended,
            approval_status="pending",
            discovered_by=self.discovered_by,
            sample_items=probe.get("sample", []),
            config=config or {},
            last_new_item_at=latest,
        )
        self.db.add(src)
        self.db.flush()
        self.existing[norm] = src
        self.created.append(src)
        return src

    # ------------------------------------------------------------ Customers
    def customers(self) -> None:
        c = self.company
        from app.services.competitors import ranked_keywords

        kws = ranked_keywords(c)[:4] or (c.keywords or [])[:3]
        # Stack Exchange: choose communities whose audience matches the company's problem space.
        sites = stackexchange_sites(self.fetcher)
        if sites:
            descs = [f"{s['name']}: {s['audience']}" for s in sites]
            sims = self.prober.emb.similarity(self.prober.ptext, descs)
            ranked = sorted(zip(sims, sites), key=lambda t: -t[0])[:3]
            for sim, site in ranked:
                if sim < 0.25:
                    continue
                for term in kws[:2] + [c.name]:
                    url = stackexchange_url(site["api_site_parameter"], term)
                    probe = self.prober.probe(url, "stackexchange")
                    if probe and probe["count"] >= 2:
                        self.add(
                            name=f"{site['name']} Q&A: “{term}”",
                            url=url,
                            category="customers",
                            source_type="stackexchange",
                            description=f"Questions people ask on {site['name']} ({site['audience']}) about “{term}”.",
                            reason=f"Captures real customer questions and pain points in their own words. Community chosen because its audience is {sim:.0%} similar to {c.name}'s problem space.",
                            probe=probe,
                            query=term,
                            config={"site": site["api_site_parameter"], "query": term},
                            min_relevance=0.35,
                        )
                        break
        else:
            self.notes.append("Stack Exchange API unavailable during discovery.")
        # Hacker News (developer/tech-heavy products)
        for term in [c.name] + kws[:1]:
            url = hackernews_url(term)
            probe = self.prober.probe(url, "hackernews")
            if probe and probe["count"] >= 3 and probe["relevance"] >= 0.35:
                self.add(name=f"Hacker News discussions: “{term}”", url=url, category="customers", source_type="hackernews",
                         description=f"Hacker News stories and comments mentioning “{term}”.",
                         reason="Technical buyers discuss tools, complaints and alternatives here; probe showed relevant recent discussion.",
                         probe=probe, query=term, config={"query": term}, min_relevance=0.35)
        # Customer-problem coverage in news (complaints, problems, expectations)
        for term in kws[:2]:
            for suffix in ("complaints", "problems"):
                q = f"{term} {suffix}"
                url = bing_news_url(q)
                probe = self.prober.probe(url, "news_search")
                if probe and probe["count"] >= 3:
                    self.add(name=f"Customer-problem news: “{q}”", url=url, category="customers", source_type="news_search",
                             description=f"News coverage of customer complaints/problems around “{term}”.",
                             reason=f"Surfaces reported customer pain points and unmet needs in {c.name}'s problem space (secondary reporting, not first-hand reviews).",
                             probe=probe, query=q, config={"query": q})
        # Reddit via official API only
        s = get_settings()
        if not (s.reddit_client_id and s.reddit_client_secret):
            self.notes.append("Reddit not added: reddit.com robots.txt disallows anonymous crawling. Configure REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET (free OAuth app) to enable subreddit monitoring via the official API.")
        founder = (c.profile or {}).get("founder", {})
        for item in founder.get("customer_problems", []):
            for term in nlp.keyphrases([item["answer"]], top_k=2):
                if len(term.split()) < 2:
                    continue
                q = f"{term}"
                url = bing_news_url(q)
                probe = self.prober.probe(url, "news_search")
                if probe and probe["count"] >= 3:
                    self.add(name=f"Founder-identified problem: “{q}”", url=url, category="customers", source_type="news_search",
                             description=f"Coverage of “{term}”, a customer problem named by the founder.", reason="Founder identified this as a top customer problem in the interview.",
                             probe=probe, query=q, config={"query": q}, min_relevance=0.35)

    # ------------------------------------------------------------ Competitors
    def competitors(self, limit: int = 8) -> None:
        comps = list(self.db.scalars(select(Competitor).where(Competitor.company_id == self.company.id, Competitor.status != "rejected").order_by(Competitor.status.asc(), Competitor.confidence.desc())))[:limit]
        for comp in comps:
            q = f'"{comp.name}"'
            url = bing_news_url(q)
            probe = self.prober.probe(url, "news_search")
            if probe:
                # keep only items that actually mention the competitor to compute relevance honestly
                probe["items"] = [i for i in probe["items"] if comp.name_key in nlp.name_key(i["title"] + " " + (i.get("snippet") or ""))]
                probe["count"] = len(probe["items"])
            self.add(name=f"Competitor news: {comp.name}", url=url, category="competitors", source_type="news_search",
                     description=f"News coverage mentioning {comp.name}: launches, pricing, funding, partnerships, hiring, expansion.",
                     reason=f"{comp.name} is a {'founder-confirmed' if comp.status == 'confirmed' else 'discovered'} {comp.kind} competitor. {comp.reason or ''}".strip(),
                     probe=probe, competitor=comp, query=q, config={"query": q, "must_mention": comp.name})
            if comp.website:
                self._competitor_site(comp)

    def _competitor_site(self, comp: Competitor) -> None:
        base = comp.website.rstrip("/")
        try:
            home = self.fetcher.get(base)
        except (FetchError, RobotsDisallowed) as exc:
            self.skipped.append({"name": comp.name, "url": base, "why": str(exc)[:200]})
            return
        feeds = discover_feed_links(home.text, home.final_url)
        if not feeds:
            for path in ("/blog/feed", "/feed", "/rss.xml", "/blog/rss.xml", "/blog/feed.xml", "/feed.xml", "/news/feed"):
                try:
                    r = self.fetcher.get(urljoin(base + "/", path.lstrip("/")))
                    if parse_feed(r.text):
                        feeds = [r.final_url]
                        break
                except (FetchError, RobotsDisallowed):
                    continue
        if feeds:
            url = feeds[0]
            probe = self.prober.probe(url, "rss")
            if probe and probe["count"]:
                self.add(name=f"{comp.name} blog/newsroom feed", url=url, category="competitors", source_type="rss",
                         description=f"Official RSS/Atom feed published by {comp.name}.",
                         reason=f"Primary source for {comp.name}'s own launches, positioning and announcements.", probe=probe, competitor=comp)
                return
        probe = self.prober.probe(home.final_url, "web_page")
        self.add(name=f"{comp.name} website (change monitor)", url=home.final_url, category="competitors", source_type="web_page",
                 description=f"Homepage of {comp.name}, monitored for changes in messaging, offers and positioning.",
                 reason=f"No public feed found; page-change detection reveals {comp.name}'s positioning/offer changes.", probe=probe, competitor=comp)
        # pricing page change monitoring when linked from the homepage
        if "/pricing" in home.text:
            purl = urljoin(home.final_url, "/pricing")
            pprobe = self.prober.probe(purl, "web_page")
            if pprobe:
                self.add(name=f"{comp.name} pricing page (change monitor)", url=purl, category="competitors", source_type="web_page",
                         description=f"{comp.name}'s pricing page.", reason="Detects pricing changes, which directly affect win rates.", probe=pprobe, competitor=comp)

    # ------------------------------------------------------------ Market
    def market(self) -> None:
        c = self.company
        p = c.profile or {}
        from app.services.competitors import ranked_keywords

        kws = ranked_keywords(c)[:5] or (c.keywords or [])[:4]
        industry_short = (c.industry or p.get("industry") or "").split("/")[-1].strip()
        # 1) Topic news feeds (regulation, market, technology, per geography)
        geos = [g for g in p.get("geographies", []) if g not in ("Europe",)][:6]
        topics = []
        if kws:
            topics += [(f"{kws[0]} regulation", "Regulatory developments"), (f"{kws[0]} market trends", "Industry and market trends")]
        if len(kws) > 1:
            topics.append((f"{kws[1]} policy", "Policy changes"))
        if industry_short:
            topics.append((f"{industry_short} industry news", "Industry developments"))
            topics.append((f"{industry_short} AI technology", "Technology changes"))
        for g in geos[:4]:
            if kws:
                topics.append((f"{kws[0]} {g}", f"Country-level developments: {g}"))
        founder = p.get("founder", {})
        for item in founder.get("market_changes", []) + founder.get("risks", []):
            for term in nlp.keyphrases([item["answer"]], top_k=2):
                if len(term.split()) >= 2:
                    topics.append((term, "Founder-identified market change/risk"))
        publisher_counts: Counter[str] = Counter()
        publisher_urls: dict[str, str] = {}
        for q, label in topics[:12]:
            url = bing_news_url(q)
            probe = self.prober.probe(url, "news_search")
            if probe:
                for it in probe["items"]:
                    d = nlp.domain_of(it.get("url") or "")
                    if d:
                        publisher_counts[d] += 1
                        publisher_urls.setdefault(d, it["url"])
            self.add(name=f"{label}: “{q}”", url=url, category="market", source_type="news_search",
                     description=f"News search feed for “{q}”.", reason=f"{label} relevant to {c.name}: query built from its profile ({'founder input' if 'Founder' in label else 'website themes and markets'}).",
                     probe=probe, query=q, config={"query": q})
        # 2) Industry publishers discovered from coverage frequency -> their own RSS feeds
        added = 0
        for dom, n in publisher_counts.most_common(12):
            if n < 2 or added >= 4 or dom in ("bing.com", "msn.com") or dom == nlp.domain_of(c.website):
                continue
            feed_url = self._find_feed(f"https://{dom}")
            if not feed_url:
                continue
            probe = self.prober.probe(feed_url, "rss")
            if probe and probe["count"]:
                src = self.add(name=f"{dom} feed", url=feed_url, category="market", source_type="rss",
                               description=f"RSS/Atom feed of {dom}, a publisher that covered {n} items in {c.name}'s topic searches.",
                               reason=f"Discovered because {dom} published {n} of the articles returned for {c.name}'s industry queries.", probe=probe, min_relevance=0.38)
                if src:
                    added += 1
        # 3) Government / regulatory primary sources matched to geography
        reg_terms = kws[:3]
        if "United States" in geos:
            for term in reg_terms:
                url = federal_register_url(term)
                probe = self.prober.probe(url, "rss")
                if probe and probe["count"] >= 2:
                    self.add(name=f"US Federal Register: “{term}”", url=url, category="market", source_type="federal_register",
                             description=f"US Federal Register documents (rules, proposed rules, notices) matching “{term}”.",
                             reason="Primary regulatory source for the United States, a market referenced on the company website.", probe=probe, query=term, min_relevance=0.35)
                    break
        if "United Kingdom" in geos:
            for term in reg_terms:
                url = govuk_url(term)
                probe = self.prober.probe(url, "rss")
                if probe and probe["count"] >= 2:
                    self.add(name=f"GOV.UK news & guidance: “{term}”", url=url, category="market", source_type="govuk",
                             description=f"UK government announcements and guidance matching “{term}”.",
                             reason="Primary regulatory source for the United Kingdom, a market referenced on the company website.", probe=probe, query=term, min_relevance=0.35)
                    break

    def _find_feed(self, base: str) -> str | None:
        try:
            home = self.fetcher.get(base)
            feeds = discover_feed_links(home.text, home.final_url)
            if feeds:
                return feeds[0]
        except (FetchError, RobotsDisallowed):
            pass
        for path in ("/feed", "/rss", "/feed/"):
            try:
                r = self.fetcher.get(base + path)
                if parse_feed(r.text):
                    return r.final_url
            except (FetchError, RobotsDisallowed):
                continue
        return None

    def run(self, categories: tuple[str, ...] = ("competitors", "customers", "market")) -> dict:
        for cat in categories:
            try:
                getattr(self, cat)()
            except Exception as exc:  # one failing category must not abort discovery
                log.exception("discovery category failed")
                self.notes.append(f"{cat} discovery error: {exc}")
        mark_duplicates(self.db, self.company.id)
        return {
            "created": len(self.created),
            "recommended": sum(1 for s in self.created if s.recommended),
            "by_category": dict(Counter(s.category for s in self.created)),
            "skipped": self.skipped[:50],
            "notes": self.notes,
        }


def mark_duplicates(db: Session, company_id: int) -> list[tuple[int, int]]:
    """Flag sources whose normalized URL or name duplicates an earlier source."""
    srcs = list(db.scalars(select(Source).where(Source.company_id == company_id, Source.approval_status != "removed").order_by(Source.id)))
    seen_url: dict[str, Source] = {}
    seen_name: dict[str, Source] = {}
    pairs = []
    for s in srcs:
        nk = nlp.name_key(s.name)
        first = seen_url.get(s.normalized_url) or seen_name.get(nk)
        if first and first.id != s.id:
            s.duplicate_of_id = first.id
            pairs.append((s.id, first.id))
        else:
            s.duplicate_of_id = None
            seen_url[s.normalized_url] = s
            seen_name[nk] = s
    db.flush()
    return pairs


def discover_sources(db: Session, company: Company, fetcher: PoliteFetcher | None = None, categories=("competitors", "customers", "market"), discovered_by: str = "discovery") -> dict:
    return Discovery(db, company, fetcher, discovered_by).run(categories)
