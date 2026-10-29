"""API tests with FastAPI's test client. Gemma is replaced by a stub; no Ollama needed."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from backend import game as game_mod
from backend import main
from backend.dictionary import DATA_DIR

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "ghosts.json").exists(), reason="data files not built"
)

SECRET_KEYS = {"kind", "truth", "correct", "source", "id", "etym", "line", "model", "batch", "proof"}


def stub_ask(mode, word, definition="", options=None):
    return "real" if mode == "real-or-ghost" else 1


@pytest.fixture()
def client(monkeypatch):
    eng = game_mod.Engine(ask=stub_ask, seed=13)
    monkeypatch.setattr(main, "engine", eng)
    return TestClient(main.app)


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def assert_no_answer(card: dict, engine) -> None:
    """The card must not carry the answer: no secret keys, and nothing that only one kind has."""
    assert not SECRET_KEYS & set(walk_keys(card)), card
    game = next(g for g in engine.games.values() if any(c.word == card["word"] for c in g.cards))
    c = next(c for c in game.cards if c.word == card["word"])
    if c.kind == "ghost":
        assert c.source["id"] not in json.dumps(card)


def test_health(client, monkeypatch):
    monkeypatch.setattr(main.oc, "health", lambda: {"ollama": True, "models": {}, "ok": True})
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["headwords"] > 100_000 and body["reals"] == 150


def test_real_or_ghost_full_game(client):
    r = client.post("/api/game", json={"mode": "real-or-ghost", "rounds": 20})
    assert r.status_code == 200
    g = r.json()
    gid, card = g["id"], g["card"]
    kinds = []
    for n in range(1, 21):
        assert card["n"] == n
        assert_no_answer(card, main.engine)
        assert set(card) == {"n", "rounds", "mode", "word", "pos", "definition"}
        res = client.post(f"/api/game/{gid}/answer", json={"n": n, "choice": "real"}).json()
        kinds.append(res["kind"])
        assert res["truth"] == res["kind"]
        assert res["correct"] == (res["kind"] == "real")
        assert res["gemma"]["answer"] == "real" and res["gemma"]["source"] == "live"
        if res["kind"] == "real":
            assert res["proof"]["entry"]["senses"]
            assert "1913" in res["proof"]["text"]
        else:
            assert "no trace" in res["proof"]["text"]
            assert [c["code"] for c in res["proof"]["checks"]][:2] == ["shape", "1913"]
        if n < 20:
            assert res["next"] == n + 1
            card = client.get(f"/api/game/{gid}/card/{n + 1}").json()["card"]
        else:
            assert res["next"] is None
    assert 8 <= kinds.count("ghost") <= 12
    final = res["scores"]
    assert final["finished"] and final["you"] == kinds.count("real") == final["gemma"]
    summary = client.get(f"/api/game/{gid}/summary").json()
    assert len(summary["rounds"]) == 20


def test_three_defs_game(client):
    g = client.post("/api/game", json={"mode": "three-defs", "rounds": 20}).json()
    gid, card = g["id"], g["card"]
    for n in range(1, 21):
        assert_no_answer(card, main.engine)
        assert len(card["options"]) == 3 and "definition" not in card
        res = client.post(f"/api/game/{gid}/answer", json={"n": n, "choice": 2}).json()
        assert res["truth"] in (1, 2, 3)
        real_def = next(r for r in main.engine.reals if r["word"] == res["word"])["definition"]
        assert res["options"][res["truth"] - 1] == real_def
        assert res["gemma"]["correct"] == (res["truth"] == 1)
        if res["next"]:
            card = client.get(f"/api/game/{gid}/card/{res['next']}").json()["card"]
    assert res["scores"]["finished"]


def test_cannot_peek_ahead_or_answer_twice(client):
    g = client.post("/api/game", json={"mode": "real-or-ghost", "rounds": 5}).json()
    gid = g["id"]
    assert client.get(f"/api/game/{gid}/card/2").status_code == 409
    assert client.post(f"/api/game/{gid}/answer", json={"n": 2, "choice": "real"}).status_code == 409
    assert client.post(f"/api/game/{gid}/answer", json={"n": 1, "choice": "real"}).status_code == 200
    assert client.post(f"/api/game/{gid}/answer", json={"n": 1, "choice": "ghost"}).status_code == 409


def test_bad_input(client):
    assert client.post("/api/game", json={"mode": "seance"}).status_code == 422
    assert client.post("/api/game", json={"rounds": 0}).status_code == 422
    gid = client.post("/api/game", json={"rounds": 3}).json()["id"]
    assert client.post(f"/api/game/{gid}/answer", json={"n": 1, "choice": "maybe"}).status_code == 422
    assert client.get("/api/game/nope/card/1").status_code == 404


def test_vs_gemma_off(client):
    g = client.post("/api/game", json={"rounds": 2, "vsGemma": False}).json()
    res = client.post(f"/api/game/{g['id']}/answer", json={"n": 1, "choice": "real"}).json()
    assert res["gemma"] is None
    assert res["scores"]["gemma"] == 0


def test_gemma_down_falls_back_cleanly(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("ollama crashed")

    eng = game_mod.Engine(ask=broken, seed=2)
    monkeypatch.setattr(main, "engine", eng)
    c = TestClient(main.app)
    gid = c.post("/api/game", json={"rounds": 2}).json()["id"]
    res = c.post(f"/api/game/{gid}/answer", json={"n": 1, "choice": "ghost"}).json()
    assert res["gemma"]["answer"] is None
    assert res["scores"]["gemmaAnswered"] == 0


def test_slow_gemma_times_out(monkeypatch):
    def slow(*a, **k):
        time.sleep(1.0)
        return "real"

    monkeypatch.setattr(game_mod, "GEMMA_WAIT_S", 0.05)
    eng = game_mod.Engine(ask=slow, seed=3)
    monkeypatch.setattr(main, "engine", eng)
    c = TestClient(main.app)
    gid = c.post("/api/game", json={"rounds": 2}).json()["id"]
    res = c.post(f"/api/game/{gid}/answer", json={"n": 1, "choice": "ghost"}).json()
    assert res["gemma"]["source"] == "timeout"


def gemma_says(monkeypatch, *items, cut_after=None):
    """Stub Gemma's raw reply to the summon prompt; cut_after chops the text like a token limit."""
    text = json.dumps({"words": list(items)}, indent=2)
    if cut_after:
        text = text[:cut_after]
    monkeypatch.setattr(game_mod.oc, "generate", lambda *a, **k: text)


