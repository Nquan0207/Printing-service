import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select

from app.crawler.parser import NormalizedProduct
from app.database.models import Base, Product, ProductPriceHistory
from app.repositories.product_repository import ProductRepository

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="set TEST_DATABASE_URL to run PostgreSQL integration tests")


@pytest.fixture
def repo():
    engine = create_engine(TEST_URL); Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with engine.begin() as connection:
        from sqlalchemy.orm import Session
        with Session(connection) as session: yield ProductRepository(session); session.commit()
    Base.metadata.drop_all(engine)


def item(price=1000, description="useful"):
    return NormalizedProduct(source_product_id="42", name="Black Vest", brand="TestBrand", industry_slug="food", category_slug="aprons", price_jpy=price, description=description, colors=["black"], sizes=["M"], product_url="https://apparel.raksul.com/casual-uniform/products/42", scraped_at=datetime.now(timezone.utc))


def test_postgres_upsert_preserves_optional_data_and_price_history(repo):
    category = repo.ensure_category("food", "Food", "aprons", "Aprons", "https://example.test")
    first, created = repo.upsert(item(), category.id); repo.session.flush()
    assert created
    second, created = repo.upsert(item(1200, None), category.id); repo.session.flush()
    assert not created and second.description == "useful"
    assert repo.session.scalar(select(func.count()).select_from(Product)) == 1
    assert repo.session.scalar(select(func.count()).select_from(ProductPriceHistory)) == 2


@pytest.mark.parametrize("filters", [{"max_price": 1100}, {"industry":"food"}, {"category":"aprons"}, {"brand":"Test"}, {"color":"black"}, {"query":"Vest"}])
def test_search_filters(repo, filters):
    category = repo.ensure_category("food", "Food", "aprons", "Aprons", "https://example.test")
    repo.upsert(item(), category.id); repo.session.flush()
    assert len(repo.search(**filters)) == 1

