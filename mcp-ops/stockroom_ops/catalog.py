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
    tokens: Any, products: list[dict[str, Any]]
) -> tuple[set[str], list[str]]:
    """Turn what the model asked for into real slugs.

    A model rarely knows the slug. It might say "copy paper", "コピー用紙", or
    "copy_paper_toner" — all three should work, so each token is matched
    case-insensitively against both the slug and the display name, as a
    substring. Returns (matched slugs, tokens that matched nothing).
    """
    requested = normalize_tokens(tokens)
    if not requested:
        return set(), []

    known: dict[str, str] = {}
    for product in products:
        category = product.get("category") or {}
        slug = category.get("slug")
        if slug:
            known[slug] = category.get("name", "")

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


def available_categories(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every category present in the unfiltered catalog, for the View's chips."""
    counts: dict[str, dict[str, Any]] = {}
    for product in products:
        category = product.get("category") or {}
        slug = category.get("slug")
        if not slug:
            continue
        entry = counts.setdefault(
            slug, {"slug": slug, "name": category.get("name", slug), "count": 0}
        )
        entry["count"] += 1
    return sorted(counts.values(), key=lambda c: (-c["count"], c["name"]))
