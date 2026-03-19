from __future__ import annotations

import json
import math
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
VEC_DIM = 256


@dataclass(slots=True)
class MemoryItem:
    text: str
    created_at: str


class PersonalMemory:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self) -> list[dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write(self, data: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, text: str) -> MemoryItem:
        item = MemoryItem(text=text.strip(), created_at=datetime.now().isoformat(timespec="seconds"))
        data = self._read()
        data.append({"text": item.text, "created_at": item.created_at})
        self._write(data)
        return item

    def all(self, limit: int = 50) -> list[MemoryItem]:
        data = self._read()[-limit:]
        return [MemoryItem(text=x.get("text", ""), created_at=x.get("created_at", "")) for x in data]

    def search(self, query: str, top_k: int = 3) -> list[MemoryItem]:
        query = query.strip()
        if not query:
            return self.all(limit=top_k)

        q_vec = self._vectorize(query)
        q_tokens = set(TOKEN_RE.findall(query.lower()))
        if not q_vec:
            return self.all(limit=top_k)

        scored: list[tuple[float, MemoryItem]] = []
        for row in self._read():
            text = row.get("text", "")
            t_vec = self._vectorize(text)
            if not t_vec:
                continue
            sim = self._cosine(q_vec, t_vec)
            t_tokens = set(TOKEN_RE.findall(text.lower()))
            overlap = 0
            for qt in q_tokens:
                for tt in t_tokens:
                    if qt in tt or tt in qt:
                        overlap += 1
                        break
            lexical = overlap / max(1, len(q_tokens))

            if sim <= 0 and lexical <= 0:
                continue

            score = 0.65 * sim + 0.35 * lexical
            scored.append((score, MemoryItem(text=text, created_at=row.get("created_at", ""))))

        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return self.all(limit=top_k)
        return [x[1] for x in scored[:top_k]]

    def delete_by_query(self, query: str, limit: int = 3) -> int:
        query = query.strip().lower()
        if not query:
            return 0
        data = self._read()
        if not data:
            return 0

        q_tokens = set(TOKEN_RE.findall(query))
        kept: list[dict[str, Any]] = []
        removed = 0
        for row in data:
            text = str(row.get("text", ""))
            low = text.lower()
            t_tokens = set(TOKEN_RE.findall(low))
            matched = query in low or any(qt in tt or tt in qt for qt in q_tokens for tt in t_tokens)
            if matched and removed < limit:
                removed += 1
                continue
            kept.append(row)

        if removed > 0:
            self._write(kept)
        return removed

    def _feature_tokens(self, text: str) -> list[str]:
        low = text.lower()
        tokens = TOKEN_RE.findall(low)
        compact = re.sub(r"\s+", "", low)
        ngrams = [compact[i : i + 3] for i in range(max(0, len(compact) - 2))]
        return tokens + ngrams

    def _vectorize(self, text: str) -> list[float]:
        features = self._feature_tokens(text)
        if not features:
            return []
        vec = [0.0] * VEC_DIM
        for ft in features:
            digest = hashlib.md5(ft.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "big") % VEC_DIM
            vec[idx] += 1.0

        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return []
        return [x / norm for x in vec]

    def _cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        return sum(x * y for x, y in zip(a, b))
