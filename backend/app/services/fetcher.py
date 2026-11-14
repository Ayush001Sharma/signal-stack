"""Polite HTTP fetcher used by research, discovery, crawling and audits.

Guarantees:
* robots.txt is checked (and cached) for every URL before fetching; disallowed URLs are never requested.
* A minimum delay is enforced between requests to the same host (rate limiting).
* Timeouts, bounded retries with exponential backoff for transient errors (429/5xx/network).
* Conditional requests (ETag / Last-Modified) and a short in-memory response cache.
* Response-size cap. No authentication, paywall or CAPTCHA bypass is attempted.
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    pass


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    headers: dict = field(default_factory=dict)
    not_modified: bool = False
    from_cache: bool = False
    elapsed_ms: int = 0

    def json(self):
        import json

        return json.loads(self.text)


# Hosts that publish explicit request-rate guidance get a larger delay.
HOST_DELAYS = {
    "api.gdeltproject.org": 6.0,
    "www.bing.com": 3.0,
    "api.stackexchange.com": 1.0,
    "hn.algolia.com": 1.0,
}


class PoliteFetcher:
    def __init__(self, user_agent: str | None = None, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.settings = s
        self.user_agent = user_agent or s.crawler_user_agent
        self._client = httpx.Client(
            timeout=httpx.Timeout(s.request_timeout_seconds),
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml,application/atom+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en;q=0.9",
            },
            transport=transport,
        )
        self._robots: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None]] = {}
        self._last_request: dict[str, float] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._cache: dict[str, tuple[float, FetchResult]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ robots
    def _host_lock(self, host: str) -> threading.Lock:
        with self._lock:
            return self._host_locks.setdefault(host, threading.Lock())

    def robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        now = time.time()
        cached = self._robots.get(base)
        if not cached or now - cached[0] > 3600:
            rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
            try:
                self._throttle(parsed.netloc)
                r = self._client.get(base + "/robots.txt", timeout=10)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                else:  # 404 etc -> everything allowed
                    rp.parse([])
            except httpx.ConnectError as exc:
                raise FetchError(f"{type(exc).__name__}: {exc}") from exc
            except httpx.HTTPError:
                rp = None  # robots unreachable: be conservative only if the site itself is unreachable
            self._robots[base] = (now, rp)
            cached = self._robots[base]
        rp = cached[1]
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    # ------------------------------------------------------------------ throttle
    def _throttle(self, host: str) -> None:
        base = self.settings.per_host_delay_seconds
        delay = HOST_DELAYS.get(host, base) if base > 0 else 0.0
        lock = self._host_lock(host)
        with lock:
            last = self._last_request.get(host, 0.0)
            wait = last + delay - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_request[host] = time.time()

    # ------------------------------------------------------------------ fetch
    def get(
        self,
        url: str,
        params: dict | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        check_robots: bool = True,
        use_cache: bool = True,
        headers: dict | None = None,
    ) -> FetchResult:
        req = httpx.Request("GET", url, params=params)
        full_url = str(req.url)
        if check_robots and not self.robots_allowed(full_url):
            raise RobotsDisallowed(f"robots.txt disallows fetching {full_url}")
        now = time.time()
        if use_cache and not etag and not last_modified:
            hit = self._cache.get(full_url)
            if hit and now - hit[0] < self.settings.http_cache_ttl_seconds:
                res = hit[1]
                return FetchResult(**{**res.__dict__, "from_cache": True})
        hdrs = dict(headers or {})
        if etag:
            hdrs["If-None-Match"] = etag
        if last_modified:
            hdrs["If-Modified-Since"] = last_modified
        host = urlparse(full_url).netloc
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.settings.max_retries:
            self._throttle(host)
            t0 = time.time()
            try:
                with self._client.stream("GET", full_url, headers=hdrs) as r:
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > self.settings.max_response_bytes:
                            break
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    status = r.status_code
                    enc = r.encoding or "utf-8"
                    resp_headers = {k.lower(): v for k, v in r.headers.items()}
                    final_url = str(r.url)
                elapsed = int((time.time() - t0) * 1000)
                if status == 304:
                    return FetchResult(full_url, final_url, status, "", resp_headers, not_modified=True, elapsed_ms=elapsed)
                if status in (429, 500, 502, 503, 504) and attempt < self.settings.max_retries:
                    retry_after = resp_headers.get("retry-after")
                    backoff = min(float(retry_after), 30.0) if retry_after and retry_after.isdigit() else 2.0 * (2**attempt)
                    log.info("transient status, retrying", extra={"url": full_url})
                    time.sleep(backoff)
                    attempt += 1
                    continue
                if status >= 400:
                    raise FetchError(f"HTTP {status} for {full_url}", status)
                try:
                    text = body.decode(enc, errors="replace")
                except LookupError:
                    text = body.decode("utf-8", errors="replace")
                res = FetchResult(full_url, final_url, status, text, resp_headers, elapsed_ms=elapsed)
                if use_cache:
                    self._cache[full_url] = (time.time(), res)
                return res
            except httpx.HTTPError as exc:
                last_exc = exc
                # DNS failures / refused connections are not transient: fail fast.
                if isinstance(exc, httpx.ConnectError) and not isinstance(exc, httpx.ConnectTimeout):
                    raise FetchError(f"{type(exc).__name__}: {exc}") from exc
                if attempt < self.settings.max_retries:
                    time.sleep(2.0 * (2**attempt))
                    attempt += 1
                    continue
                raise FetchError(f"{type(exc).__name__}: {exc}") from exc
        raise FetchError(str(last_exc) if last_exc else "fetch failed")

    def head_ok(self, url: str) -> tuple[bool, int | None, str | None]:
        """Lightweight availability check used by audits (GET fallback because many servers reject HEAD)."""
        try:
            r = self.get(url, use_cache=False)
            return True, r.status, None
        except RobotsDisallowed as e:
            return False, None, str(e)
        except FetchError as e:
            return False, e.status, str(e)

    def close(self) -> None:
        self._client.close()


_shared: PoliteFetcher | None = None
_shared_lock = threading.Lock()


def get_fetcher() -> PoliteFetcher:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = PoliteFetcher()
        return _shared
