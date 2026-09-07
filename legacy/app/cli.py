from __future__ import annotations

import argparse
import logging

from app.crawler.runner import run_crawl
from app.database.connection import make_engine, session_scope
from app.database.models import Base
from app.repositories.product_repository import ProductRepository
from app.services.product_service import ProductService


def parser():
    root = argparse.ArgumentParser(description="RAKSUL catalog MVP")
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    crawl = commands.add_parser("crawl"); crawl.add_argument("--category"); crawl.add_argument("--limit", type=int); crawl.add_argument("--config")
    commands.add_parser("stats")
    categories = commands.add_parser("categories"); categories.add_argument("--industry")
    search = commands.add_parser("search")
    for name in ("query", "industry", "category", "brand", "color"): search.add_argument(f"--{name}")
    search.add_argument("--min-price", type=int); search.add_argument("--max-price", type=int); search.add_argument("--limit", type=int, default=10)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    engine = make_engine()
    if args.command == "init-db":
        Base.metadata.create_all(engine); print("Database initialized."); return
    if args.command == "crawl":
        result = run_crawl(args.category, args.limit, args.config, engine)
        print(f"Crawl completed.\nCategories: {result.categories}\nProducts discovered: {result.discovered}\nUnique products: {result.unique_products}\nInserted: {result.inserted}\nUpdated: {result.updated}\nFailed: {result.failed}\nRuntime: {result.runtime_seconds:.1f}s"); return
    with session_scope(engine) as session:
        repo = ProductRepository(session); service = ProductService(repo)
        if args.command == "stats":
            for key, value in repo.stats().items(): print(f"{key.title()}: {value}")
        elif args.command == "categories":
            for category in service.list_categories(args.industry): print(f"{category.industry.slug}/{category.slug}: {category.name} ({'enabled' if category.enabled else 'disabled'})")
        elif args.command == "search":
            filters = vars(args); products = service.search_products(**{k: filters[k] for k in ("query", "industry", "category", "brand", "color", "min_price", "max_price", "limit")})
            if not products: print("No products found.")
            for product in products:
                price = f"¥{product.price_jpy:,}" if product.price_jpy is not None else "unknown"
                print(f"ID: {product.id}\nName: {product.name}\nBrand: {product.brand or '-'}\nIndustry: {product.category.industry.name}\nCategory: {product.category.name}\nPrice: {price}\nURL: {product.product_url}\n")


if __name__ == "__main__": main()

