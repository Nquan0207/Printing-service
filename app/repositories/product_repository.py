from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.crawler.parser import NormalizedProduct
from app.database.models import Category, Industry, Product, ProductPriceHistory, utcnow


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def ensure_category(
        self,
        industry_slug,
        industry_name,
        category_slug,
        category_name,
        source_url,
        enabled=True,
        max_products=8,
    ):
        industry = self.session.scalar(
            select(Industry).where(Industry.slug == industry_slug)
        )
        if not industry:
            industry = Industry(slug=industry_slug, name=industry_name)
            self.session.add(industry)
            self.session.flush()
        category = self.session.scalar(
            select(Category).where(
                Category.industry_id == industry.id, Category.slug == category_slug
            )
        )
        if not category:
            category = Category(
                industry_id=industry.id,
                slug=category_slug,
                name=category_name,
                source_url=source_url,
                enabled=enabled,
                max_products=max_products,
            )
            self.session.add(category)
            self.session.flush()
        else:
            category.name = category_name
            category.source_url = source_url
            category.enabled = enabled
            category.max_products = max_products
        return category

    def upsert(self, item: NormalizedProduct, category_id: int) -> tuple[Product, bool]:
        values = item.model_dump(mode="python") | {
            "category_id": category_id,
            "product_url": str(item.product_url),
            "image_url": str(item.image_url) if item.image_url else None,
        }
        values.pop("industry_slug")
        values.pop("category_slug")
        existing = self.session.scalar(
            select(Product).where(Product.product_url == str(item.product_url))
        )
        old_price = existing.price_jpy if existing else None
        mutable = {
            key: value
            for key, value in values.items()
            if value is not None or key in {"colors", "sizes"}
        }
        mutable["updated_at"] = utcnow()
        stmt = (
            insert(Product)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Product.product_url], set_=mutable
            )
            .returning(Product)
        )
        product = self.session.scalars(stmt).one()
        created = existing is None
        if item.price_jpy is not None and (created or old_price != item.price_jpy):
            self.session.add(ProductPriceHistory(product_id=product.id, price_jpy=item.price_jpy))
        return product, created

    def search(
        self, query=None, industry=None, category=None, brand=None, color=None,
        min_price=None, max_price=None, limit=10,
    ):
        stmt = (
            select(Product)
            .join(Product.category)
            .join(Category.industry)
            .options(joinedload(Product.category).joinedload(Category.industry))
        )
        if query:
            stmt = stmt.where(
                or_(
                    Product.name.ilike(f"%{query}%"),
                    Product.description.ilike(f"%{query}%"),
                )
            )
        if industry:
            stmt = stmt.where(Industry.slug == industry)
        if category:
            stmt = stmt.where(Category.slug == category)
        if brand:
            stmt = stmt.where(Product.brand.ilike(f"%{brand}%"))
        if color:
            stmt = stmt.where(Product.colors.contains([color]))
        if min_price is not None:
            stmt = stmt.where(Product.price_jpy >= min_price)
        if max_price is not None:
            stmt = stmt.where(Product.price_jpy <= max_price)
        return list(self.session.scalars(stmt.order_by(Product.id).limit(min(max(limit, 1), 100))).unique())

    def get(self, product_id):
        return self.session.get(
            Product,
            product_id,
            options=[joinedload(Product.category).joinedload(Category.industry)],
        )

    def get_by_source_id(self, source_id):
        return self.session.scalar(
            select(Product)
            .where(Product.source_product_id == source_id)
            .options(joinedload(Product.category).joinedload(Category.industry))
        )

    def list_industries(self):
        return list(self.session.scalars(select(Industry).order_by(Industry.name)))

    def list_categories(self, industry=None):
        stmt = (
            select(Category)
            .join(Category.industry)
            .options(joinedload(Category.industry))
            .order_by(Industry.name, Category.name)
        )
        return list(self.session.scalars(stmt.where(Industry.slug == industry) if industry else stmt))

    def stats(self):
        return {
            "industries": self.session.scalar(select(func.count()).select_from(Industry)),
            "categories": self.session.scalar(select(func.count()).select_from(Category)),
            "products": self.session.scalar(select(func.count()).select_from(Product)),
        }
