from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time
from collections import deque
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from veritylake.config import Settings
from veritylake.text import extract_html
from veritylake.util import digest, utcnow

log = logging.getLogger(__name__)


class CrawlPolicyError(RuntimeError):
    pass


class CrawlBackoffError(CrawlPolicyError):
    pass


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise CrawlPolicyError("Only absolute HTTP(S) URLs are supported")
    if parsed.username or parsed.password:
        raise CrawlPolicyError("Credentials in source URLs are forbidden")
    if parsed.query:
        raise CrawlPolicyError("Query-string URLs are disabled to avoid crawl traps and accidental secrets")
    decoded = unquote(unquote(parsed.path))
    if "\\" in decoded or any(p in (".", "..") for p in decoded.split("/")) or any(ord(c) < 32 for c in decoded):
        raise CrawlPolicyError("Ambiguous path")
    host = parsed.hostname.lower()
    netloc = f"[{host}]" if ":" in host else host
    port = parsed.port
    if port and port != (443 if parsed.scheme.lower() == "https" else 80):
        netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))


class URLPolicy:
    def __init__(self, settings: Settings, resolver=socket.getaddrinfo):
        self.settings = settings
        self.seed = canonical_url(settings.source_url)
        self.origin = urlsplit(self.seed)[:2]
        self.resolver = resolver

    def check(self, value: str, robots: bool = False) -> str:
        value = canonical_url(value)
        p = urlsplit(value)
        if p[:2] != self.origin:
            raise CrawlPolicyError("Cross-origin crawling and redirects are forbidden")
        prefix = self.settings.source_path_prefix
        if not robots and not p.path.startswith(prefix):
            raise CrawlPolicyError("Outside configured path prefix")
        if not self.settings.allow_private_sources:
            try:
                addresses = self.resolver(p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
            except OSError as exc:
                raise CrawlPolicyError("DNS lookup failed") from exc
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise CrawlPolicyError("Non-public destination address")
        return value


class Crawler:
    """Bounded, same-origin crawler. DNS checks are defense-in-depth, not an egress firewall."""
    def __init__(self, settings: Settings, client: httpx.Client | None = None,
                 resolver=socket.getaddrinfo, sleep=time.sleep, monotonic=time.monotonic):
        self.settings = settings
        self.policy = URLPolicy(settings, resolver)
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(settings.http_timeout_seconds), follow_redirects=False,
            headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml"},
            trust_env=False,
        )
        self.owns_client = client is None
        self.sleep, self.clock = sleep, monotonic
        self.next_request = 0.0
        self.interval = settings.request_interval_seconds
        self.robots = RobotFileParser()
        self.robots_document = {}

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def _wait(self) -> None:
        delay = self.next_request - self.clock()
        if delay > 0:
            self.sleep(delay)
        self.next_request = self.clock() + self.interval

    def _retry_after(self, value: str | None, attempt: int) -> float:
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
                except (ValueError, TypeError):
                    pass
        return float(2 ** attempt)

    def _request(self, url: str, robots_request: bool = False) -> tuple[httpx.Response, bytes]:
        for redirect in range(4):
            url = self.policy.check(url, robots=robots_request)
            if not robots_request and not self.robots.can_fetch(self.settings.user_agent, url):
                raise CrawlPolicyError("Disallowed by robots.txt")
            for attempt in range(3):
                self._wait()
                with self.client.stream("GET", url) as response:
                    if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
                        delay = self._retry_after(response.headers.get("Retry-After"), attempt)
                        if delay > self.settings.max_retry_wait_seconds:
                            # Do not cap Retry-After and crawl early. Abort and let the operator reschedule.
                            raise CrawlBackoffError("Origin requested a delay beyond this run's retry budget")
                        if attempt == 2:
                            raise CrawlBackoffError("Origin unavailable after bounded retries")
                        self.next_request = max(self.next_request, self.clock() + delay)
                        continue
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise CrawlPolicyError("Redirect has no destination")
                        url = urljoin(url, location)
                        break
                    limit = 500_000 if robots_request else self.settings.max_response_bytes
                    data = bytearray()
                    for part in response.iter_bytes():
                        data.extend(part)
                        if len(data) > limit:
                            raise CrawlPolicyError("Response exceeds byte budget")
                    return response, bytes(data)
            else:
                raise CrawlPolicyError("Request retry loop exhausted")
        raise CrawlPolicyError("Redirect limit exceeded")

    def load_robots(self) -> None:
        origin = urlsplit(self.policy.seed)
        robots_url = urlunsplit((origin.scheme, origin.netloc, "/robots.txt", "", ""))
        response, data = self._request(robots_url, robots_request=True)
        if response.status_code in (404, 410):
            text = "User-agent: *\nAllow: /\n"
        elif response.status_code == 200:
            text = data.decode("utf-8", errors="replace")
        else:
            raise CrawlPolicyError("robots.txt unavailable; refusing to assume permission")
        self.robots.parse(text.splitlines())
        crawl_delay = self.robots.crawl_delay(self.settings.user_agent)
        request_rate = self.robots.request_rate(self.settings.user_agent)
        if crawl_delay is not None:
            self.interval = max(self.interval, float(crawl_delay))
        if request_rate is not None and request_rate.requests > 0:
            self.interval = max(self.interval, request_rate.seconds / request_rate.requests)
        self.next_request = max(self.next_request, self.clock() + self.interval)
        self.robots_document = {"url": robots_url, "status": response.status_code, "fetched_at": utcnow(),
                                "content": text, "sha256": digest(data), "interval_seconds": self.interval,
                                "missing_policy": response.status_code in (404, 410)}

    def crawl(self) -> dict:
        try:
            self.load_robots()
            queue, scheduled, visited = deque([self.policy.seed]), {self.policy.seed}, set()
            pages, errors, documents = [], [], 0
            pattern = re.compile(self.settings.source_record_pattern)
            while queue and len(visited) < self.settings.max_fetches and documents < self.settings.max_pages:
                url = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)
                try:
                    response, raw = self._request(url)
                    response.raise_for_status()
                    mime = response.headers.get("Content-Type", "").lower()
                    if "text/html" not in mime and "application/xhtml+xml" not in mime:
                        raise CrawlPolicyError("Not an HTML document")
                    html = raw.decode(response.encoding or "utf-8", errors="replace")
                    final_url = canonical_url(str(response.url))
                    info = extract_html(html, final_url, self.settings.source_adapter, self.settings.source_selector)
                    selected = info["is_document"] and bool(pattern.search(urlsplit(final_url).path))
                    if selected:
                        documents += 1
                    pages.append({"doc_id": digest(final_url), "url": final_url, "title": info["title"],
                                  "text": info["text"], "html": html, "raw_html": raw, "html_bytes": len(raw),
                                  "fetched_at": utcnow(), "status": response.status_code,
                                  "etag": response.headers.get("ETag", ""),
                                  "last_modified": response.headers.get("Last-Modified", ""),
                                  "content_sha256": digest(raw), "is_document": selected})
                    for target in info["links"]:
                        try:
                            candidate = canonical_url(target)
                            p = urlsplit(candidate)
                            if p[:2] != self.policy.origin or not p.path.startswith(self.settings.source_path_prefix):
                                continue
                            if re.search(r"\.(pdf|png|jpg|jpeg|gif|svg|zip|css|js|mp4)$", p.path, re.I):
                                continue
                            if candidate not in scheduled and len(scheduled) < self.settings.max_fetches * 4:
                                scheduled.add(candidate)
                                queue.append(candidate)
                        except (CrawlPolicyError, ValueError):
                            continue
                except CrawlBackoffError:
                    raise
                except (httpx.HTTPError, CrawlPolicyError, ValueError) as exc:
                    errors.append({"url": url, "type": type(exc).__name__})
                    log.warning("crawl_page_rejected", extra={"fields": {"error_type": type(exc).__name__}})
            return {"pages": pages, "errors": errors, "robots": self.robots_document,
                    "document_count": documents, "fetch_count": len(visited)}
        finally:
            self.close()
