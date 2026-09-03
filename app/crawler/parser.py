from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, FeatureNotFound
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def clean(value: str | None) -> str | None:
    return " ".join(value.split()) if value and value.strip() else None


def extract_product_id(url: str) -> str | None:
    match = re.search(r"/products/(\d+)(?:/|$|[?#])", url)
    return match.group(1) if match else None


def parse_jpy_price(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    matches = re.findall(r"(?:¥\s*)?([\d,]+)\s*円?", value)
    return int(matches[0].replace(",", "")) if matches else None


class NormalizedProduct(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    source_product_id: str | None = None
    name: str
    brand: str | None = None
    industry_slug: str
    category_slug: str
    price_jpy: int | None = Field(default=None, ge=0)
    description: str | None = None
    colors: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    stock_status: str | None = None
    printing_available: bool | None = None
    product_url: HttpUrl
    image_url: HttpUrl | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return {}


def parse_product(html: str, url: str, industry: str, category: str) -> NormalizedProduct:
    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")
    data = _jsonld(soup)
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    meta = lambda prop: (soup.find("meta", attrs={"property": prop}) or {}).get("content")
    name = clean(data.get("name")) or clean(meta("og:title")) or (clean(soup.h1.get_text(" ")) if soup.h1 else None)
    if not name:
        raise ValueError(f"Product name not found at {url}")
    brand_data = data.get("brand")
    brand = clean(brand_data.get("name")) if isinstance(brand_data, dict) else clean(brand_data)
    description = clean(data.get("description")) or clean(meta("og:description"))
    image = data.get("image") or meta("og:image")
    if isinstance(image, list):
        image = image[0] if image else None
    availability = str(offers.get("availability", ""))
    stock = "available" if "InStock" in availability else "unavailable" if "OutOfStock" in availability else None
    text = soup.get_text(" ", strip=True)
    printing = True if ("印刷" in text or "プリント" in text) else None
    return NormalizedProduct(
        source_product_id=extract_product_id(url), name=name, brand=brand,
        industry_slug=industry, category_slug=category,
        price_jpy=parse_jpy_price(offers.get("price")) or parse_jpy_price(text),
        description=description, stock_status=stock, printing_available=printing,
        product_url=url, image_url=urljoin(url, image) if image else None,
    )
