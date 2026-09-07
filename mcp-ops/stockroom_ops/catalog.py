"""Category tokens for the catalog View.

Resolution ("copy paper" -> copy_paper_toner) lives in the Go service: it
already holds the category list, so doing it there is one request instead of
two. All that is left here is accepting whatever shape a model sends.
"""

from __future__ import annotations

import re
from typing import Any


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
