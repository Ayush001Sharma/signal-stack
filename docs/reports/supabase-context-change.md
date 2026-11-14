# Context-change stress test — Supabase

*Hypothetical stress-test context, reverted after the reassessment is recorded.*

## What changed

Business context updated. 7 new themes (developers building llm, vector database, rag applications, pgvector embeddings, application backend) now lead source discovery. Relevance was re-scored for 39 sources: 16 gained, 4 lost relevance; 0 flagged as no longer useful; 12 new sources proposed.

- **Before:** industry `None`, context `None`
- **After:** industry `Developer tools / AI infrastructure`, context: “Vector database and AI application backend for developers building LLM and RAG applications with pgvector embeddings, semantic search and AI agents.”
- **New themes leading discovery:** developers building llm, vector database, rag applications, pgvector embeddings, application backend, semantic, agents

## Approved sources flagged as no longer useful

- None

## Relevance re-scored (largest losses and gains)

| Source | Before | After | Δ |
|---|---|---|---|
| Industry and market trends: “postgres development market trends” | 1.00 | 0.92 | -0.08 |
| Firebase pricing page (change monitor) | 0.35 | 0.27 | -0.08 |
| Founder-identified market change/risk: “cloud pricing competition” | 0.31 | 0.24 | -0.07 |
| Founder-identified problem: “public forums” | 0.09 | 0.06 | -0.03 |
| pgEdge pricing page (change monitor) | 0.38 | 0.35 | -0.03 |
| Postgres website (change monitor) | 0.22 | 0.21 | -0.01 |
| seekingalpha.com feed | 0.06 | 0.06 | -0.01 |
| Policy changes: “open source policy” | 0.29 | 0.28 | -0.01 |
| Salesforce Q&A: “open source” | 0.02 | 0.02 | -0.00 |
| Firebase website (change monitor) | 0.30 | 0.30 | -0.00 |
| note.com feed | 0.00 | 0.00 | +0.00 |
| Founder-identified market change/risk: “push developers” | 0.14 | 0.14 | +0.00 |
| Competitor news: Altinity | 0.60 | 0.64 | +0.04 |
| Altinity blog/newsroom feed | 0.37 | 0.41 | +0.04 |
| Competitor news: EDB | 0.73 | 0.77 | +0.04 |
| Competitor news: Firebase | 0.56 | 0.60 | +0.04 |
| pgEdge website (change monitor) | 0.35 | 0.40 | +0.05 |
| Technology changes: “SaaS AI technology” | 0.53 | 0.59 | +0.05 |
| Hacker News discussions: “Supabase” | 0.24 | 0.29 | +0.06 |
| Regulatory developments: “postgres development regulation” | 0.80 | 0.85 | +0.06 |
| EDB website (change monitor) | 0.13 | 0.19 | +0.07 |
| Founder-identified market change/risk: “open-source licensing changes” | 0.28 | 0.35 | +0.07 |
| siliconangle.com feed | 0.13 | 0.22 | +0.09 |
| Founder-identified market change/risk: “serverless database” | 0.30 | 0.42 | +0.12 |

## New sources proposed for the new context (1)

- **Software Recommendations Q&A: “vector database”** (customers, expected relevance 43%, not recommended) — Captures real customer questions and pain points in their own words. Community chosen because its audience is 57% similar to Supabase's problem space.

## Revert to the original (research-only) context

Business context updated. 0 new themes (none) now lead source discovery. Relevance was re-scored for 40 sources: 4 gained, 17 lost relevance; 2 flagged as no longer useful; 12 new sources proposed.

Retired themes: developers building llm, vector database, rag applications, pgvector embeddings, application backend, semantic, agents

The 1 sources proposed for the hypothetical context were rejected after the revert.
