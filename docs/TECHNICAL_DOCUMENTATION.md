# Signal Stack — Technical Documentation

*Company Intelligence & Executive Briefing Engine · EDXSO AI Engineer Intern Assignment 1 · (≈5 pages)*

## 1. Architecture

Signal Stack is a **modular monolith**: one FastAPI process (API + in-process APScheduler) backed by PostgreSQL, and a Next.js dashboard. No queues, Redis or microservices are needed at this scale; long jobs run in background threads and every run is persisted as a `JobRun` row.

```
 Next.js 14 dashboard (TypeScript, Tailwind, shadcn-style UI, Recharts)
          │  REST/JSON (OpenAPI at /docs)
 FastAPI ─┼─ api/        companies · interview · sources · signals · briefs · audits · jobs · uploads · dashboard
          ├─ services/
          │   research.py      website crawl → provenance-tracked profile facts
          │   competitors.py   dynamic competitor discovery from news co-mentions (+ grounded LLM)
          │   interview.py     10 research-grounded questions, follow-ups, profile updates
          │   discovery.py     probes & proposes Customer/Competitor/Market sources with justification
          │   fetcher.py       polite HTTP: robots.txt, per-host rate limit, retries, caching, size cap
          │   search.py        robots-permitted indexes: Bing News RSS, GDELT, Stack Exchange, HN, Federal Register, GOV.UK
          │   crawler.py       monitoring engine: fetch → normalise → dedup → version → store evidence
          │   analysis.py      classification + explainable scoring + interpretation
          │   internal.py      CSV/XLSX/PDF/TXT upload parsing → recurring themes → internal signals
          │   briefs.py        Monday Morning Brief (JSON + Markdown + HTML + PDF)
          │   audit.py         monthly Signal Stack audit + business-context reassessment
          │   jobs.py / scheduler.py   persistent job runs, cron schedules from DB, restart recovery
          │   llm.py / nlp.py  optional local LLM (Ollama) · embeddings (MiniLM) with TF-IDF fallback
          └─ PostgreSQL 16 (SQLAlchemy 2 + Alembic migrations)
```

**Data model (16 tables).** `companies`, `profile_facts` (statement + status + origin + source URL + evidence), `interview_questions`, `competitors`, `sources`, `crawl_runs`, `crawl_logs` (per-source attempt history), `raw_items` (evidence exactly as collected, versioned), `signals` (analysis of a raw item), `internal_documents`, `briefs`, `brief_actions` (action tracking), `audit_reports`, `context_changes`, `job_runs`, `schedule_configs`. Every company-owned row carries `company_id`; every API route resolves the company first and returns 404 for objects owned by another company (tenant isolation, tested).

**Evidence vs interpretation.** `raw_items` are never modified by analysis. `signals` reference their raw item and store interpretation (`why_it_matters`, `recommended_action`, `interpretation_method = rules | llm`) separately from evidence (`evidence_url`, `evidence_snippet`, `publisher`, dates). The original rule-based interpretation is kept in `score_breakdown.rule_interpretation` even when the LLM rewrites it, so AI output can always be audited against the deterministic baseline.

## 2. Company research & adaptive interview

