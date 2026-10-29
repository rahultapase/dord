"""Small, careful client for the local Ollama server.

Ollama crashed once on this laptop (CUDA error) when two requests ran at the same time, so every
call goes through one process-wide lock: one request at a time. Each call has a timeout and is
retried once after a short pause. Only 127.0.0.1 is ever contacted.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"

GEN_MODEL = "gemma4:e2b"  # writes fakes and bluffs, plays the seance
SMALL_MODEL = "gemma3:1b"  # second seance player
EMBED_MODEL = "qwen3-embedding:0.6b"  # similarity check for bluffs
REQUIRED_MODELS = (GEN_MODEL, SMALL_MODEL, EMBED_MODEL)

DEFAULT_NUM_CTX = 8192  # Ollama defaults to 4096; 8192 fits in 4 GB VRAM with gemma4:e2b
RETRY_PAUSE_S = 3.0

_lock = threading.Lock()


class OllamaError(RuntimeError):
    """Ollama could not be reached or returned an error after one retry."""


def _post(path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    last = ""
    for attempt in range(2):
        if attempt:
            time.sleep(RETRY_PAUSE_S)
        try:
            with _lock:
                resp = httpx.post(f"{OLLAMA_URL}{path}", json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            last = f"{path}: {type(exc).__name__}: {exc}"
            continue
        if resp.status_code < 400:
            return resp.json()
        last = f"{path} returned {resp.status_code}: {resp.text[:200]}"
        if resp.status_code < 500:
            break  # unknown model or bad request: retrying will not help
    raise OllamaError(last)


def generate(
    prompt: str,
    *,
    model: str = GEN_MODEL,
    system: str | None = None,
    temperature: float = 0.7,
    json_mode: bool = False,
    seed: int | None = None,
    num_predict: int | None = None,
    num_ctx: int = DEFAULT_NUM_CTX,
    think: bool | None = False,
    timeout: float = 180.0,
) -> str:
    """Return the model's full response text (non-streaming).

    gemma4 "thinks" by default, and the thinking tokens count against num_predict (a 40-token
    budget came back with an empty response). Thinking is off unless asked for; None leaves the
    model's default.
    """
    options: dict[str, Any] = {"temperature": temperature, "num_ctx": num_ctx}
    if seed is not None:
        options["seed"] = seed
    if num_predict is not None:
        options["num_predict"] = num_predict
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    if think is not None:
        payload["think"] = think
    if system:
        payload["system"] = system
    if json_mode:
        payload["format"] = "json"
    data = _post("/api/generate", payload, timeout)
    return str(data.get("response", ""))


def generate_json(prompt: str, **kwargs: Any) -> Any:
    """Generate with JSON output and parse it. Raises ValueError if it is not valid JSON."""
    text = generate(prompt, json_mode=True, **kwargs)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model did not return valid JSON: {text[:200]!r}") from exc


def embed(texts: list[str], *, model: str = EMBED_MODEL, timeout: float = 120.0) -> list[list[float]]:
    """Return one embedding vector per input text."""
    data = _post("/api/embed", {"model": model, "input": texts}, timeout)
    vectors = data.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise OllamaError(f"unexpected embed response: {str(data)[:200]}")
    return vectors


def list_models(timeout: float = 5.0) -> list[str]:
    """Names of the locally pulled models. Raises OllamaError if Ollama is unreachable."""
    try:
        with _lock:
            resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama not reachable at {OLLAMA_URL}: {exc}") from exc
    return [m.get("name", "") for m in resp.json().get("models", [])]


def health() -> dict[str, Any]:
    """Reachability plus which of the three required models are present."""
    try:
        names = set(list_models())
    except OllamaError as exc:
        return {"ollama": False, "error": str(exc), "models": {m: False for m in REQUIRED_MODELS}}
    models = {m: m in names for m in REQUIRED_MODELS}
    return {"ollama": True, "models": models, "ok": all(models.values())}
