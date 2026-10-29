"""Game state: decks, rounds, scoring, Gemma's background guesses, live summoning.

Everything lives in memory (one local player). A card sent to the browser never says whether it
is real or which definition is true; that only comes back from answer(), after the player has
committed.
"""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from backend import ollama_client as oc
from backend import prompts
from backend.checks import Checker, card_text, definition_problem, pos_problem, tidy_definition
from backend.dictionary import DATA_DIR, get_dictionary

MODES = ("real-or-ghost", "three-defs")
MAX_ROUNDS = 40
GEMMA_WAIT_S = 8.0  # how long answer() waits for a guess still running
SEANCE_PATH = DATA_DIR / "seance-results.json"


def _load(name: str, default: Any) -> Any:
    path = DATA_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


class GameError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------- Gemma as the opponent

def _parse_answer(raw: Any, mode: str) -> str | int | None:
    val = raw.get("answer") if isinstance(raw, dict) else raw
    if mode == "real-or-ghost":
        s = str(val).strip().lower()
        if s.startswith("real"):
            return "real"
        if s.startswith(("ghost", "invent", "fake")):
            return "ghost"
        return None
    try:
        n = int(str(val).strip().strip("."))
    except ValueError:
        return None
    return n if n in (1, 2, 3) else None


def ask_gemma(mode: str, word: str, definition: str = "", options: list[str] | None = None,
              model: str = oc.GEN_MODEL) -> str | int | None:
    """One answer from the model for a card, or None if it gave nothing usable."""
    if mode == "real-or-ghost":
        prompt = prompts.real_or_ghost(word, definition)
    else:
        prompt = prompts.three_definitions(word, options or [])
    raw = oc.generate_json(prompt, model=model, temperature=0, seed=7, num_predict=24, timeout=60)
    return _parse_answer(raw, mode)


@dataclass
class Guess:
    answer: str | int | None = None
    source: str = "pending"  # live / seance / none
    seconds: float = 0.0
    done: threading.Event = field(default_factory=threading.Event)


# ---------------------------------------------------------------- cards and games

@dataclass
class Card:
    n: int
    word: str
    pos: str
    kind: str  # real / ghost (never sent before the answer)
    definition: str = ""  # what the card shows (real-or-ghost)
    options: list[str] = field(default_factory=list)  # three-defs
    correct: int = 0  # 1-based index of the true definition (three-defs)
    source: dict[str, Any] = field(default_factory=dict)  # the real or ghost record
    answer: str | int | None = None
    guess: Guess | None = None

    def public(self, mode: str, rounds: int) -> dict[str, Any]:
        d: dict[str, Any] = {"n": self.n, "rounds": rounds, "mode": mode, "word": self.word, "pos": self.pos}
        if mode == "real-or-ghost":
            d["definition"] = self.definition
        else:
            d["options"] = self.options
        return d


@dataclass
class Game:
    id: str
    mode: str
    rounds: int
    vs_gemma: bool
    cards: list[Card]
    current: int = 1  # the card being played (1-based)
    you: int = 0
    gemma: int = 0
    gemma_answered: int = 0
    created: float = field(default_factory=time.time)

    @property
    def finished(self) -> bool:
        return self.current > self.rounds

    def scores(self) -> dict[str, Any]:
        return {"you": self.you, "gemma": self.gemma, "gemmaAnswered": self.gemma_answered,
                "round": min(self.current, self.rounds), "rounds": self.rounds, "finished": self.finished}


