import socket

import httpx
import pytest

from veritylake.crawler import CrawlBackoffError, CrawlPolicyError, Crawler, URLPolicy, canonical_url


class Clock:
    value = 0.0
    def now(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


def crawler(settings, handler):
    clock = Clock()
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.org")
    instance = Crawler(settings, client=client, sleep=clock.sleep, monotonic=clock.now)
    return instance, clock


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://u:p@example.org/", "http://example.org/?token=x",
                                 "https://example.org/%2e%2e/private", "https://example.org/a%5Cb"])
def test_unsafe_url_rejected(url):
    with pytest.raises(CrawlPolicyError):
        canonical_url(url)


def test_canonical_url():
    assert canonical_url("https://EXAMPLE.ORG:443/page#part") == "https://example.org/page"


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "fd00::1"])
def test_private_dns_is_blocked(settings, address):
    settings.allow_private_sources = False
    def resolver(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
    with pytest.raises(CrawlPolicyError):
        URLPolicy(settings, resolver).check("https://example.org/")


def test_robots_disallow_is_respected(settings):
    visited = []
    def handler(request):
        visited.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<main><h1>One</h1><a href='/private'>Forbidden</a></main>")
    instance, _ = crawler(settings, handler)
    result = instance.crawl()
    assert "/private" not in visited
    assert len(result["errors"]) == 1


def test_missing_robots_allows_and_applies_rate_limit(settings):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        text = "<main><h1>Page</h1>Useful data<a href='/two'>Next</a></main>"
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text=text)
    instance, clock = crawler(settings, handler)
    result = instance.crawl()
    assert result["document_count"] == 2
    assert clock.value >= 2 * settings.request_interval_seconds
    assert result["robots"]["missing_policy"]


def test_robots_failure_is_fail_closed(settings):
    instance, _ = crawler(settings, lambda request: httpx.Response(403))
    with pytest.raises(CrawlPolicyError):
        instance.crawl()


def test_long_retry_after_aborts_not_shortens(settings):
    instance, clock = crawler(settings, lambda request: httpx.Response(429, headers={"Retry-After": "120"}))
    with pytest.raises(CrawlBackoffError):
        instance.crawl()
    assert clock.value < 120


def test_short_retry_after_is_obeyed(settings):
    calls = 0
    def handler(request):
        nonlocal calls
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<main><h1>One</h1>Data</main>")
    instance, clock = crawler(settings, handler)
    assert instance.crawl()["document_count"] == 1
    assert clock.value >= 3


def test_cross_origin_redirect_never_followed(settings):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
    instance, _ = crawler(settings, handler)
    assert instance.crawl()["document_count"] == 0
    assert not any("169.254" in u for u in seen)


def test_html_byte_limit(settings):
    settings.max_response_bytes = 1024
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"x" * 1500)
    instance, _ = crawler(settings, handler)
    assert instance.crawl()["document_count"] == 0


def test_crawl_delay_respected(settings):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 4\nAllow: /")
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<main><h1>One</h1>Data</main>")
    instance, clock = crawler(settings, handler)
    instance.crawl()
    assert clock.value >= 4
