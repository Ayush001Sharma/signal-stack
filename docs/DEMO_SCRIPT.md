# Demo Walkthrough Script & Screen-Recording Plan (≈ 8 minutes)

**Setup before recording:** backend on :8000, frontend on :3000, Ollama running, three companies already processed by `scripts/run_demo.py`. Use a 1440×900 browser window, dark mode, and zoom to 100%.

| # | Time | Screen | What to show / say |
|---|---|---|---|
| 1 | 0:00–0:30 | README / architecture | "Signal Stack turns a company website into a monitored intelligence system. It runs on a free, open-source stack: FastAPI, Postgres, Next.js and an optional local LLM. Every claim links to evidence." |
| 2 | 0:30–1:15 | **Company Setup** (`/companies/new`) | Enter a *new* company (for example `https://posthog.com`) and submit. Show the live progress (research → competitors → interview → sources) while explaining that nothing is configured by hand. Then switch to **MeetUniversity**, which is already processed. |
| 3 | 1:15–2:00 | **Company Profile** | Show the status badges (verified with source link and snippet, unverified news, AI assumption, needs confirmation), the name-collision exclusion in the research summary, and an inline edit of a fact. |
| 4 | 2:00–2:50 | **Adaptive Interview** | Show the 10 questions and the "why we ask" rationale that cites research (products, Study-in-country pages, discovered competitors). Answer one question as *Founder* to show a follow-up being generated, and skip one as confidential. Switch the company selector to Razorpay to show its very different questions. |
| 5 | 2:50–3:40 | **Signal Stack** + **Source Manager** | Walk the four categories. On one source, show its reason, credibility rationale, measured relevance, update frequency and sample items. In the Source Manager, demonstrate approve/reject, pause, crawl history, duplicates and **Add source**: a duplicate URL gives 409, and a robots-blocked site gives 422. |
| 6 | 3:40–4:30 | **Intelligence Feed** | Filter by Competitors, high priority and a date range. Open **Why this score** to show the weighted components, their reasons and the formula. Point out that reliability, evidence strength and relevance are separate, and that the interpretation is labelled as rules or AI. Click the evidence link to open the original article. |
| 7 | 4:30–5:00 | **Competitor Intelligence** | Show the discovered competitors with their evidence links, the discovery method and confidence, and confirm or reject one. |
| 8 | 5:00–6:15 | **Monday Morning Brief** | Scroll through the 10 sections: executive summary, customer signals, competitor intelligence, market (material vs general), internal (labelled SYNTHETIC data), opportunities, risks, actions with owner and status tracking, the watch list and the appendix. Click an `[S#]` reference, then export the PDF and Markdown. |
| 9 | 6:15–6:45 | **Internal Uploads** | Upload a CSV and show the themes with quotes, the win-rate pattern and the internal signals it produced. |
| 10 | 6:45–7:30 | **Automation** + **Source Health** | Show the weekly and monthly jobs with their next run times and timezone, the execution history including a failed or interrupted run, Run now, and the latest audit with dead/duplicate/inactive sources and recommendations. |
| 11 | 7:30–8:00 | **Context change** (Supabase profile) + **Settings** | Show the stored context-change report with relevance before/after, flagged sources and new proposals, then the system panel (LLM model, embeddings, auth mode, robots policy). Close: "No fabricated data. Limitations are documented in the project audit." |

**Recording tips:** use OBS or the built-in OS recorder at 1080p and 30 fps, with the microphone on. Keep sections tight and use the prepared data so you don't wait on crawls. Start the new-company setup in step 2 early so its progress is visible later.
