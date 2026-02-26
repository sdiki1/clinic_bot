from __future__ import annotations

import hashlib
import re


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 10:
        return None
    return f"+{digits}"


def mask_phone(normalized_phone: str) -> str:
    digits = re.sub(r"\D", "", normalized_phone)
    if len(digits) <= 4:
        return f"+{digits}"
    visible_prefix = min(2, len(digits) - 4)
    hidden = max(0, len(digits) - visible_prefix - 4)
    return f"+{digits[:visible_prefix]}{'*' * hidden}{digits[-4:]}"


def hash_phone(normalized_phone: str, salt: str) -> str:
    value = f"{salt}:{normalized_phone}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()
