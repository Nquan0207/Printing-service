from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CategoryConfig:
    industry: str
    industry_name: str
    category: str
    category_name: str
    source_url: str
    enabled: bool = True
    max_products: int = 8


def load_categories(path: str | Path | None = None) -> list[CategoryConfig]:
    config_path = Path(path or os.getenv("CRAWLER_CONFIG", "categories.json"))
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    global_cap = int(os.getenv("MAX_PRODUCTS_PER_CATEGORY", "10"))
    return [
        CategoryConfig(**(item | {"max_products": min(int(item.get("max_products", 8)), global_cap)}))
        for item in raw["categories"]
    ]


MAX_PRODUCTS_TOTAL = int(os.getenv("MAX_PRODUCTS_TOTAL", "100"))
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "1.25"))
