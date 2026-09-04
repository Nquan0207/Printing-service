"""Stage B: turn a product page into a normalized variant record.

Only the schema.org Product JSON-LD block is parsed. The page also embeds a
Nuxt payload, but that uses index-based dereferencing -- `"price":181` means
"element 181 of a flat array", not 181 yen -- so reading it naively yields
nonsense prices.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

_JSONLD = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)


@dataclass(frozen=True)
class SkuVariant:
    """One ?sku= variant of a stockroom product."""

    product_id: str
    sku_id: str
    name: str
    unit_price_jpy: int
    description: str | None = None
    brand: str | None = None
    images: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://stockroom.raksul.com/products/{self.product_id}?sku={self.sku_id}"


def _product_jsonld(html: str) -> dict:
    for block in _JSONLD.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return {}


def _unit_price(offers: dict) -> int | None:
    """Highest tier price, rounded up to whole yen.

    stockroom quotes a tiered range: `lowPrice` is the bulk unit price and
    `highPrice` the price at minimum order quantity. The PoC has no quantity
    model, so it stores what a buyer pays for the smallest order -- the
    conservative figure. Values are fractional (916.5), hence the ceil.
    """
    for key in ("highPrice", "price", "lowPrice"):
        value = offers.get(key)
        if isinstance(value, (int, float)):
            return math.ceil(value)
        if isinstance(value, str):
            try:
                return math.ceil(float(value.replace(",", "")))
            except ValueError:
                continue
    return None


def parse_variant(html: str, product_id: str, sku_id: str) -> SkuVariant | None:
    """Return the variant, or None when the page lacks a usable Product block."""
    data = _product_jsonld(html)
    if not data:
        return None
    name = (data.get("name") or "").strip()
    offers = data.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = _unit_price(offers)
    if not name or price is None:
        return None

    brand = data.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    images = data.get("image") or []
    if isinstance(images, str):
        images = [images]

    description = (data.get("description") or "").strip() or None
    return SkuVariant(
        product_id=product_id,
        sku_id=str(data.get("sku") or sku_id),
        name=name,
        unit_price_jpy=price,
        description=description,
        brand=(brand or "").strip() or None,
        images=[url for url in images if isinstance(url, str)],
    )


def product_display_name(variants: list[SkuVariant]) -> str:
    """Derive a product name shared by its variants.

    Variant names carry their spec in parentheses --
    「手提げ紙袋（オレンジ マット・幅120×マチ70×高さ165mm）」 -- so the text
    before the bracket is the product itself. The most common such stem wins;
    with no bracket the full name is used unchanged.
    """
    from collections import Counter

    stems = Counter(re.split(r"[（(]", v.name, maxsplit=1)[0].strip() for v in variants)
    stem, _ = stems.most_common(1)[0]
    return stem or variants[0].name
