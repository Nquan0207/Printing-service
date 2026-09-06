from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, FeatureNotFound

BASE_URL = "https://apparel.raksul.com"


@dataclass(frozen=True)
class DiscoveredProduct:
    industry: str
    category: str
    url: str


def canonical_product_url(href: str, base_url: str = BASE_URL) -> str | None:
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    product_path = re.fullmatch(
        r"/(?:work|clinic|food|casual)-uniform/products/\d+/?", parts.path
    )
    if parts.netloc != "apparel.raksul.com" or not product_path:
        return None
    return urlunsplit(("https", parts.netloc, parts.path.rstrip("/"), "", ""))


def extract_product_urls(html: str, base_url: str = BASE_URL) -> list[str]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:  # keeps lightweight tooling usable before requirements are installed
        soup = BeautifulSoup(html, "html.parser")
    urls = {url for a in soup.find_all("a", href=True) if (url := canonical_product_url(a["href"], base_url))}
    return sorted(urls)


def discover(html: str, industry: str, category: str, limit: int) -> list[DiscoveredProduct]:
    return [DiscoveredProduct(industry, category, url) for url in extract_product_urls(html)[:limit]]
