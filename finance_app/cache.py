from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ResultCache(Protocol):
    def get(self, key: str) -> dict | None:
        ...

    def set(self, key: str, value: dict) -> None:
        ...

    def clear(self) -> None:
        ...


class NullResultCache:
    def get(self, key: str) -> dict | None:
        return None

    def set(self, key: str, value: dict) -> None:
        return None

    def clear(self) -> None:
        return None


class JSONResultCache:
    def __init__(self, cache_dir: str | Path, max_age_seconds: int = 3600) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_seconds = max_age_seconds

    def get(self, key: str) -> dict | None:
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        created_at = float(payload.get("created_at", 0))
        if created_at <= 0 or time.time() - created_at > self.max_age_seconds:
            return None
        value = payload.get("value")
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict) -> None:
        path = self._path_for_key(key)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        payload = {"created_at": time.time(), "value": value}
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temp_path.replace(path)

    def clear(self) -> None:
        if not self.cache_dir.exists():
            return
        for path in self.cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass

    def _path_for_key(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("cache key must be a SHA-256 hex digest")
        return self.cache_dir / f"{key}.json"
