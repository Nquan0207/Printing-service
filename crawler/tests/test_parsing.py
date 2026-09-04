"""Parsing and discovery tests -- fixtures are real stockroom.raksul.com pages."""

from pathlib import Path

import pytest

from stockroom_crawler.config import TOP_LEVEL_CATEGORIES
from stockroom_crawler.discovery import (
    category_pages_by_top_level,
    general_sitemap_url,
    product_skus,
)
from stockroom_crawler.parser import SkuVariant, parse_variant, product_display_name

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_product_jsonld():
    html = (FIXTURES / "product_sku.html").read_text(encoding="utf-8")
    variant = parse_variant(html, "4734", "10122")
    assert variant is not None
    assert variant.sku_id == "10122"
    assert variant.name == "担々麺白"
    assert variant.brand == "ラクスル"
    assert variant.images == [
        "https://cdn-stockroom.raksul.com/public_images/"
        "c43f517e-2816-4fb0-8665-13c7ce687fce"
    ]


def test_price_uses_min_order_tier_rounded_up():
    """highPrice is the min-quantity unit price; 917 here, not the 916 bulk rate."""
    html = (FIXTURES / "product_sku.html").read_text(encoding="utf-8")
    assert parse_variant(html, "4734", "10122").unit_price_jpy == 917


def test_page_without_product_jsonld_is_skipped():
    assert parse_variant("<html><body>404</body></html>", "1", "2") is None


def test_category_page_groups_skus_by_product():
    html = (FIXTURES / "category.html").read_text(encoding="utf-8")
    grouped = product_skus(html)
    assert grouped["158"][:3] == ["1034", "1035", "1036"]
    # Only products with enough variants can be given S/M/L labels.
    assert sum(1 for skus in grouped.values() if len(skus) >= 3) >= 3


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["手提げ紙袋（幅120）", "手提げ紙袋マチ広（幅160）", "手提げ紙袋（幅170）"], "手提げ紙袋"),
        (["担々麺白"], "担々麺白"),
    ],
)
def test_product_name_drops_variant_spec(names, expected):
    variants = [
        SkuVariant(product_id="1", sku_id=str(i), name=n, unit_price_jpy=100)
        for i, n in enumerate(names)
    ]
    assert product_display_name(variants) == expected


def test_sitemap_index_locates_general_sitemap():
    xml = (
        "<sitemapindex><sitemap><loc>https://x/sitemap_product1.xml</loc></sitemap>"
        "<sitemap><loc>https://x/sitemap_general.xml</loc></sitemap></sitemapindex>"
    )
    assert general_sitemap_url(xml) == "https://x/sitemap_general.xml"


def test_bare_top_level_category_pages_are_dropped():
    """An L1 page is a hub of subcategory tiles and lists no products."""
    xml = """<urlset>
      <url><loc>https://stockroom.raksul.com/categories/store_supplies/</loc></url>
      <url><loc>https://stockroom.raksul.com/categories/store_supplies/bags/</loc></url>
      <url><loc>https://stockroom.raksul.com/categories/store_supplies/bags/paperbag/</loc></url>
      <url><loc>https://stockroom.raksul.com/rank/paperbag</loc></url>
    </urlset>"""
    grouped = category_pages_by_top_level(xml)
    assert grouped["store_supplies"] == [
        "https://stockroom.raksul.com/categories/store_supplies/bags/",
        "https://stockroom.raksul.com/categories/store_supplies/bags/paperbag/",
    ]


def test_whitelist_covers_the_sixteen_landing_tiles():
    assert len(TOP_LEVEL_CATEGORIES) == 16
    assert "store_supplies" in TOP_LEVEL_CATEGORIES
