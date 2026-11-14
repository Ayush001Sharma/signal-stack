# Cost Statement — Signal Stack

**Total running cost: $0.** Every component is free and open source, or a free public endpoint used within its published terms. No paid API, paid scraping service or paid AI service is used, and no API key is required to run the full product.

| Layer | Technology | Licence / cost | Notes and limitations |
|---|---|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, APScheduler, HTTPX, BeautifulSoup4, lxml, feedparser | MIT / BSD / Apache-2.0 — free | — |
| Database | PostgreSQL 16 | PostgreSQL licence — free | Self-hosted (Docker or local). |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Radix UI (shadcn-style components), Recharts, lucide-react | MIT / ISC — free | — |
| Local LLM (optional) | Ollama + `qwen2.5:3b` (Apache-2.0) | Free, runs on CPU | Approx. 10–12 tokens/s on 4 CPU cores. Used only to phrase questions, extract organisation names that must appear verbatim in evidence, and rewrite interpretations of top signals. Set `LLM_PROVIDER=none` to disable; every feature keeps working through deterministic fallbacks. |
| Embeddings (optional) | sentence-transformers `all-MiniLM-L6-v2` (Apache-2.0), CPU PyTorch | Free | Downloaded once from Hugging Face (~90 MB). Without it the app falls back to TF-IDF similarity (scikit-learn). |
| NLP | scikit-learn TF-IDF, VADER sentiment, rapidfuzz | Free | Rule-based classification is transparent but less nuanced than a large model. |
| Reports | Markdown, xhtml2pdf (PDF) | Free | — |
| News discovery | Bing News RSS (`/news/search?format=rss`, allowed by bing.com/robots.txt) | Free public feed | Returns about 10–15 items per query, with occasional throttling. Its terms limit use to personal, non-commercial RSS reading, so production commercial use would need a licensed news API. |
| News fallback | GDELT DOC 2.0 API | Free, open | Limited to 1 request per 5 s. It was unreachable from the build environment (connection reset), so a circuit breaker skips it for 30 minutes after a failure. |
| Customer discussions | Stack Exchange API (no key), Hacker News Algolia API | Free | Stack Exchange allows 300 requests/day per IP without a key; a free key raises this to 10,000. |
| Regulatory | US Federal Register API, GOV.UK search Atom feeds | Free, official | — |
| Reddit (optional) | Official Reddit OAuth API | Free tier (non-commercial, 100 QPM) | Requires the user to create a free app and set `REDDIT_CLIENT_ID/SECRET`. Anonymous crawling is not used because reddit.com/robots.txt disallows it. |
| Deployment | Docker / Docker Compose | Free | No paid hosting is required. A free-tier cloud deployment was not performed because no hosting account credentials were available. |

**Deliberately not used (robots.txt or terms):** Google News RSS (`/rss` is disallowed for automated agents), anonymous Reddit, Apple App Store review RSS, Trustpilot, LinkedIn, Glassdoor.
