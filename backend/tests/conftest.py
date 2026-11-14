"""Test configuration: isolated Postgres test database, no network, no LLM, TF-IDF embeddings."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://signal:signal@localhost:5432/signalstack_test")
os.environ["LLM_PROVIDER"] = "none"
os.environ["EMBEDDINGS_BACKEND"] = "tfidf"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["PER_HOST_DELAY_SECONDS"] = "0"
os.environ["MAX_RETRIES"] = "0"
os.environ["UPLOAD_DIR"] = "/tmp/signalstack-test-uploads"
os.environ["API_KEY"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.services.fetcher import PoliteFetcher  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


class FakeWeb:
    """Routes URL -> (status, body, headers). Unknown URLs return 404. robots.txt allows all unless set."""

    def __init__(self):
        self.routes: dict[str, tuple[int, str, dict]] = {}
        self.calls: list[str] = []

    def add(self, url: str, body: str, status: int = 200, headers: dict | None = None):
        self.routes[url] = (status, body, headers or {"content-type": "text/html"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if url in self.routes:
            st, body, h = self.routes[url]
            return httpx.Response(st, text=body, headers=h)
        base = url.split("?")[0]
        for key, (st, body, h) in self.routes.items():
            if key.endswith("*") and url.startswith(key[:-1]):
                return httpx.Response(st, text=body, headers=h)
        if base.endswith("/robots.txt"):
            return httpx.Response(404, text="")
        return httpx.Response(404, text="not found")

    def fetcher(self) -> PoliteFetcher:
        return PoliteFetcher(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def web():
    return FakeWeb()


def rss(items: list[dict], title: str = "Feed") -> str:
    parts = [f'<?xml version="1.0"?><rss version="2.0"><channel><title>{title}</title>']
    for it in items:
        parts.append(f"<item><title>{it['title']}</title><link>{it['link']}</link><description>{it.get('desc', '')}</description><pubDate>{it.get('date', 'Mon, 09 Nov 2026 08:00:00 GMT')}</pubDate></item>")
    parts.append("</channel></rss>")
    return "".join(parts)


@pytest.fixture
def make_company(db):
    from app.models import Company

    def _make(name="Acme Study", website="https://acme.example", **kw):
        c = Company(name=name, website=website, domain=website.split("//")[1], profile=kw.pop("profile", {}), keywords=kw.pop("keywords", []), research_summary={}, **kw)
        db.add(c)
        db.flush()
        return c

    return _make
