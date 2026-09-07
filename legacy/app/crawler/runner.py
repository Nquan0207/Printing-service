from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic

from app.crawler.client import HttpClient
from app.crawler.config import MAX_PRODUCTS_TOTAL, REQUEST_DELAY_SECONDS, load_categories
from app.crawler.discovery import discover
from app.crawler.product import crawl_product
from app.database.connection import session_scope
from app.repositories.product_repository import ProductRepository

log = logging.getLogger(__name__)


@dataclass
class CrawlSummary:
    categories: int = 0
    discovered: int = 0
    unique_products: int = 0
    inserted: int = 0
    updated: int = 0
    failed: int = 0
    runtime_seconds: float = 0


def run_crawl(category_slug=None, limit=None, config_path=None, engine=None):
    started = monotonic(); summary = CrawlSummary(); client = HttpClient(delay=REQUEST_DELAY_SECONDS)
    configs = [c for c in load_categories(config_path) if c.enabled and (not category_slug or c.category == category_slug)]
    remaining = min(limit if limit is not None else MAX_PRODUCTS_TOTAL, MAX_PRODUCTS_TOTAL)
    seen: set[str] = set()
    with session_scope(engine) as session:
        repository = ProductRepository(session)
        for config in configs:
            if remaining <= 0: break
            summary.categories += 1
            log.info("Crawling category %s/%s", config.industry, config.category)
            category = repository.ensure_category(config.industry, config.industry_name, config.category, config.category_name, config.source_url, config.enabled, config.max_products)
            try:
                found = discover(client.get_text(config.source_url), config.industry, config.category, min(config.max_products, remaining))
            except Exception:
                log.exception("Category discovery failed: %s", config.source_url); summary.failed += 1; continue
            summary.discovered += len(found)
            selected = [item for item in found if item.url not in seen]
            for position, item in enumerate(selected, 1):
                if remaining <= 0: break
                seen.add(item.url); remaining -= 1
                log.info("Crawling product %d/%d %s", position, len(selected), item.url)
                try:
                    product = crawl_product(client, item.url, item.industry, item.category)
                    saved, created = repository.upsert(product, category.id)
                    summary.inserted += int(created); summary.updated += int(not created)
                    log.info("%s product %s", "Inserted" if created else "Updated", saved.source_product_id)
                except Exception:
                    log.exception("Product crawl failed: %s", item.url); summary.failed += 1
    summary.unique_products = len(seen); summary.runtime_seconds = monotonic() - started
    return summary

