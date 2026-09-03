from __future__ import annotations

import logging
from time import sleep
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "RAKSULCatalogMVP/1.0 (+local research catalog; respectful crawler)"
log = logging.getLogger(__name__)


class HttpClient:
    def __init__(self, timeout: float = 20, delay: float = 1.25):
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.5"})
        self._robots: RobotFileParser | None = None

    def robots_allowed(self, url: str) -> bool:
        if self._robots is None:
            parser = RobotFileParser("https://apparel.raksul.com/robots.txt")
            try:
                parser.read()
                self._robots = parser
            except Exception as exc:  # a robots outage must not silently look like a denial
                log.warning("Could not read robots.txt (%s); stopping crawl", exc)
                return False
        return self._robots.can_fetch(USER_AGENT, url)

    def get_text(self, url: str, *, delayed: bool = False) -> str:
        if not self.robots_allowed(url):
            raise PermissionError(f"robots.txt does not allow crawling {url}")
        if delayed:
            sleep(self.delay)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

