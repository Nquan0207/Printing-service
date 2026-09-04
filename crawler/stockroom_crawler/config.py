"""Crawl settings and the fixed top-level category whitelist."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://stockroom.raksul.com"
SITEMAP_INDEX_URL = "https://public-assets-stockroom.raksul.com/sitemaps/sitemap_index.xml"
USER_AGENT = "RAKSULStockroomPoC/1.0 (+local hackweek catalog; respectful crawler)"

# Size labels applied to a product's variants, cheapest first.
SIZE_LABELS = ("S", "M", "L")

# The 16 top-level tiles on the stockroom landing page. Subcategories are
# traversed during discovery but never persisted -- products attach to their
# L1 ancestor.
TOP_LEVEL_CATEGORIES: dict[str, str] = {
    "stationery_office_supplies": "文房具・事務用品",
    "files": "ファイル",
    "copy_paper_toner": "コピー用紙・OA用紙・トナー・インク",
    "office_furniture_interior_exterior": "オフィス家具・インテリア・エクステリア",
    "pc_peripherals_media": "パソコン周辺機器・メディア・プリンタ",
    "office_electronics_lighting": "事務機器・電化製品・照明・電池",
    "daily_life_goods": "日用品・生活雑貨",
    "drinks_food": "ドリンク・フード",
    "store_supplies": "店舗用品",
    "tape_packing_logistics": "テープ・梱包資材・物流用品",
    "nursing_medical_care": "看護・医療・介護",
    "research_equipment": "研究用総合機器",
    "tools_power_measuring": "工具・電動工具・切削工具・計測用品",
    "work_office_wear": "作業服・オフィスウエア",
    "agricultural_supplies": "農業関連用品",
    "gifts": "ギフト",
}


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    max_products: int
    sizes_per_product: int
    max_images: int
    request_delay: float

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.getenv("STOCKROOM_DATABASE_URL")
        if not url:
            raise RuntimeError(
                "STOCKROOM_DATABASE_URL is required; copy .env.example to .env"
            )
        return cls(
            database_url=url,
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            minio_bucket=os.getenv("MINIO_BUCKET", "stockroom-media"),
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            max_products=_int("CRAWL_MAX_PRODUCTS", 150),
            sizes_per_product=_int("CRAWL_SIZES_PER_PRODUCT", len(SIZE_LABELS)),
            max_images=_int("CRAWL_MAX_IMAGES", 3),
            request_delay=float(os.getenv("CRAWL_REQUEST_DELAY", "1.25")),
        )