class Engine:
    def __init__(self, ask: Callable[..., str | int | None] = ask_gemma, seed: int | None = None) -> None:
        self.ask = ask
        self.rng = random.Random(seed)
        self.checker = Checker()
        self.dictionary = get_dictionary()
        self.reals: list[dict] = _load("reals.json", [])
        self.ghosts: list[dict] = _load("ghosts.json", [])
        bluffs: dict = _load("bluffs.json", {})
        self.bluffs = {k: [b["text"] for b in v["bluffs"]] for k, v in bluffs.items() if len(v["bluffs"]) >= 2}
        self.summoned: list[dict] = []  # live ghosts, played first in the next real-or-ghost game
        # Words rejected by hand when the deck was built (real words the lists miss, plain Latin ...)
        self.hand_rejected = {x["word"]: x for x in _load("ghost-rejections.json", {}).get("items", [])
                              if x.get("code") == "hand" and x.get("word")}
        self.games: dict[str, Game] = {}
        self._guess_cache: dict[tuple, tuple[str | int | None, float]] = {}
        self._seance_answers = self._load_seance_answers()
        self._lock = threading.Lock()

    # ---- seance fallback

    @staticmethod
    def _load_seance_answers() -> dict[tuple, str | int]:
        """(mode, word) -> gemma4:e2b's seance answer, if the seance has been run.

        Real or Ghost keeps "real" / "ghost". Three Definitions keeps the text of the definition
        Gemma picked, because every game shuffles the three definitions differently.
        """
        data = _load("seance-results.json", {})
        out: dict[tuple, str | int] = {}
        for row in data.get("answers", []):
            if row.get("model") != oc.GEN_MODEL or row.get("answer") is None:
                continue
            if row.get("mode") == "real-or-ghost":
                out[("real-or-ghost", row.get("word"))] = row["answer"]
            elif row.get("mode") == "three-defs" and row.get("answerText"):
                out[("three-defs", row.get("word"))] = row["answerText"]
        return out

    def _seance_fallback(self, game: Game, card: Card) -> str | int | None:
        found = self._seance_answers.get((game.mode, card.word))
        if game.mode == "three-defs":
            return card.options.index(found) + 1 if found in card.options else None
        return found

    # ---- deck building

    def _real_card(self, n: int, r: dict) -> Card:
        return Card(n=n, word=r["word"], pos=r["pos"], kind="real", definition=r["definition"], source=r)

    def _ghost_card(self, n: int, g: dict) -> Card:
        return Card(n=n, word=g["word"], pos=g["pos"], kind="ghost", definition=card_text(g["definition"]), source=g)

    def _deal_real_or_ghost(self, rounds: int) -> list[Card]:
        n_ghost = rounds // 2 + self.rng.choice([-1, 0, 0, 1]) if rounds > 3 else rounds // 2
        n_ghost = max(0, min(rounds, n_ghost))
        summoned = self.summoned[:n_ghost]
        self.summoned = self.summoned[len(summoned):]
        ghosts = summoned + self.rng.sample(self.ghosts, n_ghost - len(summoned))
        reals = self.rng.sample(self.reals, rounds - n_ghost)
        picks = [("ghost", g) for g in ghosts] + [("real", r) for r in reals]
        self.rng.shuffle(picks)
        return [self._ghost_card(i, x) if k == "ghost" else self._real_card(i, x) for i, (k, x) in enumerate(picks, 1)]

    def _deal_three_defs(self, rounds: int) -> list[Card]:
        pool = [r for r in self.reals if r["id"] in self.bluffs]
        cards = []
        for i, r in enumerate(self.rng.sample(pool, rounds), 1):
            options = [r["definition"], *(card_text(b) for b in self.bluffs[r["id"]][:2])]
            order = [0, 1, 2]
            self.rng.shuffle(order)
            shown = [options[j] for j in order]
            cards.append(Card(n=i, word=r["word"], pos=r["pos"], kind="real", options=shown,
                              correct=order.index(0) + 1, source=r))
        return cards

    def new_game(self, mode: str, rounds: int = 20, vs_gemma: bool = True) -> dict[str, Any]:
        if mode not in MODES:
            raise GameError(422, f"mode must be one of {MODES}")
        limit = len(self.bluffs) if mode == "three-defs" else min(len(self.reals), len(self.ghosts))
        if not 1 <= rounds <= min(MAX_ROUNDS, limit):
            raise GameError(422, f"rounds must be 1-{min(MAX_ROUNDS, limit)}")
        with self._lock:
            cards = self._deal_real_or_ghost(rounds) if mode == "real-or-ghost" else self._deal_three_defs(rounds)
            game = Game(id=uuid.uuid4().hex[:12], mode=mode, rounds=rounds, vs_gemma=vs_gemma, cards=cards)
            self.games[game.id] = game
            if len(self.games) > 50:  # one local player; forget the oldest games
                for old in sorted(self.games.values(), key=lambda g: g.created)[:-50]:
                    self.games.pop(old.id, None)
        self._start_guess(game, cards[0])
        return {"id": game.id, "mode": mode, "rounds": rounds, "vsGemma": vs_gemma,
                "card": cards[0].public(mode, rounds), "scores": game.scores()}

    def get(self, game_id: str) -> Game:
        game = self.games.get(game_id)
        if game is None:
            raise GameError(404, "no such game")
        return game

    def card(self, game_id: str, n: int) -> dict[str, Any]:
        game = self.get(game_id)
        if game.finished:
            raise GameError(409, "the game is over")
        if n != game.current:
            raise GameError(409, f"card {game.current} is the one in play")
        card = game.cards[n - 1]
        self._start_guess(game, card)
        return {"card": card.public(game.mode, game.rounds), "scores": game.scores()}

    # ---- Gemma's background guess

    def _start_guess(self, game: Game, card: Card) -> None:
        if not game.vs_gemma or card.guess is not None:
            return
        card.guess = Guess()
        key = (game.mode, card.word, card.definition, tuple(card.options))
        cached = self._guess_cache.get(key)
        if cached is not None:
            card.guess.answer, card.guess.seconds = cached
            card.guess.source = "live" if cached[0] is not None else "none"
            card.guess.done.set()
            return
        threading.Thread(target=self._run_guess, args=(game.mode, card, key), daemon=True).start()

    def _run_guess(self, mode: str, card: Card, key: tuple) -> None:
        g = card.guess
        assert g is not None
        t0 = time.time()
        try:
            g.answer = self.ask(mode, card.word, card.definition, card.options)
            g.source = "live" if g.answer is not None else "none"
        except Exception:  # Ollama down, bad JSON: fall back below
            g.answer, g.source = None, "none"
        g.seconds = round(time.time() - t0, 1)
        if g.answer is not None:
            self._guess_cache[key] = (g.answer, g.seconds)
        g.done.set()

    def _gemma_result(self, game: Game, card: Card) -> dict[str, Any] | None:
        if not game.vs_gemma:
            return None
        g = card.guess
        if g is not None:
            g.done.wait(GEMMA_WAIT_S)
        answer, source, seconds = (g.answer, g.source, g.seconds) if g and g.done.is_set() else (None, "pending", 0.0)
        if answer is None:
            fallback = self._seance_fallback(game, card)
            if fallback is not None:
                answer, source = fallback, "seance"
        if answer is None:
            return {"answer": None, "source": "none" if source != "pending" else "timeout", "correct": None}
        return {"answer": answer, "source": source, "seconds": seconds, "correct": answer == self._truth(card, game.mode)}

    # ---- answering

    @staticmethod
    def _truth(card: Card, mode: str) -> str | int:
        return card.kind if mode == "real-or-ghost" else card.correct

    def _proof(self, card: Card) -> dict[str, Any]:
        if card.kind == "real":
            entries = self.dictionary.lookup(card.word)
            e = next((x for x in entries if x.get("line") == card.source.get("line")), entries[0] if entries else {})
            return {
                "kind": "real",
                "text": f"Found in Webster's Revised Unabridged Dictionary, 1913 (line {e.get('line', '?'):,} of the Project Gutenberg text).",
                "entry": {k: e.get(k) for k in ("headline", "pron", "pos", "etym", "labels", "line")}
                | {"senses": (e.get("senses") or [])[:3]},
            }
        v = self.checker.check(card.word)
        src = card.source
        return {
            "kind": "ghost",
            "text": self.checker.proof_text() if v.ghost else v.reason,
            "checks": [{"code": c, "label": _CHECK_LABELS.get(c, c)} for c in v.checks],
            "headwords": self.checker.headword_count,
            "ghost": {"definition": src.get("definition", ""), "etym": src.get("etym", ""),
                      "model": src.get("model", oc.GEN_MODEL), "summoned": bool(src.get("summoned"))},
        }

    def answer(self, game_id: str, n: int, choice: str | int) -> dict[str, Any]:
        game = self.get(game_id)
        if game.finished or n != game.current:
            raise GameError(409, f"card {game.current} is the one in play" if not game.finished else "the game is over")
        card = game.cards[n - 1]
        if game.mode == "real-or-ghost":
            choice = str(choice).strip().lower()
            if choice not in ("real", "ghost"):
                raise GameError(422, "choice must be 'real' or 'ghost'")
        else:
            try:
                choice = int(choice)
            except (TypeError, ValueError):
                raise GameError(422, "choice must be 1, 2 or 3") from None
            if choice not in (1, 2, 3):
                raise GameError(422, "choice must be 1, 2 or 3")
        truth = self._truth(card, game.mode)
        gemma = self._gemma_result(game, card)
        with self._lock:
            if n != game.current:  # a double submit raced us
                raise GameError(409, "already answered")
            card.answer = choice
            correct = choice == truth
            game.you += int(correct)
            if gemma and gemma["answer"] is not None:
                game.gemma_answered += 1
                game.gemma += int(bool(gemma["correct"]))
            game.current += 1
        result = {
            "n": n, "choice": choice, "correct": correct, "truth": truth, "kind": card.kind,
            "word": card.word, "pos": card.pos, "proof": self._proof(card), "gemma": gemma,
            "scores": game.scores(), "next": None if game.finished else game.current,
        }
        if game.mode == "three-defs":
            result["options"] = card.options
        if not game.finished and game.vs_gemma:
            self._start_guess(game, game.cards[game.current - 1])  # think about the next card early
        return result

    def summary(self, game_id: str) -> dict[str, Any]:
        game = self.get(game_id)
        rows = []
        for c in game.cards[: game.current - 1]:
            rows.append({"n": c.n, "word": c.word, "kind": c.kind, "you": c.answer,
                         "truth": self._truth(c, game.mode),
                         "gemma": c.guess.answer if c.guess and c.guess.done.is_set() else None})
        return {"id": game.id, "mode": game.mode, "scores": game.scores(), "rounds": rows}

    # ---- live summoning

    def warm_up(self) -> None:
        """Load Gemma into memory so the first card's guess is not lost to a ~20 s cold start."""
        def run() -> None:
            try:
                oc.generate("Say ok.", num_predict=2, timeout=120)
            except oc.OllamaError:
                pass
        threading.Thread(target=run, daemon=True).start()

    def summon(self) -> dict[str, Any]:
        theme = self.rng.choice(prompts.GHOST_THEMES)
        t0 = time.time()
        try:
            # Gemma usually writes several words; the reply may be cut off mid-list. Keep the first.
            reply = oc.generate(prompts.summon_one(theme), json_mode=True, temperature=0.9,
                                seed=self.rng.randint(1, 10**6), num_predict=300, timeout=60)
        except oc.OllamaError as exc:
            raise GameError(503, f"Gemma did not answer: {exc}") from None
        seconds = round(time.time() - t0, 1)
        item = prompts.first_object(reply)
        if item is None:
            raise GameError(503, "Gemma returned no word")
        word = str(item.get("word", "")).strip()
        pos = str(item.get("pos", "")).strip()
        pos = {"v.": "v. t.", "v": "v. t.", "adj.": "a.", "adj": "a."}.get(pos, pos)
        definition = tidy_definition(item.get("definition", ""))
        deck = {g["word"] for g in self.ghosts} | {g["word"] for g in self.summoned} | {r["word"] for r in self.reals}
        v = self.checker.check(word, deck=deck)
        out: dict[str, Any] = {"word": v.word or word, "pos": pos, "definition": definition,
                               "etym": str(item.get("etym", "")).strip(), "theme": theme, "seconds": seconds,
                               "model": oc.GEN_MODEL,
                               "checks": [{"code": c, "label": _CHECK_LABELS.get(c, c)} for c in v.checks]}
        problem = None
        if v.ghost and v.word in self.hand_rejected:
            v.ghost, v.code = False, "hand"
            v.reason = f"'{v.word}' was rejected by hand when the deck was built: {self.hand_rejected[v.word]['reason']}."
        if v.ghost:
            problem = definition_problem(v.word, definition) or pos_problem(pos, definition)
            if problem is None and pos not in prompts.POS_CHOICES:
                problem = f"part of speech {pos!r}"
        if v.ghost and problem is None:
            ghost = {k: out[k] for k in ("word", "pos", "definition", "etym", "model", "theme")} | {"summoned": True}
            with self._lock:
                self.summoned.append(ghost)
            out.update({"accepted": True, "reason": self.checker.proof_text()})
        else:
            out.update({"accepted": False, "code": v.code or "definition", "reason": v.reason or problem,
                        "match": v.match or None})
            if v.entry:
                out["entry"] = {k: v.entry.get(k) for k in ("headline", "pron", "pos", "etym")} | {
                    "senses": (v.entry.get("senses") or [])[:2]}
        return out

    # ---- seance

    @staticmethod
    def seance() -> dict[str, Any] | None:
        return _load("seance-results.json", None)


_CHECK_LABELS = {
    "shape": "a single word of 5-14 letters",
    "1913": "not among Webster's 1913 headwords",
    "modern": "not in a modern English word list (wordfreq)",
    "near-1913": "not one letter away from a 1913 headword",
    "inflection": "not a 1913 headword with an ending added",
    "duplicate": "not already in the deck",
}
