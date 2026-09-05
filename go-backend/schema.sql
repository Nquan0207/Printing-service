-- =========================================================
-- 1. USERS
-- =========================================================

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    address TEXT,
    -- Gates /api/v1/admin/*. Granted at startup from STOCKROOM_ADMIN_EMAILS,
    -- never by any API call, so the surface cannot escalate its own access.
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =========================================================
-- 2. CATEGORIES
-- =========================================================

CREATE TABLE categories (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    slug VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =========================================================
-- 3. PRODUCTS
-- =========================================================

CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    category_id BIGINT NOT NULL
        REFERENCES categories(id)
        ON DELETE RESTRICT,
    source_product_id VARCHAR(100) UNIQUE,
    name VARCHAR(500) NOT NULL,
    brand VARCHAR(200),
    description TEXT,
    -- Definitive baseline price (e.g. ¥2,500)
    base_price_jpy INTEGER NOT NULL CHECK (base_price_jpy >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =========================================================
-- 4. PRODUCT IMAGES
-- =========================================================

CREATE TABLE product_images (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES products(id)
        ON DELETE CASCADE,
    -- MinIO object key, never a public URL. The Go service
    -- proxies it at GET /media/{key}.
    image_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(product_id, image_key)
);


-- =========================================================
-- 5. PRODUCT SIZES (Option C: Price Adjustment / Delta)
-- =========================================================

CREATE TABLE product_sizes (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES products(id)
        ON DELETE CASCADE,
    -- stockroom ?sku= identifier this variant was crawled from
    source_sku_id VARCHAR(100),
    size_name VARCHAR(100) NOT NULL,
    -- Surcharge or discount relative to base_price_jpy (e.g., 0, 300, -100)
    price_adjustment_jpy INTEGER NOT NULL DEFAULT 0,
    UNIQUE(product_id, size_name)
);


-- =========================================================
-- 6. CART ITEMS
-- =========================================================

CREATE TABLE cart_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(id)
        ON DELETE CASCADE,
    product_size_id BIGINT NOT NULL
        REFERENCES product_sizes(id)
        ON DELETE RESTRICT,
    quantity INTEGER NOT NULL DEFAULT 1
        CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(user_id, product_id, product_size_id)
);


-- =========================================================
-- 7. ORDERS
-- =========================================================

CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL
        REFERENCES users(id)
        ON DELETE RESTRICT,
    order_number VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL DEFAULT 'confirmed'
        CHECK (
            status IN (
                'pending',
                'confirmed',
                'cancelled'
            )
        ),
    shipping_address TEXT NOT NULL,
    total_jpy INTEGER NOT NULL
        CHECK (total_jpy >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =========================================================
-- 8. ORDER ITEMS (Immutable historical snapshot)
-- =========================================================

CREATE TABLE order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES orders(id)
        ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(id)
        ON DELETE RESTRICT,
    product_size_id BIGINT
        REFERENCES product_sizes(id)
        ON DELETE SET NULL,
    product_name VARCHAR(500) NOT NULL,
    size_name VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    -- Stores the final computed unit price: (base_price + price_adjustment)
    unit_price_jpy INTEGER NOT NULL
        CHECK (unit_price_jpy >= 0),
    subtotal_jpy INTEGER NOT NULL
        CHECK (subtotal_jpy >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =========================================================
-- PERFORMANCE INDEXES
-- =========================================================

CREATE INDEX idx_products_category_id ON products(category_id);
CREATE INDEX idx_product_images_product_id ON product_images(product_id);
CREATE INDEX idx_product_sizes_product_id ON product_sizes(product_id);
CREATE INDEX idx_cart_items_user_id ON cart_items(user_id);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);