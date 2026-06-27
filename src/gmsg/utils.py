"""Small shared helpers."""
from __future__ import annotations

import json
import re


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
