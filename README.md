# Signal Stack — Company Intelligence & Executive Briefing Engine

Signal Stack turns a company name and website into a continuously monitored intelligence system. It **researches** the company and separates verified facts from assumptions. It runs a **10-question adaptive founder interview**, **discovers and justifies** sources across Customers, Competitors, Market and Internal data, and **crawls** approved sources politely, respecting robots.txt and rate limits. It then **analyses and ranks** developments with an explainable score and produces a **Monday Morning Intelligence Brief** in which every item links back to its evidence. A weekly brief job and a monthly source-audit job run on a schedule.

> Built for the EDXSO AI Engineer Intern Assignment 1. Free and open-source stack only, with no mandatory API keys. See [docs/COST_STATEMENT.md](docs/COST_STATEMENT.md).

## Contents
- [Quick start (Docker)](#quick-start-docker)
- [Local development setup](#local-development-setup)
- [Reproducing the demonstration](#reproducing-the-demonstration)
- [How it works](#how-it-works)
- [Repository structure](#repository-structure)
- [Documentation & deliverables](#documentation--deliverables)
- [Limitations](#limitations)

## Quick start (Docker)

```bash
git clone https://github.com/ayush001sharma/signal-stack.git && cd signal-stack
docker compose up --build -d                      # postgres + backend (runs migrations) + frontend
# optional local LLM:
docker compose --profile llm up -d ollama && docker compose exec ollama ollama pull qwen2.5:3b
```

- Dashboard: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs · ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health/ready

## Local development setup

Prerequisites: Python 3.12+, Node 20+, PostgreSQL 16. Ollama is optional.

```bash
# 1. Database
sudo -u postgres psql -c "CREATE USER signal WITH PASSWORD 'signal' SUPERUSER;"
sudo -u postgres createdb -O signal signalstack
sudo -u postgres createdb -O signal signalstack_test      # for the test suite

# 2. Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# optional, better semantic relevance (CPU):
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements-ml.txt
cp .env.example .env                                      # edit if needed
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000           # single worker: the scheduler runs in-process

# 3. Optional local LLM
ollama serve & ollama pull qwen2.5:3b

# 4. Frontend
cd ../frontend
cp .env.example .env.local                                # NEXT_PUBLIC_API_URL=http://localhost:8000
npm ci && npm run build && npm run start -- -p 3000
```

Run the tests (with Postgres running):

```bash
cd backend && PYTHONPATH=. pytest -q
```

### Configuration
All settings are environment variables; see [`backend/.env.example`](backend/.env.example). The main ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://signal:signal@localhost:5432/signalstack` | PostgreSQL connection |
| `API_KEY` | *(empty)* | When set, every `/api` call needs header `X-API-Key`. Empty = local-demo mode (no auth) — do not expose publicly without it. |
| `LLM_PROVIDER` / `OLLAMA_MODEL` | `ollama` / `qwen2.5:3b` | Optional local LLM; `none` disables it (deterministic fallbacks are used) |
| `EMBEDDINGS_BACKEND` | `auto` | sentence-transformers if installed, else TF-IDF |
| `PER_HOST_DELAY_SECONDS`, `MAX_RETRIES`, `REQUEST_TIMEOUT_SECONDS` | 1.5 / 2 / 20 | Crawler politeness |
| `REDDIT_CLIENT_ID/SECRET` | *(empty)* | Optional official Reddit API (anonymous crawling is disallowed by robots.txt) |
| `DEFAULT_TIMEZONE`, `SCHEDULER_ENABLED` | `Asia/Kolkata`, `true` | Scheduling |

## Reproducing the demonstration

With the backend running:

```bash
python scripts/run_demo.py                 # MeetUniversity, Razorpay, Supabase end-to-end
python scripts/run_demo.py --only MeetUniversity
python scripts/context_stress_test.py --company Supabase   # hypothetical context change → reassessment report → revert
python scripts/acceptance_metrics.py                       # acceptance numbers straight from the database
```

The script uses only the public REST API, the same calls the dashboard makes. For each company it:

1. Creates the company, which runs setup: research → competitor discovery → 10 interview questions → source discovery.
2. Answers the interview as a demo operator. These answers are **labelled and stored as assumptions, never as founder facts**. Questions only a founder could answer are skipped as confidential.
3. Approves the recommended sources.
4. Uploads the clearly labelled `SYNTHETIC_DEMO_*` internal files.
5. Runs the weekly pipeline (crawl → analyse → rank → brief) and the monthly audit.
6. Separately, `scripts/context_stress_test.py` applies a hypothetical business context, records how source relevance, flags and proposals change, and then reverts it.

Reports are written to [`docs/reports/`](docs/reports/).

To run monitoring and briefs manually:

```bash
curl -X POST localhost:8000/api/companies/1/crawl
curl -X POST localhost:8000/api/companies/1/briefs -H 'content-type: application/json' -d '{}'
curl -X POST localhost:8000/api/companies/1/audits
```

The dashboard has the same actions: **Run crawl now**, **Generate brief now** and **Run audit now**. Each returns a `job_run_id`, which you can follow at `GET /api/jobs/{id}`.

## How it works

| Stage | Module | Highlights |
|---|---|---|
| Research | `services/research.py` | Crawls the homepage and up to 7 priority pages. Every fact gets a status (`verified` / `unverified` / `assumption` / `needs_confirmation`) plus its source URL and evidence snippet. News with a matching name but unrelated content is excluded. |
| Competitors | `services/competitors.py` | Builds category queries from the profile, extracts organisation names that co-occur in the results, and validates each candidate against its own coverage. Websites are accepted only when the page title matches the name. Nothing is hard-coded. |
| Interview | `services/interview.py` | Ten topic questions grounded in the research, each with a rationale. Follow-ups are capped and de-duplicated. Questions can be skipped as confidential, answers can be edited, and answers update the profile. |
| Source discovery | `services/discovery.py` | Every candidate is probed before it is proposed. Each source records its reason, credibility rationale, measured relevance and update frequency, and gets a recommendation flag. |
| Monitoring | `services/crawler.py`, `fetcher.py` | Checks robots.txt and rate-limits per host. Uses ETag/Last-Modified, retries, deduplication and versioning, and detects web-page changes. Source health is tracked, and one failing source does not stop the run. |
| Analysis | `services/analysis.py` | Explainable priority score: 0.30 relevance, 0.25 impact, 0.15 urgency, 0.10 credibility, 0.10 recency, 0.10 novelty. Source reliability, evidence strength and strategic relevance are stored separately. |
| Brief | `services/briefs.py` | The 10 required sections. Empty sections say so explicitly. Every item has a source appendix entry, and briefs export to Markdown, HTML and PDF. |
| Internal | `services/internal.py` | CSV, XLSX, PDF and TXT uploads are parsed into objections, lost deals, product requests, recurring problems, operational risks and sales patterns. |
| Automation | `services/scheduler.py`, `jobs.py` | Weekly brief and monthly audit cron jobs per company, plus a monitoring crawl. Schedules are stored in the database. On restart the scheduler recovers and catches up missed runs. Every run is recorded. |

Full detail: [docs/TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md).

## Repository structure

```
backend/            FastAPI app (app/api, app/services, app/models.py), Alembic migrations, tests/
frontend/           Next.js 14 dashboard (14 pages)
demo/               companies.json (demo inputs) + SYNTHETIC internal files and generator
scripts/run_demo.py reproducible end-to-end demonstration driver
docs/               technical docs, cost statement, reports, screenshots, test results, demo script, audit
docker-compose.yml  postgres + backend + frontend (+ optional ollama)
```

## Documentation & deliverables
- [Technical documentation](docs/TECHNICAL_DOCUMENTATION.md): architecture, discovery, crawling, ranking, AI analysis, scheduling and reliability
- [Cost statement](docs/COST_STATEMENT.md)
- [Sample reports](docs/reports/): Monday Briefs (Markdown and PDF), source audits and the context-change report
- [Test results](docs/TEST_RESULTS.md)
- [Screenshots](docs/screenshots/)
- [Demo walkthrough & screen-recording plan](docs/DEMO_SCRIPT.md)
- [Final project audit / acceptance checklist](docs/PROJECT_AUDIT.md)

## Limitations
See [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md) for the full, honest list. The main limitations:

- **News coverage is limited.** The robots-permitted news index (Bing News RSS) returns about 10–15 items per query, and Google News RSS is not used because its robots.txt disallows automated agents.
- **No real customer reviews.** Reddit, app-store reviews and Trustpilot are not crawled without official API access.
- **Synthetic internal data.** The demo's internal files are synthetic and labelled as such, because no real company data was available.
- **No founder interview.** No real founders were interviewed, so the demo answers are entered as a labelled demo operator.
