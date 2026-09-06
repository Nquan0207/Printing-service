"""Grouping and category selection for the catalog View.

The admin products endpoint returns a flat list, each product carrying its
category, so grouping and multi-category filtering happen here rather than in
the Go service. At PoC scale (~60 products, capped at 500 server-side) that is
free, and it keeps the API surface unchanged.
"""

from __future__ import annotations

import re
from typing import Any


def _fold(text: str) -> str:
    """Strip separators so "copy paper" matches "copy_paper_toner"."""
    return re.sub(r"[\s_\-/·・]+", "", text.lower())


def normalize_tokens(raw: Any) -> list[str]:
    """Accept whatever a model actually sends.

    Models pass ["files"], "files", "files,drinks", or ["files, drinks"]
    interchangeably. Rejecting the last three is a bug on our side, not theirs,
    so everything is flattened to a list of single tokens.
    """
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple, set)) else [raw]
    out: list[str] = []
    for item in items:
        for part in re.split(r"[,;、，\n]+", str(item)):
            part = part.strip()
            if part:
                out.append(part)
    return out


def resolve_categories(
    tokens: Any, categories: list[dict[str, Any]]
) -> tuple[set[str], list[str]]:
    """Turn what the model asked for into real slugs.

    A model rarely knows the slug. It might say "copy paper", "コピー用紙", or
    "copy_paper_toner" — all three should work, so each token is matched
    case-insensitively against both the slug and the display name, with
    separators folded. Returns (matched slugs, tokens that matched nothing).

    Resolution happens here, but *filtering* happens in SQL: the resolved slugs
    go to the API, which does the work.
    """
    requested = normalize_tokens(tokens)
    if not requested:
        return set(), []

    known = {c["slug"]: c.get("name", "") for c in categories if c.get("slug")}

    matched: set[str] = set()
    unmatched: list[str] = []
    for raw in requested:
        token = _fold(raw)
        if not token:
            continue
        hits = {
            slug
            for slug, name in known.items()
            if token in _fold(slug) or token in _fold(name)
        }
        if hits:
            matched |= hits
        else:
            unmatched.append(str(raw))
    return matched, unmatched


def group_by_category(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group into rendered sections, largest first, then by name.

    An empty group is never emitted: a section header with nothing under it
    reads as a bug.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for product in products:
        category = product.get("category") or {}
        slug = category.get("slug") or "uncategorised"
        bucket = buckets.setdefault(
            slug,
            {
                "category": {"slug": slug, "name": category.get("name", slug)},
                "products": [],
            },
        )
        bucket["products"].append(product)

    groups = [g for g in buckets.values() if g["products"]]
    for group in groups:
        group["count"] = len(group["products"])
    groups.sort(key=lambda g: (-g["count"], g["category"]["name"]))
    return groups


def available_categories(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chips for the View: every category, with its size, largest first."""
    out = [
        {"slug": c["slug"], "name": c.get("name", c["slug"]), "count": c.get("product_count", 0)}
        for c in categories
        if c.get("slug")
    ]
    return sorted(out, key=lambda c: (-c["count"], c["name"]))
