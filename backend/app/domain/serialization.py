from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any


def canonical_json(value: Any) -> str:
    """Stable JSON used for hashes and byte-for-byte comparisons."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def json_scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
