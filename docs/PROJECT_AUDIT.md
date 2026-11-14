# Final Project Audit — Signal Stack

*Audit date: 2026-11-14. All numbers come from `python scripts/acceptance_metrics.py` against the demonstration database, not from estimates.*

## 1. Acceptance checklist

| # | Requirement | Status | Evidence / explanation |
|---|---|---|---|
| 1 | Company setup (name, website, optional industry and context) | **PASS** | `POST /api/companies` and the `/companies/new` page. Validation: 409 on duplicate domain, 422 on invalid input. Tests: `test_onboarding.py`. |
| 2 | Research with verified / unverified / AI assumption / needs-confirmation separation | **PASS** | `services/research.py` stores every fact with status, origin, source URL and snippet. In the profile UI, MeetUniversity's research excluded a name-collision news item ("Meet University's new Fulbright scholars"). Tests: `test_research.py`. |
| 3 | 10 adaptive questions, one at a time, follow-ups, no repeats, skip, edit, profile update | **PASS** | Each company got 10 primary questions plus 3 follow-ups. Questions cite each company's own offerings, competitors and markets (see the interview screenshot, and compare company 1 with company 2). Duplicate follow-ups are blocked at TF-IDF similarity > 0.55. Tests: `test_interview.py` (5). |
| 4 | Questions differ between companies, not hard-coded | **PASS** | Builders fill topic templates with researched specifics, and LLM phrasing is accepted only when it is grounded. Test `test_questions_are_ten_grounded_and_company_specific` asserts zero overlap between two companies. |
| 5 | Four Signal Stack categories | **PASS** | Customers, Competitors and Market sources are discovered and probed; Internal comes from uploads (`/signal-stack` page). |
| 6 | Customer sources capture real customer language, never synthetic | **PARTIAL** | Real questions and comments come from Stack Exchange and Hacker News, plus customer-problem news, all labelled "community claim". Reddit, app-store and Trustpilot reviews are **not** crawled because robots.txt disallows it; Reddit is supported via its official API once the user adds credentials. MeetUniversity therefore has thin first-hand customer evidence: only 2 meaningful customer items fell in the 14-day window. |
| 7 | 5–10 dynamically discovered competitors | **PASS** (with review) | MeetUniversity has 5 after review (upGrad, Leverage Edu, Western Overseas Study Abroad, PhysicsWallah, Utkarsh Classes). Razorpay has 10 (Stripe, PhonePe, PayPal, Google Pay, Gr4vy, Sunrate, QuickBooks Payments, Coinbase, Zelle, ZBD). Supabase has 8 (Firebase, ClickHouse, pgEdge, EDB, EnterpriseDB, Altinity, Postgres, OpenAI). All are discovered from news co-mentions and validated against their own coverage; nothing is hard-coded, and every decision is traced in `research_summary.competitor_discovery`. Precision is imperfect: 4 obvious non-competitors (a person, a university office, an investor, a generic term) were rejected in the review step with reasons recorded in `demo/companies.json`, and some accepted entries are ecosystem players rather than direct rivals (for example OpenAI and Coinbase). All remain `suggested` until a founder confirms them. |
| 8 | Market: regulatory, economic, technology, government; generic vs material | **PASS** | Profile-derived topic feeds, publishers discovered by coverage frequency, and US Federal Register / GOV.UK feeds selected by market. Every brief splits "Material" from "General context". |
| 9 | Internal: CSV / XLSX / PDF / TXT; objections, lost deals, requests, patterns, risks; isolation | **PASS** | `services/internal.py`. MeetUniversity has 16 internal themes (win rate, lost-deal reasons, conversion by destination). Tests: `test_uploads.py` covers all 4 formats, validation and cross-company isolation. Demo files are **synthetic and labelled as such**. |
| 10 | Source metadata (reason, credibility, relevance, frequency, health, approval…) | **PASS** | `sources` table and Source Manager UI. Relevance and frequency are *measured* from probed items. |
| 11 | Approve, reject, add, remove, pause/resume, crawl history, errors, duplicates | **PASS** | Source Manager and API. Tests: `test_discovery.py` (approval API, manual add with duplicate/robots checks, isolation). |
| 12 | At least 20 approved MeetUniversity sources | **PASS** | 27 approved (customers 7, competitors 6, market 14), each with a stored reason for inclusion. |
| 13 | Real crawling: RSS first, change detection, dates, dedup, history, snippets, retries, robots, rate limits | **PASS** | 236 crawl attempts logged with 0 failed fetches; versioned evidence records; web-page diffs. Tests: `test_crawler.py` (10), including failure isolation and three regression tests for bugs found in live runs. |
| 14 | At least 30 actual intelligence records | **PASS** | 1,777 external evidence records were collected (282 MeetUniversity, 388 Razorpay, 1,107 Supabase), giving 266 meaningful external signals after the final re-scoring. All external signals link to their original URL (279/279, 378/378, 1,096/1,096). Full numbers: `docs/ACCEPTANCE_METRICS.txt`. |
| 15 | Analysis fields (what, when, source, dates, snippet, verification, reliability, strength, relevance, impact, urgency, novelty, area, polarity, action, why) | **PASS** | `signals` table; the feed UI shows them along with "Why this score". |
| 16 | Transparent ranking; separate reliability / evidence strength / relevance; AI confidence is not proof | **PASS** | Fixed weighted formula with a stored per-component reason. The LLM never scores, and LLM text must pass a grounding check. Tests: `test_analysis.py`. |
| 17 | Monday Brief with the exact 10 sections, evidence, empty-state honesty, ≥3 opportunities where supported | **PASS** | `docs/reports/*-monday-brief.md/.pdf`. Test `test_brief_structure_and_evidence` checks section order. Supabase's market section states that nothing material was found rather than inventing items. |
| 18 | Web view, history, Markdown, PDF, print-friendly | **PASS** | Brief page, Reports History, `/markdown`, `/pdf` and `/html` endpoints, and a print stylesheet. |
| 19 | Weekly scheduler (automatic plus manual) | **PASS** | APScheduler cron per company in the configured timezone, plus "Generate brief now". Tests: `test_scheduler.py` (5). |
| 20 | Monthly audit (dead, duplicate, inactive, declining, new sources, recommendations, report) | **PASS** | `docs/reports/*-source-audit.md`. Tests: `test_audit.py`. |
| 21 | Failed jobs visible; config persisted; restart recovery | **PASS** | Real failures are visible in Automation and on the Overview, for example "Interrupted by application restart" and the crawler bug fixed during the build. Interrupted jobs are marked failed and missed runs are caught up. |
| 22 | Context change reassesses sources and explains what changed | **PASS** | `docs/reports/supabase-context-change.md`: re-scored relevance before and after, flagged sources, new proposals, then a revert. |
| 23 | Three companies from different industries with different outputs | **PASS** | MeetUniversity (study-abroad services), Razorpay (fintech/payments) and Supabase (developer tools) have distinct profiles, questions, competitors, sources and briefs. |
| 24 | Frontend: 14 pages, polished, functional buttons, filters, search | **PASS** | `frontend/`. `npm run build` and `npm run lint` are clean; screenshots are in `docs/screenshots/`. |
| 25 | Engineering: validation, error handling, logging, migrations, auth option, secure uploads, pagination, health, API docs | **PASS** | Covered in technical documentation §8, with 3 Alembic migrations and `/docs`. |
| 26 | Tests run and pass | **PASS** | 50 backend tests passing (`docs/TEST_RESULTS.md`), plus clean frontend lint and type-check. |
| 27 | Docker / compose / .env.example / README | **PARTIAL** | Files are written and follow standard patterns, but `docker compose up` could **not be executed** here because the build container has no Docker daemon. The local, non-Docker setup in the README was verified end to end. |
| 28 | Deployed URL | **NOT DONE** | No hosting credentials were available. A local deployment is documented; no deployment is claimed. |
| 29 | Screen recording | **NOT DONE (user action)** | A recording cannot be produced from this environment. A timed script is in `docs/DEMO_SCRIPT.md`. |
| 30 | MeetUniversity founder interview | **PARTIAL** | No real founder was available. Answers were entered as `answered_by=demo_operator`, so they are stored as labelled assumptions and never as verified facts. Confidential and unknown questions were skipped. |

