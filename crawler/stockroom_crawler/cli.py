from __future__ import annotations

import argparse
import logging

from stockroom_crawler import db, pipeline
from stockroom_crawler.config import TOP_LEVEL_CATEGORIES, Settings


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m stockroom_crawler.cli",
        description="Crawl stockroom.raksul.com into the go-backend schema",
    )
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("init-db", help="apply go-backend/schema.sql (drops tables)")
    commands.add_parser("categories", help="list the top-level category whitelist")
    commands.add_parser("stats", help="row counts per table")

    crawl = commands.add_parser("crawl", help="crawl and import products")
    crawl.add_argument("--category", help="restrict to one top-level slug")
    crawl.add_argument(
        "--categories",
        type=int,
        metavar="N",
        help="use only the first N top-level categories (overrides CRAWL_MAX_CATEGORIES)",
    )
    crawl.add_argument("--limit", type=int, help="override CRAWL_MAX_PRODUCTS")
    crawl.add_argument(
        "--reset", action="store_true", help="truncate crawled tables first"
    )
    return root


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.command == "categories":
        for slug, name in TOP_LEVEL_CATEGORIES.items():
            print(f"{slug}: {name}")
        return

    settings = Settings.from_env()

    if args.command == "init-db":
        connection = db.connect(settings.database_url)
        try:
            db.apply_schema(connection)
        finally:
            connection.close()
        print("Schema applied.")
        return

    if args.command == "stats":
        connection = db.connect(settings.database_url)
        try:
            for table, count in db.counts(connection).items():
                print(f"{table}: {count}")
        finally:
            connection.close()
        return

    overrides = {}
    if args.limit:
        overrides["max_products"] = args.limit
    if args.categories:
        overrides["max_categories"] = args.categories
    if overrides:
        from dataclasses import replace

        settings = replace(settings, **overrides)
    if args.reset:
        connection = db.connect(settings.database_url)
        try:
            db.reset_catalog(connection)
        finally:
            connection.close()
        print("Cleared crawled tables.")

    summary = pipeline.run(settings, args.category)
    print(
        "\nCrawl complete."
        f"\n  Categories:      {summary.categories}"
        f"\n  Products:        {summary.products}"
        f"\n  Sizes:           {summary.sizes}"
        f"\n  Images in MinIO: {summary.images}"
        f"\n  Skipped (<{settings.sizes_per_product} SKUs): {summary.skipped_too_few_skus}"
        f"\n  Failed:          {summary.failed}"
        f"\n  Runtime:         {summary.runtime_seconds:.1f}s"
    )
    if summary.per_category:
        print("\nPer category:")
        for slug, count in summary.per_category.items():
            print(f"  {slug}: {count}")


if __name__ == "__main__":
    main()