1. **Website research** (`research.py`): the homepage plus up to 7 prioritised internal pages (about, product, services, pricing, solutions, blog, press, careers) are fetched politely. Extracted: meta description/H1 (positioning), offering headings (products/services), segment lexicon matches with ≥2 mentions, country mentions, contact data, advertised RSS feeds, business-model wording cues, keyphrases (heading/meta zones re-ranked by semantic similarity to the company's core description).
2. **Provenance statuses**: `verified` (quoted from the company's own site with URL + snippet, or stated by the founder/user), `unverified` (third-party news), `assumption` (rule/AI inference such as business model or industry classification), `needs_confirmation` (important but not public: revenue mix, segment value, operating vs. destination markets). An optional local-LLM one-line summary is always stored as an `assumption` labelled with the model name.
3. **Public developments**: news results for the company name/domain are kept only if they semantically match the profile; name collisions (e.g. *"Meet University's new Fulbright scholars"* for MeetUniversity) are excluded and listed in `research_summary.name_collisions_excluded`.
4. **Interview** (`interview.py`): exactly ten topics (revenue streams, high-value customers, customer problems, differentiation, competitors, market changes, risks, growth priorities, internal data, decisions). Each question is produced by a research-grounded builder that references the company's own products, segments, markets, discovered competitors and public developments, and stores a *rationale* (why it was asked). If Ollama is available the LLM may phrase the question, but its output is accepted only when it references at least one researched specific. Answers create profile facts (founder → `verified`; team member / demo operator → `assumption`, explicitly labelled), confirm or reject competitors named by the founder, add geographies and keyphrases that steer discovery. Follow-ups are generated (LLM or rules) only for brief or information-rich answers, at most one per question and five per interview, and are rejected if TF-IDF similarity to any earlier question exceeds 0.55. Skips are stored as confidential `needs_confirmation` facts; edits replace the previous fact.

## 3. Source discovery (Signal Stack generation)

Nothing is hard-coded per company: every query is built from the researched profile and interview answers, and **every candidate source is probed** (fetched, parsed, dated and scored) before it is proposed.

| Category | How candidates are found | Source types |
|---|---|---|
| **Competitors** | `competitors.py`: up to 28 category queries built from the most specific keyphrases (ranked by similarity to industry/positioning) × {startup, platform, raises funding, launches, acquires, competitors, rivals, app, consultants, …} plus the company's home market; organisation names extracted from sentence-case descriptions (and camel-case brands) plus grounded LLM extraction whose names must appear verbatim; co-mentions counted across distinct articles; **acceptance requires ≥2 independent news items about the candidate whose content is ≥38 % similar to the profile** (a context-qualified second check is allowed only when general similarity ≥ 0.2 and the LLM agrees it is an organisation). Persons (founder/CEO/"appoints X" patterns), investors ("led by", "venture capital"), generic words and name variants are rejected; accepted competitors' coverage is snowballed for further candidates. The small LLM is advisory only — it cannot veto evidence. Every decision is stored in `research_summary.competitor_discovery` (queries, articles scanned, per-candidate similarity and decision). Website accepted only if the fetched page title contains the name. Discovered competitors start as `suggested`; founder-named ones are `confirmed`. | competitor news feed (Bing News RSS, filtered to items that mention the competitor), competitor RSS/newsroom, homepage/pricing page change monitor |
| **Customers** | Stack Exchange communities chosen by semantic similarity between the company's problem space and each site's audience; Hacker News when discussion is relevant; customer-problem news queries; founder-named problems | `stackexchange`, `hackernews`, `news_search`, `reddit` (official OAuth API only) |
| **Market** | profile-derived topic queries (regulation, policy, market trends, technology, per-country); **publishers discovered by frequency** in those results whose own RSS feed is then found and probed; government primary sources selected by the company's markets (US Federal Register API, GOV.UK search Atom) | `news_search`, `rss`, `federal_register`, `govuk` |
| **Internal** | uploads (CSV/XLSX/PDF/TXT) | documents |

Each source stores: name, URL, category, description, **reason for inclusion**, credibility score + label + rationale (official / primary / established media / publisher / aggregated / community), **expected relevance** (mean semantic similarity of sampled items to the profile, with matched themes), update frequency (median gap between real publication dates), approval status, recommendation flag (relevance ≥ 0.42, credibility ≥ 0.4, items present, latest item < 6 months), health, last check/success, consecutive failures, last error and duplicate link. Users approve/reject, add manually (probed + robots-checked + duplicate-checked), remove (soft remove keeps history), pause/resume, check now, and inspect crawl history and collected items.

**Compliance decisions.** Google News RSS (`news.google.com/robots.txt` disallows `/rss`), anonymous Reddit (`Disallow: /`), Apple App Store review feeds and Trustpilot are **not** crawled because their robots.txt disallows automated agents. Reddit is supported through its official free OAuth API when credentials are configured.

## 4. Crawling & monitoring

`crawler.py` processes approved, active sources one by one, each inside its own `try/except` **and database savepoint**. A failing fetch or storage error in one source is rolled back and logged, and never aborts the run. `fetcher.py` enforces robots.txt (cached 1 h), a per-host minimum delay (1.5 s default; 3 s Bing, 6 s GDELT), 20 s timeouts, ≤2 retries with exponential backoff for 429/5xx/timeouts (honouring `Retry-After`), no retries for DNS/connection-refused, a 3 MB response cap, conditional GET (ETag / Last-Modified → 304), and a 15-minute in-memory cache. No authentication, paywall or CAPTCHA bypass exists anywhere in the code.

Per item: duplicate entries within one feed are collapsed; canonical URL (tracking parameters stripped) → `url_hash`; `content_hash` of title+body; **new** if URL unseen, **modified** (stored as version n+1, history preserved) if the hash changed, skipped if identical; cross-source duplicates (same normalised title within 45 days) are linked via `duplicate_of_id` and increase the original signal's corroboration count and evidence strength. Publication dates come from feed metadata, HTML meta, JSON-LD or `<time>`; `date_source` records which. Web pages are monitored by **baseline snapshot + line-level diff** (added/removed lines stored as evidence). Source health moves `healthy → degraded → failing` (3 consecutive failures), `dead` on 404/410/DNS failure, `blocked` on robots disallow. Each attempt is stored in `crawl_logs` (status, HTTP code, items, new/changed, duration, error).

## 5. Intelligence analysis & explainable ranking

For each new record (`analysis.py`): signal type by transparent regex rules restricted per category (e.g. competitors: funding, acquisition, pricing, product launch, partnership, expansion, hiring, technology, complaint; market: regulation, economic, technology, trend; customers: complaint, unmet need, question, pricing), competitor linkage, polarity (opportunity/threat/neutral from category-specific rules plus VADER sentiment), business area and suggested owner.

**Priority = 100 × (0.30·relevance + 0.25·impact + 0.15·urgency + 0.10·source credibility + 0.10·recency + 0.10·novelty)** — High ≥ 60, Medium ≥ 45.

| Component | Computation (stored with a human-readable reason) |
|---|---|
| Relevance (strategic) | 0.5·semantic similarity to profile + 0.2·keyword-theme hits + 0.15·entity match (company/competitor, or market country) + 0.15·similarity to founder priorities/risks |
| Impact | base by signal type (regulation 0.8, pricing 0.75, acquisition 0.75 …) +0.10 quantified (money/%) +0.10 founder-confirmed competitor +0.10 high community engagement +0.10 large page change |
| Urgency | 0.2 + 0.3·recency +0.30 time-sensitive language ("effective from", "deadline", "cap", "ban") +0.15 regulation/pricing −0.20 if > 60 days old |
| Credibility | per-publisher reliability for news-search items (official 0.95, established 0.8, press release 0.5, community 0.4, other 0.6); source credibility otherwise |
| Recency | exp(−age/21 days); 0.5 if undated |
| Novelty | 1 − max TF-IDF similarity to signals of the last 60 days |

Three measures are deliberately **separate**: *source reliability* (who published it), *evidence strength* (verification type: official 0.9, observed page change 0.8, primary 0.75, single report 0.45–0.7, community 0.35; +date, +substantive snippet, +0.1 per corroborating publisher) and *strategic relevance*. Verification statuses: `official_primary`, `primary_source`, `corroborated`, `single_source_report`, `community_claim`, `observed_change`, `internal_document`. A signal is *meaningful* only if relevance ≥ 0.38 and it is ≤ 120 days old; community posts must additionally match a business theme, a competitor or the company itself (a country-name match alone is not enough). Non-meaningful records are kept for audit but excluded from briefs. `POST /signals/reanalyze` rebuilds all signals from stored evidence when rules or the profile change. Market items are split into *material* (relevance ≥ 0.5 and impact ≥ 0.5) vs *general* context. The LLM never sets scores; `ai_confidence` is not used as evidence. LLM interpretations are applied only to external signals and only if they pass a **grounding check**: every number and proper name in the generated text must appear in the evidence or company profile it was given, otherwise the rule-based interpretation is kept. The brief narrative is deterministic, because free-form LLM summaries proved prone to unsupported claims in testing.

## 6. Monday Morning Brief

`briefs.py` selects meaningful signals published in the look-back window (default 14 days; undated items by discovery date), collapses duplicate stories, and builds the ten required sections in fixed order. Executive Summary = top 5 by priority with ≤ 2 per category; Opportunities/Risks by polarity (a note states when fewer than three evidence-backed opportunities exist); Recommended Actions de-duplicated from the highest-priority opportunities/risks/summary items with suggested owner by business area (tracked in `brief_actions`); Watch list = weak-evidence relevant items, founder-stated risks without evidence, unhealthy sources; Source Appendix = every cited item with link, publisher, publication and discovery dates, snippet, verification status, reliability, evidence strength and relevance. Empty sections state so explicitly. Uploaded documents whose name or description marks them as **synthetic** are shown only in section 5 under a "SYNTHETIC TEST DATA" banner and never feed the executive summary, opportunities, risks or actions. Exports: web view, Markdown, print-friendly HTML (email-ready), PDF (xhtml2pdf).

## 7. Automation & reliability

Two independent cron jobs per company — **Weekly Intelligence Brief** (crawl → analyse → optional LLM enrichment → brief → save) and **Monthly Signal Stack Audit** (availability/dead URLs, duplicates, inactive > 45 days, declining relevance, new-source discovery, add/remove recommendations, source-health report) — plus an interval monitoring crawl. Schedules (timezone, day, time, interval, look-back) live in `schedule_configs`, are validated (IANA timezone, HH:MM) and re-applied on startup. On restart, runs left `running` are marked failed ("interrupted by restart"), and a missed weekly/monthly run is caught up once (`trigger = startup_recovery`). APScheduler uses `coalesce`, `max_instances=1`, 6 h misfire grace; an in-process guard prevents concurrent runs of the same job for a company. Every run (manual, scheduled, recovery) is a `JobRun` with status, message, error trace and details — failures appear on the dashboard.

**Context change** (`POST /companies/{id}/context`): new context keyphrases lead the keyword list, every source's relevance is re-scored against the new profile (before/after recorded), non-competitor sources below 33 % are flagged as no longer useful, and discovery proposes new sources; the change and its explanation are stored in `context_changes`.

## 8. Engineering quality

Pydantic validation on every input; centralised exception handlers (409 integrity, 422 validation, 500 generic without stack leakage); structured JSON logging; Alembic migrations; per-request transactions (commit/rollback) and explicit transactions in jobs; pagination on list endpoints; `/health` and `/health/ready` (DB + scheduler); optional API-key auth (`X-API-Key`, constant-time compare) with open local-demo mode documented; uploads validated by extension, magic bytes, encoding, size (10 MB), stored under per-company folders with random names; secrets only via environment variables. Test suite: see `docs/TEST_RESULTS.md`.
