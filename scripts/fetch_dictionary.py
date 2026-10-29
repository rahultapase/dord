"""Download Webster's Revised Unabridged Dictionary (1913), Project Gutenberg #29765.

The Gutenberg server drops long downloads part-way, so this resumes with HTTP Range requests
until the file is complete, then checks the Gutenberg END marker and prints the SHA-256.

    uv run python scripts/fetch_dictionary.py

Output: data/raw/webster1913.txt (gitignored, ~27.6 MB).
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import httpx

URL = "https://www.gutenberg.org/cache/epub/29765/pg29765.txt"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "webster1913.txt"
PART = OUT.with_suffix(".txt.part")
END_MARKER = b"END OF THE PROJECT GUTENBERG"
MAX_TRIES = 12
CHUNK = 1 << 16


def _download() -> None:
    PART.parent.mkdir(parents=True, exist_ok=True)
    total: int | None = None
    for attempt in range(1, MAX_TRIES + 1):
        have = PART.stat().st_size if PART.exists() else 0
        if total is not None and have >= total:
            return
        headers = {"Range": f"bytes={have}-"} if have else {}
        print(f"try {attempt}: starting at {have:,} bytes", flush=True)
        try:
            with httpx.stream("GET", URL, headers=headers, timeout=60, follow_redirects=True) as r:
                if r.status_code == 416:  # range starts at or past the end: already complete
                    return
                r.raise_for_status()
                if have and r.status_code != 206:
                    print("server ignored Range; starting over", flush=True)
                    have = 0
                    PART.unlink(missing_ok=True)
                if r.status_code == 206:
                    crange = r.headers.get("content-range", "")  # bytes a-b/total
                    if "/" in crange and crange.rsplit("/", 1)[1].isdigit():
                        total = int(crange.rsplit("/", 1)[1])
                elif r.headers.get("content-length", "").isdigit():
                    total = int(r.headers["content-length"])
                with PART.open("ab") as f:
                    for chunk in r.iter_bytes(CHUNK):
                        f.write(chunk)
            size = PART.stat().st_size
            if total is None or size >= total:
                return
            print(f"connection closed at {size:,} of {total:,} bytes", flush=True)
        except httpx.HTTPError as exc:
            print(f"dropped: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(min(2 * attempt, 10))
    raise SystemExit(f"gave up after {MAX_TRIES} tries")


def _verify(path: Path) -> str:
    data = path.read_bytes()
    if END_MARKER not in data[-30000:]:
        raise SystemExit(f"{path.name}: END marker missing, file is incomplete")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    if OUT.exists():
        print(f"{OUT.relative_to(ROOT)} already present")
    else:
        _download()
        _verify(PART)
        PART.replace(OUT)
    digest = _verify(OUT)
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size:,} bytes, END marker OK")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
