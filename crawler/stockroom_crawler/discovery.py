"""Stage A: find product/SKU pairs, grouped under a top-level category.

The sitemap index lists ~3,800 category pages. Only depth>=2 pages list
products (a bare L1 page is a hub of subcategory tiles), so discovery walks
an L1's subcategory pages shallowest-first until it has enough products.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

_LOC = re.compile(r"<loc>([^<]+)</loc>")
_CATEGORY_PATH = re.compile(r"^/categories/(?P<path>[^?#]+?)/?$")
_PRODUCT_LINK = re.compile(r"/products/(\d+)\?sku=(\d+)")


def sitemap_locations(xml: str) -> list[str]:
    return [m.strip() for m in _LOC.findall(xml)]


def general_sitemap_url(index_xml: str) -> str:
    for url in sitemap_locations(index_xml):
        if url.endswith("sitemap_general.xml"):
            return url
    raise ValueError("sitemap_general.xml not present in the sitemap index")


def category_pages_by_top_level(general_xml: str) -> dict[str, list[str]]:
    """Group subcategory page URLs under their L1 slug, shallowest first.

    A bare L1 page is dropped: it lists no products.
    """
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for url in sitemap_locations(general_xml):
        match = _CATEGORY_PATH.match(urlsplit(url).path)
        if not match:
            continue
        segments = match.group("path").split("/")
        if len(segments) < 2:
            continue
        grouped[segments[0]].append((len(segments), url))
    return {
        slug: [url for _, url in sorted(pages)] for slug, pages in grouped.items()
    }


def product_skus(html: str) -> dict[str, list[str]]:
    """Map product id -> sorted SKU ids linked from a category listing page."""
    found: dict[str, set[str]] = defaultdict(set)
    for product_id, sku in _PRODUCT_LINK.findall(html):
        found[product_id].add(sku)
    return {
        product_id: sorted(skus, key=int) for product_id, skus in found.items()
    }
