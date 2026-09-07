"""Crawl orchestration: discover -> parse -> store images -> write rows."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from time import monotonic

from stockroom_crawler import db, discovery
from stockroom_crawler.config import (
    SITEMAP_INDEX_URL,
    SIZE_LABELS,
    TOP_LEVEL_CATEGORIES,
    Settings,
)
from stockroom_crawler.http import HttpClient
from stockroom_crawler.parser import SkuVariant, parse_variant, product_display_name
from stockroom_crawler.storage import ImageStore

log = logging.getLogger(__name__)


@dataclass
class CrawlSummary:
    categories: int = 0
    products: int = 0
    sizes: int = 0
    images: int = 0
    skipped_too_few_skus: int = 0
    failed: int = 0
    runtime_seconds: float = 0.0
    per_category: dict[str, int] = field(default_factory=dict)


def _fetch_variants(
    client: HttpClient, product_id: str, sku_ids: list[str], wanted: int
) -> list[SkuVariant]:
    """Fetch SKU pages until `wanted` variants at distinct prices are collected.

    Distinct prices matter: S/M/L labels are meaningless if two variants
    resolve to the same yen figure.
    """
    variants: list[SkuVariant] = []
    seen_prices: set[int] = set()
    for sku_id in sku_ids:
        if len(variants) >= wanted:
            break
        try:
            html = client.get_text(
                f"https://stockroom.raksul.com/products/{product_id}?sku={sku_id}"
            )
        except Exception as exc:
            log.warning("Fetch failed for %s?sku=%s: %s", product_id, sku_id, exc)
            continue
        variant = parse_variant(html, product_id, sku_id)
        if variant and variant.unit_price_jpy not in seen_prices:
            seen_prices.add(variant.unit_price_jpy)
            variants.append(variant)
    return variants


def _store_images(
    client: HttpClient,
    store: ImageStore,
    product_id: str,
    variants: list[SkuVariant],
    limit: int,
) -> list[str]:
    urls: list[str] = []
    for variant in variants:
        for url in variant.images:
            if url not in urls:
                urls.append(url)
    keys: list[str] = []
    for url in urls[:limit]:
        try:
            # cdn-stockroom.raksul.com is a static asset host; a browser pulls
            # a dozen of these per page view, so no inter-request delay.
            body, content_type = client.get_bytes(url, delayed=False)
            keys.append(store.put(product_id, body, content_type))
        except Exception as exc:
            log.warning("Image fetch failed %s: %s", url, exc)
    return keys


def _discover_products(
    client: HttpClient, pages: list[str], needed: int, sizes_per_product: int
) -> dict[str, list[str]]:
    """Walk a category's subcategory pages until enough products are found."""
    collected: dict[str, list[str]] = {}
    for page in pages:
        if len(collected) >= needed:
            break
        try:
            html = client.get_text(page)
        except Exception as exc:
            log.warning("Category page failed %s: %s", page, exc)
            continue
        for product_id, skus in discovery.product_skus(html).items():
            if product_id in collected or len(skus) < sizes_per_product:
                continue
            collected[product_id] = skus
            if len(collected) >= needed:
                break
    return collected


def run(settings: Settings, only_category: str | None = None) -> CrawlSummary:
    started = monotonic()
    summary = CrawlSummary()
    client = HttpClient(delay=settings.request_delay)
    store = ImageStore(settings)
    store.ensure_bucket()

    if only_category:
        if only_category not in TOP_LEVEL_CATEGORIES:
            raise SystemExit(f"Unknown top-level category: {only_category}")
        slugs = [only_category]
    else:
        slugs = settings.selected_categories()
    log.info(
        "Budget: %d products across %d categories (%s)",
        settings.max_products,
        len(slugs),
        ", ".join(slugs),
    )

    log.info("Reading sitemap index")
    index_xml = client.get_text(SITEMAP_INDEX_URL, delayed=False)
    general_xml = client.get_text(
        discovery.general_sitemap_url(index_xml), delayed=False
    )
    pages_by_category = discovery.category_pages_by_top_level(general_xml)

    remaining = settings.max_products

    connection = db.connect(settings.database_url)
    try:
        for index, slug in enumerate(slugs):
            if remaining <= 0:
                break
            # Re-divide what is left over the categories still to come, so a
            # thin category's shortfall is picked up by later ones and the
            # configured budget is actually reached.
            want = min(remaining, math.ceil(remaining / (len(slugs) - index)))
            name = TOP_LEVEL_CATEGORIES[slug]
            pages = pages_by_category.get(slug, [])
            if not pages:
                log.warning("No subcategory pages for %s", slug)
                continue

            log.info("[%s] discovering up to %d products", slug, want)
            found = _discover_products(
                client, pages, want, settings.sizes_per_product
            )
            if not found:
                continue

            category_id = db.upsert_category(connection, slug, name)
            summary.categories += 1
            stored_here = 0

            for product_id, sku_ids in found.items():
                if remaining <= 0:
                    break
                variants = _fetch_variants(
                    client, product_id, sku_ids, settings.sizes_per_product
                )
                if len(variants) < settings.sizes_per_product:
                    summary.skipped_too_few_skus += 1
                    continue

                variants.sort(key=lambda v: v.unit_price_jpy)
                base_price = variants[0].unit_price_jpy
                first = variants[0]

                try:
                    row_id = db.upsert_product(
                        connection,
                        category_id=category_id,
                        source_product_id=product_id,
                        name=product_display_name(variants),
                        brand=first.brand,
                        description=first.description,
                        base_price_jpy=base_price,
                    )
                    db.replace_sizes(
                        connection,
                        row_id,
                        [
                            (label, v.sku_id, v.unit_price_jpy - base_price)
                            for label, v in zip(SIZE_LABELS, variants)
                        ],
                    )
                    keys = _store_images(
                        client, store, product_id, variants, settings.max_images
                    )
                    db.sync_images(connection, row_id, keys)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    log.exception("Failed to store product %s", product_id)
                    summary.failed += 1
                    continue

                summary.products += 1
                summary.sizes += len(variants)
                summary.images += len(keys)
                stored_here += 1
                remaining -= 1
                log.info(
                    "[%s] %s -> id=%s base=¥%s sizes=%d images=%d",
                    slug,
                    product_id,
                    row_id,
                    base_price,
                    len(variants),
                    len(keys),
                )

            summary.per_category[slug] = stored_here
    finally:
        connection.close()

    summary.runtime_seconds = monotonic() - started
    return summary
