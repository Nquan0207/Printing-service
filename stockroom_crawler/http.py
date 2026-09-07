"""Polite HTTP access to stockroom.raksul.com."""

from __future__ import annotations

import logging
from time import sleep
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from stockroom_crawler.config import BASE_URL, USER_AGENT

log = logging.getLogger(__name__)


class HttpClient:
    """Session with retry, a real user agent, and robots.txt enforcement.

    robots.txt is fetched once for stockroom.raksul.com. Asset hosts
    (the sitemap bucket, the image CDN) are not gated by it -- they serve
    static objects the site itself links to.
    """

    def __init__(self, delay: float = 1.25, timeout: float = 25):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.5"}
        )
        self._robots: RobotFileParser | None = None

    def _robots_allowed(self, url: str) -> bool:
        if self._robots is None:
            parser = RobotFileParser(f"{BASE_URL}/robots.txt")
            try:
                parser.read()
            except Exception as exc:  # an outage must not read as permission
                log.warning("Could not read robots.txt (%s); refusing to crawl", exc)
                return False
            self._robots = parser
        return self._robots.can_fetch(USER_AGENT, url)

    def get_text(self, url: str, *, delayed: bool = True) -> str:
        if url.startswith(BASE_URL) and not self._robots_allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        if delayed:
            sleep(self.delay)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def get_bytes(self, url: str, *, delayed: bool = True) -> tuple[bytes, str]:
        """Return (body, content_type) -- used for product images."""
        if delayed:
            sleep(self.delay)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.content, content_type.split(";")[0].strip()
