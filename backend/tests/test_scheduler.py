from datetime import datetime, timedelta, timezone

import pytest

from app.core.db import SessionLocal
from app.models import JobRun, ScheduleConfig
from app.services import jobs as jobs_mod
from app.services import scheduler as sch


@pytest.fixture
def running_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    sch._scheduler = BackgroundScheduler(timezone=timezone.utc)
    sch._scheduler.start(paused=True)
    yield sch._scheduler
    sch._scheduler.shutdown(wait=False)
    sch._scheduler = None


def test_schedule_api_validation_and_sync(client, running_scheduler):
    cid = client.post("/api/companies", json={"name": "Acme", "website": "https://acme.example", "run_setup": False}).json()["id"]
    assert client.put(f"/api/companies/{cid}/schedule", json={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.put(f"/api/companies/{cid}/schedule", json={"weekly_time": "25:00"}).status_code == 422
    r = client.put(f"/api/companies/{cid}/schedule", json={"timezone": "America/New_York", "weekly_day_of_week": "mon", "weekly_time": "07:30", "monthly_day": 1, "monthly_time": "06:00"})
    assert r.status_code == 200 and r.json()["timezone"] == "America/New_York"
    jobs = {j["job_type"]: j for j in sch.list_jobs(cid)}
    assert set(jobs) == {"weekly_brief", "monthly_audit", "crawl"}
    nxt = datetime.fromisoformat(jobs["weekly_brief"]["next_run_time"])
    assert nxt.weekday() == 0 and (nxt.hour, nxt.minute) == (7, 30) and str(nxt.tzinfo) in ("America/New_York", "EST", "EDT") or nxt.utcoffset() in (timedelta(hours=-5), timedelta(hours=-4))
    # disabling removes the job; persisted config drives sync
    client.put(f"/api/companies/{cid}/schedule", json={"weekly_enabled": False})
    assert "weekly_brief" not in {j["job_type"] for j in sch.list_jobs(cid)}
    db = SessionLocal()
    assert db.query(ScheduleConfig).filter_by(company_id=cid).one().weekly_enabled is False
    db.close()


def test_last_fire_and_recovery(db, make_company):
    c = make_company()
    c.created_at = datetime.now(timezone.utc) - timedelta(days=40)
    cfg = ScheduleConfig(company_id=c.id, timezone="UTC", weekly_day_of_week="mon", weekly_time="07:00")
    db.add(cfg)
    db.add(JobRun(company_id=c.id, job_type="crawl", status="running"))
    db.commit()
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)  # a Friday
    last = sch.last_fire_before(sch.weekly_trigger(cfg), now, 8)
    assert last == datetime(2026, 11, 9, 7, 0, tzinfo=timezone.utc)
    notes, catchups = sch.recover_on_startup()
    assert any("failed after restart" in n for n in notes)
    assert ("weekly_brief", c.id) in catchups and ("monthly_audit", c.id) in catchups
    db.expire_all()
    run = db.query(JobRun).filter_by(job_type="crawl").one()
    assert run.status == "failed" and "restarted" in run.error


def test_job_runs_record_success_and_failure(db, make_company, monkeypatch):
    c = make_company()
    db.commit()

    def ok(db, company, run, **kw):
        return {"_message": "fine", "value": 1}

    def boom(db, company, run, **kw):
        raise RuntimeError("source exploded")

    monkeypatch.setitem(jobs_mod.JOB_FUNCS, "ok_job", ok)
    monkeypatch.setitem(jobs_mod.JOB_FUNCS, "bad_job", boom)
    a = jobs_mod.start_job("ok_job", c.id, background=False)
    b = jobs_mod.start_job("bad_job", c.id, background=False, trigger="scheduled")
    s = SessionLocal()
    ra, rb = s.get(JobRun, a), s.get(JobRun, b)
    assert ra.status == "success" and ra.message == "fine" and ra.details["value"] == 1 and ra.finished_at
    assert rb.status == "failed" and "source exploded" in rb.error and rb.trigger == "scheduled"
    s.close()


def test_weekly_job_end_to_end_without_network(db, make_company, monkeypatch):
    """Weekly pipeline: crawl (no approved sources) -> brief saved -> run recorded."""
    c = make_company()
    db.commit()
    jid = jobs_mod.start_job("weekly_brief", c.id, background=False, use_llm=False)
    s = SessionLocal()
    run = s.get(JobRun, jid)
    assert run.status == "success", run.error
    assert run.details["brief_id"] and run.details["crawl"]["status"] == "success"
    s.close()


def test_scheduled_trigger_invokes_job(db, make_company, monkeypatch):
    c = make_company()
    db.commit()
    called = []
    monkeypatch.setitem(jobs_mod.JOB_FUNCS, "weekly_brief", lambda db, company, run, **kw: called.append(company.id) or {"_message": "ok"})
    sch._run_scheduled("weekly_brief", c.id)
    assert called == [c.id]
    s = SessionLocal()
    assert s.query(JobRun).filter_by(job_type="weekly_brief").one().trigger == "scheduled"
    s.close()
