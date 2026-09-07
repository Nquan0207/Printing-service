from pathlib import Path

import pytest

from app.crawler.discovery import discover, extract_product_urls
from app.crawler.parser import NormalizedProduct, extract_product_id, parse_jpy_price, parse_product
from app.crawler.config import load_categories

FIXTURES = Path(__file__).parent / "fixtures"


def test_category_url_extraction_and_deduplication():
    urls = extract_product_urls((FIXTURES / "category.html").read_text())
    assert urls == [
        "https://apparel.raksul.com/casual-uniform/products/1173",
        "https://apparel.raksul.com/casual-uniform/products/6474",
        "https://apparel.raksul.com/clinic-uniform/products/2486",
        "https://apparel.raksul.com/food-uniform/products/5931",
        "https://apparel.raksul.com/work-uniform/products/9001",
    ]


def test_discovery_associates_taxonomy_and_limits():
    found = discover((FIXTURES / "category.html").read_text(), "food", "aprons", 1)
    assert len(found) == 1 and found[0].industry == "food" and found[0].category == "aprons"


@pytest.mark.parametrize(("text", "expected"), [("3,230円", 3230), ("¥11,590", 11590), ("11,590円（税込）", 11590), (None, None)])
def test_jpy_price(text, expected): assert parse_jpy_price(text) == expected


def test_product_id():
    assert extract_product_id("https://apparel.raksul.com/casual-uniform/products/1173") == "1173"
    assert extract_product_id("https://example.com/no-product") is None


def test_normalized_product_from_jsonld():
    product = parse_product((FIXTURES / "product.html").read_text(), "https://apparel.raksul.com/casual-uniform/products/1173", "casual", "shirts")
    assert isinstance(product, NormalizedProduct)
    assert product.source_product_id == "1173"
    assert product.name == "ドライTシャツ 00300-ACT"
    assert product.brand == "glimmer" and product.price_jpy == 1590
    assert product.stock_status == "available" and product.printing_available is True


def test_default_whitelist_is_bounded():
    categories = load_categories()
    assert len(categories) == 10
    assert sum(item.max_products for item in categories) <= 100
