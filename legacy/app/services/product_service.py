from datetime import datetime, timezone

from app.repositories.product_repository import ProductRepository


class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def search_products(self, **filters):
        return self.repository.search(**filters)

    def get_product(self, product_id):
        return self.repository.get(product_id)

    def get_product_by_source_id(self, source_id):
        return self.repository.get_by_source_id(source_id)

    def list_industries(self):
        return self.repository.list_industries()

    def list_categories(self, industry=None):
        return self.repository.list_categories(industry)


def is_product_stale(product, max_age_hours=24):
    if not product.scraped_at:
        return True
    scraped = (
        product.scraped_at
        if product.scraped_at.tzinfo
        else product.scraped_at.replace(tzinfo=timezone.utc)
    )
    return (datetime.now(timezone.utc) - scraped).total_seconds() > max_age_hours * 3600
