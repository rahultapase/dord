"""Read-only access to the parsed 1913 Webster's (data/webster1913.jsonl, data/headwords.txt)."""

from __future__ import annotations

import json
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def normalize(word: str) -> str:
    """Lowercase, trim, and fold accents/ligatures ('Aërial' -> 'aerial', 'Æon' -> 'aeon')."""
    s = word.strip().lower().replace("\u00e6", "ae").replace("\u0153", "oe")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


class Dictionary:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.jsonl_path = data_dir / "webster1913.jsonl"
        headwords_path = data_dir / "headwords.txt"
        words = headwords_path.read_text(encoding="utf-8").split("\n")
        self.headwords: frozenset[str] = frozenset(normalize(w) for w in words if w.strip())
        self.single_words: frozenset[str] = frozenset(w for w in self.headwords if w.isalpha())
        self._offsets: dict[str, list[int]] | None = None
        self._lock = threading.Lock()

    def __contains__(self, word: object) -> bool:
        return isinstance(word, str) and normalize(word) in self.headwords

    def __len__(self) -> int:
        return len(self.headwords)

    def _index(self) -> dict[str, list[int]]:
        with self._lock:
            if self._offsets is None:
                offsets: dict[str, list[int]] = {}
                with self.jsonl_path.open("rb") as f:
                    pos = f.tell()
                    for raw in iter(f.readline, b""):
                        entry = json.loads(raw)
                        for v in entry.get("variants") or [entry["word"]]:
                            offsets.setdefault(normalize(v), []).append(pos)
                        pos = f.tell()
                self._offsets = offsets
            return self._offsets

    def lookup(self, word: str) -> list[dict[str, Any]]:
        """Every entry whose headword line lists this spelling (MOTTLE v. t. and MOTTLE n. ...)."""
        found = self._index().get(normalize(word), [])
        out: list[dict[str, Any]] = []
        with self.jsonl_path.open("rb") as f:
            for pos in found:
                f.seek(pos)
                out.append(json.loads(f.readline()))
        return out


@lru_cache(maxsize=1)
def get_dictionary() -> Dictionary:
    return Dictionary()