def test_summon_rejects_real_word(client, monkeypatch):
    gemma_says(monkeypatch, {"word": "quixotism", "pos": "n.", "definition": "A wild and foolish plan of action.",
                             "etym": "Sp."})
    res = client.post("/api/ghosts/summon").json()
    assert res["accepted"] is False
    assert res["code"] == "1913"
    assert res["entry"]["senses"][0]["text"].startswith("That form of delusion")


def test_summon_accepts_and_joins_next_game(client, monkeypatch):
    # Gemma wrote two words and the reply was cut off inside the second: the first still counts.
    first = {"word": "glimmerwain", "pos": "n.", "definition": "A pale light seen over marshes at night.",
             "etym": "glimmer + wain"}
    second = {"word": "hushbound", "pos": "adj.", "definition": "Kept in a state of profound silence.", "etym": "x"}
    gemma_says(monkeypatch, first, second, cut_after=len(json.dumps({"words": [first]}, indent=2)) + 40)
    res = client.post("/api/ghosts/summon").json()
    assert res["accepted"] is True, res
    assert "no trace" in res["reason"]
    g = client.post("/api/game", json={"rounds": 20}).json()
    words = [main.engine.games[g["id"]].cards[i].word for i in range(20)]
    assert "glimmerwain" in words


def test_seance_missing(client, monkeypatch):
    monkeypatch.setattr(main.engine, "seance", lambda: None)
    assert client.get("/api/seance").status_code == 404


def test_summon_rejects_hand_dropped_word(client, monkeypatch):
    gemma_says(monkeypatch, {"word": "occultum", "pos": "a.", "definition": "Hidden from common sight; secret.",
                             "etym": "L."})
    res = client.post("/api/ghosts/summon").json()
    assert res["accepted"] is False
    assert res["code"] == "hand" and "Latin" in res["reason"]


def test_seance_fallback_follows_the_shuffle(monkeypatch):
    # Gemma is down, so its answer comes from the seance. In Three Definitions the seance saw the
    # definitions in another order, so the fallback must find the same text, not the same number.
    def broken(*a, **k):
        raise RuntimeError("ollama crashed")

    eng = game_mod.Engine(ask=broken, seed=5)
    monkeypatch.setattr(main, "engine", eng)
    c = TestClient(main.app)
    g = c.post("/api/game", json={"mode": "three-defs", "rounds": 2}).json()
    first = eng.games[g["id"]].cards[0]
    true_text = first.options[first.correct - 1]
    eng._seance_answers = {("three-defs", first.word): true_text}
    res = c.post(f"/api/game/{g['id']}/answer", json={"n": 1, "choice": 1}).json()
    assert res["gemma"]["source"] == "seance"
    assert res["gemma"]["answer"] == first.correct
    assert res["gemma"]["correct"] is True
