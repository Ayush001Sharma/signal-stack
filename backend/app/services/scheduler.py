"""APScheduler integration. Schedules live in the database (ScheduleConfig) and are re-applied on startup,
so configuration survives restarts. Runs missed while the app was down are caught up once on startup
(coalesced), and runs left 'running' by a crash are marked failed and visible in the dashboard.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Company, JobRun, ScheduleConfig, utcnow
from app.services.jobs import JobAlreadyRunning, ensure_schedule, start_job

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_scheduled(job_type: str, company_id: int) -> None:
    try:
        start_job(job_type, company_id, trigger="scheduled", background=False)
    except JobAlreadyRunning:
        log.warning("scheduled job skipped: already running", extra={"job": job_type, "company_id": company_id})
    except Exception:
        log.exception("scheduled job errored", extra={"job": job_type, "company_id": company_id})


def weekly_trigger(cfg: ScheduleConfig) -> CronTrigger:
    h, m = (int(x) for x in cfg.weekly_time.split(":"))
    return CronTrigger(day_of_week=cfg.weekly_day_of_week, hour=h, minute=m, timezone=cfg.timezone)


def monthly_trigger(cfg: ScheduleConfig) -> CronTrigger:
    h, m = (int(x) for x in cfg.monthly_time.split(":"))
    return CronTrigger(day=cfg.monthly_day, hour=h, minute=m, timezone=cfg.timezone)


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def sync_company(cfg: ScheduleConfig) -> None:
    if _scheduler is None:
        return
    cid = cfg.company_id
    for jid in (f"weekly_brief:{cid}", f"monthly_audit:{cid}", f"crawl:{cid}"):
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)
    if cfg.weekly_enabled:
        _scheduler.add_job(_run_scheduled, weekly_trigger(cfg), id=f"weekly_brief:{cid}", args=["weekly_brief", cid], name=f"Weekly Intelligence Brief (company {cid})", replace_existing=True)
    if cfg.monthly_enabled:
        _scheduler.add_job(_run_scheduled, monthly_trigger(cfg), id=f"monthly_audit:{cid}", args=["monthly_audit", cid], name=f"Monthly Signal Stack Audit (company {cid})", replace_existing=True)
    if cfg.crawl_enabled and cfg.crawl_interval_hours:
        _scheduler.add_job(_run_scheduled, IntervalTrigger(hours=cfg.crawl_interval_hours, timezone=cfg.timezone), id=f"crawl:{cid}", args=["crawl", cid], name=f"Source monitoring crawl (company {cid})", replace_existing=True)


def remove_company(company_id: int) -> None:
    if _scheduler is None:
        return
    for jid in (f"weekly_brief:{company_id}", f"monthly_audit:{company_id}", f"crawl:{company_id}"):
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)


def last_fire_before(trigger: CronTrigger, now: datetime, window_days: int) -> datetime | None:
    t = trigger.get_next_fire_time(None, now - timedelta(days=window_days))
    last = None
    while t is not None and t <= now:
        last = t
        t = trigger.get_next_fire_time(t, t + timedelta(seconds=1))
    return last


def recover_on_startup() -> list[str]:
    """Mark interrupted runs failed; compute missed runs to catch up."""
    notes = []
    now = utcnow()
    catchups: list[tuple[str, int]] = []
    with session_scope() as db:
        for run in db.scalars(select(JobRun).where(JobRun.status.in_(["running", "queued"]))):
            run.status = "failed"
            run.error = "Interrupted: application restarted while the job was running."
            run.message = "Interrupted by application restart"
            run.finished_at = now
            notes.append(f"marked job {run.id} ({run.job_type}) failed after restart")
        settings = get_settings()
        for company in db.scalars(select(Company)):
            cfg = ensure_schedule(db, company, settings.default_timezone)
            for job_type, enabled, trig, window in (("weekly_brief", cfg.weekly_enabled, weekly_trigger(cfg), 8), ("monthly_audit", cfg.monthly_enabled, monthly_trigger(cfg), 32)):
                if not enabled:
                    continue
                due = last_fire_before(trig, now, window)
                if due is None or due < company.created_at:
                    continue
                last_ok = db.scalar(select(JobRun.started_at).where(JobRun.company_id == company.id, JobRun.job_type == job_type, JobRun.trigger.in_(["scheduled", "startup_recovery"]), JobRun.status.in_(["success", "partial"])).order_by(JobRun.started_at.desc()).limit(1))
                if last_ok is None or last_ok < due:
                    catchups.append((job_type, company.id))
                    notes.append(f"catch-up {job_type} for company {company.id} (missed {due.isoformat()})")
    return notes, catchups


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        log.info("scheduler disabled by configuration")
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone=timezone.utc, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 6 * 3600})
    notes, catchups = recover_on_startup()
    with session_scope() as db:
        for cfg in db.scalars(select(ScheduleConfig)):
            sync_company(cfg)
    _scheduler.start()
    for n in notes:
        log.info(n)

    def _catchup():
        for job_type, cid in catchups:
            try:
                start_job(job_type, cid, trigger="startup_recovery", background=False)
            except Exception:
                log.exception("catch-up failed")

    if catchups:
        threading.Timer(90, _catchup).start()
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def list_jobs(company_id: int | None = None) -> list[dict]:
    if _scheduler is None:
        return []
    out = []
    for j in _scheduler.get_jobs():
        cid = int(j.id.split(":")[1])
        if company_id and cid != company_id:
            continue
        out.append({"id": j.id, "name": j.name, "job_type": j.id.split(":")[0], "company_id": cid, "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None, "trigger": str(j.trigger)})
    return sorted(out, key=lambda x: x["next_run_time"] or "")
