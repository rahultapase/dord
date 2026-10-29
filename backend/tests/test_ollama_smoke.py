"""Smoke test: the three local models answer. Skipped when Ollama is not running."""

import math

import pytest

from backend import ollama_client as oc

pytestmark = pytest.mark.ollama


@pytest.fixture(scope="module", autouse=True)
def _needs_ollama():
    status = oc.health()
    if not status["ollama"]:
        pytest.skip(f"Ollama not running: {status.get('error')}")
    missing = [m for m, ok in status["models"].items() if not ok]
    if missing:
        pytest.fail(f"models not pulled: {missing}")


@pytest.mark.parametrize("model", [oc.GEN_MODEL, oc.SMALL_MODEL])
def test_generate_json(model):
    out = oc.generate_json(
        'Reply with this JSON and nothing else: {"answer": "real"}',
        model=model,
        temperature=0,
        num_predict=40,
    )
    assert isinstance(out, dict)
    assert "answer" in out


def test_embed():
    vecs = oc.embed(["a hash of various kinds of meats", "any absurd medley"])
    assert len(vecs) == 2
    assert len(vecs[0]) == len(vecs[1]) > 100
    assert all(math.isfinite(x) for x in vecs[0][:20])
