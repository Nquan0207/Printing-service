from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Industry(Base):
    __tablename__ = "industries"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    categories: Mapped[list["Category"]] = relationship(back_populates="industry")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("industry_id", "slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_products: Mapped[int] = mapped_column(Integer, default=8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    industry: Mapped[Industry] = relationship(back_populates="categories")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_product_id: Mapped[str | None] = mapped_column(String(80))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(160), index=True)
    price_jpy: Mapped[int | None] = mapped_column(Integer, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    colors: Mapped[list] = mapped_column(JSONB, default=list)
    sizes: Mapped[list] = mapped_column(JSONB, default=list)
    stock_status: Mapped[str | None] = mapped_column(String(40))
    printing_available: Mapped[bool | None] = mapped_column(Boolean)
    product_url: Mapped[str] = mapped_column(Text, unique=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    category: Mapped[Category] = relationship(back_populates="products")
    price_history: Mapped[list["ProductPriceHistory"]] = relationship(back_populates="product")


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    price_jpy: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    product: Mapped[Product] = relationship(back_populates="price_history")


class Cart(Base):
    __tablename__ = "carts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.id"
    )
    orders: Mapped[list["MockOrder"]] = relationship(back_populates="cart")


class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    selected_color: Mapped[str | None] = mapped_column(String(120))
    selected_size: Mapped[str | None] = mapped_column(String(80))
    unit_price_jpy: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class MockOrder(Base):
    __tablename__ = "mock_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    total_jpy: Mapped[int] = mapped_column(Integer)
    line_items: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cart: Mapped[Cart] = relationship(back_populates="orders")


class MockCustomer(Base):
    __tablename__ = "mock_customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MockSession(Base):
    __tablename__ = "mock_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("mock_customers.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    customer: Mapped[MockCustomer] = relationship()


class MockSessionCart(Base):
    __tablename__ = "mock_session_carts"
    session_id: Mapped[str] = mapped_column(ForeignKey("mock_sessions.id", ondelete="CASCADE"), primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MockCheckoutConfirmation(Base):
    __tablename__ = "mock_checkout_confirmations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("mock_orders.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_products_source_product_id", Product.source_product_id)
Index("ix_products_colors_gin", Product.colors, postgresql_using="gin")
