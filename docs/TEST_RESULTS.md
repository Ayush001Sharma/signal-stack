# Test Results

Run: `cd backend && PYTHONPATH=. pytest -v` on 2026-11-13 against PostgreSQL 16 (isolated `signalstack_test` database). Network access is mocked with `httpx.MockTransport`, and the LLM is disabled so tests are deterministic. All tests exercise real code paths, including real HTTP parsing, database transactions, the scheduler and the FastAPI routes; nothing is stubbed out to force a pass.

| Area | Tests |
|---|---|
| Company onboarding | test_onboarding.py (3) |
| Research | test_research.py (3): provenance statuses, unreachable site, robots.txt respected |
| Competitor discovery | test_competitors.py (1): dynamic discovery, unrelated co-mention rejected, website verification |
| Interview generation & persistence | test_interview.py (5): 10 grounded questions that differ per company, follow-ups, edit, skip, demo answers not verified, API flow |
| Source discovery & approval | test_discovery.py (6): credibility rules, recommendation, duplicates, competitor sources, approval/pause/remove API, robots/duplicate/isolation on manual add |
| Crawling & deduplication | test_crawler.py (10): new/unchanged/modified versions, cross-source corroboration, failure isolation (404 → dead, robots → blocked), paused sources, web-page change detection |
| Classification & ranking | test_analysis.py (7): grounding check, community/hiring-thread gates, type rules, score = weighted formula, separate measures, novelty, competitor polarity |
| Report generation | test_briefs.py (4): synthetic-data isolation, 10 sections in order, evidence appendix, empty-state honesty, Markdown/PDF/HTML exports, action tracking, isolation |
| File uploads | test_uploads.py (3): CSV/XLSX/TXT/PDF extraction, validation (type, magic bytes, empty, size), company isolation |
| Scheduling | test_scheduler.py (5): validation, cron sync in timezone, restart recovery and catch-up, job success/failure records, end-to-end weekly job |
| Source audits | test_audit.py (3): dead/duplicate/inactive detection, failed job visible on dashboard, context-change re-scoring |

Frontend: `npm run lint` → **No ESLint warnings or errors**; `npm run build` → **compiled successfully** (strict TypeScript).

## Output

```
tests/test_analysis.py::test_classify_type_rules PASSED                  [  2%]
tests/test_analysis.py::test_scores_are_explainable_and_ranked PASSED    [  4%]
tests/test_analysis.py::test_novelty_penalises_repeats PASSED            [  6%]
tests/test_analysis.py::test_competitor_signal_polarity PASSED           [  8%]
tests/test_analysis.py::test_llm_grounding_check PASSED                  [ 10%]
tests/test_analysis.py::test_community_post_needs_business_theme PASSED  [ 12%]
tests/test_analysis.py::test_hiring_threads_are_not_customer_signals PASSED [ 14%]
tests/test_audit.py::test_monthly_audit_detects_dead_duplicate_inactive PASSED [ 16%]
tests/test_audit.py::test_audit_api_and_failed_job_visibility PASSED     [ 18%]
tests/test_audit.py::test_context_change_reassesses_sources PASSED       [ 20%]
tests/test_briefs.py::test_brief_structure_and_evidence PASSED           [ 22%]
tests/test_briefs.py::test_empty_brief_states_no_developments PASSED     [ 24%]
tests/test_briefs.py::test_brief_api_exports_and_actions PASSED          [ 26%]
tests/test_briefs.py::test_synthetic_internal_data_is_confined_to_section_5 PASSED [ 28%]
tests/test_competitors.py::test_competitors_discovered_dynamically_with_evidence PASSED [ 30%]
tests/test_crawler.py::test_crawl_stores_new_items_dedups_and_versions PASSED [ 32%]
tests/test_crawler.py::test_cross_source_duplicate_story_corroborates PASSED [ 34%]
tests/test_crawler.py::test_failures_do_not_crash_run PASSED             [ 36%]
tests/test_crawler.py::test_paused_sources_are_skipped PASSED            [ 38%]
tests/test_crawler.py::test_web_page_change_detection PASSED             [ 40%]
tests/test_crawler.py::test_duplicate_entries_in_one_feed_are_stored_once PASSED [ 42%]
tests/test_crawler.py::test_storage_error_in_one_source_is_isolated PASSED [ 44%]
tests/test_crawler.py::test_flapping_content_does_not_duplicate PASSED   [ 46%]
tests/test_crawler.py::test_news_search_snippet_variation_is_not_a_modification PASSED [ 48%]
tests/test_crawler.py::test_real_db_constraint_violation_is_isolated PASSED [ 50%]
tests/test_discovery.py::test_normalize_url_and_credibility PASSED       [ 52%]
tests/test_discovery.py::test_discovery_add_recommends_and_dedupes PASSED [ 54%]
tests/test_discovery.py::test_mark_duplicates_by_name PASSED             [ 56%]
tests/test_discovery.py::test_competitor_sources_discovered_from_competitors PASSED [ 58%]
tests/test_discovery.py::test_source_approval_api PASSED                 [ 60%]
tests/test_discovery.py::test_manual_source_add_duplicate_and_isolation PASSED [ 62%]
tests/test_interview.py::test_questions_are_ten_grounded_and_company_specific PASSED [ 64%]
tests/test_interview.py::test_answer_updates_profile_and_creates_followup PASSED [ 66%]
tests/test_interview.py::test_competitor_answer_and_skip PASSED          [ 68%]
tests/test_interview.py::test_interview_api_flow PASSED                  [ 70%]
tests/test_interview.py::test_non_founder_answers_are_not_verified PASSED [ 72%]
tests/test_onboarding.py::test_create_company_and_validation PASSED      [ 74%]
tests/test_onboarding.py::test_update_and_delete_company PASSED          [ 76%]
tests/test_onboarding.py::test_health PASSED                             [ 78%]
tests/test_research.py::test_research_builds_provenance_tracked_profile PASSED [ 80%]
tests/test_research.py::test_research_handles_unreachable_site PASSED    [ 82%]
tests/test_research.py::test_robots_disallow_is_respected PASSED         [ 84%]
tests/test_scheduler.py::test_schedule_api_validation_and_sync PASSED    [ 86%]
tests/test_scheduler.py::test_last_fire_and_recovery PASSED              [ 88%]
tests/test_scheduler.py::test_job_runs_record_success_and_failure PASSED [ 90%]
tests/test_scheduler.py::test_weekly_job_end_to_end_without_network PASSED [ 92%]
tests/test_scheduler.py::test_scheduled_trigger_invokes_job PASSED       [ 94%]
tests/test_uploads.py::test_csv_upload_extracts_patterns PASSED          [ 96%]
tests/test_uploads.py::test_xlsx_txt_and_pdf_uploads PASSED              [ 98%]
tests/test_uploads.py::test_upload_validation_and_isolation PASSED       [100%]
============================== 50 passed in 9.17s ==============================
```