## 2. Issues found and fixed during verification (not hidden)
- **Python-side column defaults read before flush** created NULL interview questions. Fixed, with a test.
- **`gov.uk` domain matching** missed official sources. Fixed, with a test.
- **Competitor discovery returned 0 competitors** for MeetUniversity on the first live run. Queries were too generic and title-case headlines produced junk entities. Rebuilt with specificity-ranked queries, entity extraction from sentence-case descriptions, a minimum of 2 independent coverage items, person/investor/variant filters and decision tracing.
- **The local 3B LLM vetoed real competitors and introduced unsupported claims** into brief narratives (for example, a win-rate claim for the US that the data did not support). The LLM was made advisory only. Interpretations must now pass a grounding check, and the narrative is deterministic.
- **Synthetic demo CRM data dominated the executive summary.** Synthetic documents are now confined to section 5 behind a banner.
- **Irrelevant Hacker News job threads counted as customer signals** because they matched only on country names. Community posts now need a business-theme match.
- **The crawler failed whole runs with a unique-key violation** when a feed alternated between two snippet versions, and the savepoint rollback was skipped after a failed flush. Fixed, with three regression tests that fail on the old code.
- **Novelty scoring was O(n²)**, making large batches slow. It is now computed once per batch.

## 3. Known limitations
1. **News coverage is limited.** Bing News RSS, the robots-permitted index, returns about 10–15 items per query. GDELT was unreachable from the build network, and Google News RSS is disallowed by robots.txt. A licensed news API would raise recall.
2. **Customer voice.** There is no first-hand review data without official API keys (Reddit) or permission (app stores, Trustpilot).
3. **Competitor precision.** Discovery can include ecosystem players or adjacent brands. They stay `suggested` until a human confirms them.
4. **Small local LLM.** On CPU, `qwen2.5:3b` is slow (setup takes about 15–30 minutes per company while discovery is LLM-bound) and unreliable, which is why it is advisory only. Everything works with `LLM_PROVIDER=none`.
5. **Interpretations are rule-based.** They connect the evidence to the company's themes, products and markets, but are less nuanced than an analyst's. Every one is labelled as rules or AI.
6. **Single process.** The scheduler runs in-process, so run one API worker. This is documented.
7. **Docker was not executed** here (no daemon), and **there is no deployment and no recording**, as noted above.
