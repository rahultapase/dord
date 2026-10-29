"""The seance: how often do the models believe in the ghosts? (The post's numbers.)

    uv run python scripts/run_seance.py          # resumes from data/seance-results.json
    uv run python scripts/run_seance.py --table  # print the markdown table, ask nothing

Both models play the same fixed cards with the game's own prompts (backend/prompts.py),
temperature 0, seed 7, thinking off, JSON answers:
  - Real or Ghost: 100 cards, 50 real words and 50 ghosts.
  - Three Definitions: 50 real words, the true 1913 definition and two of Gemma's bluffs.
  - Define this word: 30 ghosts. Does the model invent a meaning or say it is not a word?

Run it with nothing else using Ollama (stop uvicorn first): two processes at once hung Ollama.

Writes data/seance-results.json. The game reads gemma4:e2b's answers from it as a fallback when
the live guess is slow.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import ollama_client as oc  # noqa: E402
from backend import prompts  # noqa: E402
from backend.checks import card_text  # noqa: E402
from backend.game import ask_gemma  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "seance-results.json"
MODELS = (oc.GEN_MODEL, oc.SMALL_MODEL)
SEED = 1934  # picks the cards and shuffles the definitions; the same every run
N_REAL, N_GHOST, N_THREE, N_DEFINE = 50, 50, 50, 30

# A "real_word: true" reply that still says the word does not exist counts as a refusal.
REFUSAL = re.compile(
    r"not (?:a |an )?(?:real|recogni[sz]ed|known|valid|standard|actual|english)?\s*(?:english )?word"
    r"|no such word|does not exist|doesn't exist|is not in (?:the|any) dictionar|not found in"
    r"|made[- ]up|invented|fictional|neologism|nonce",
    re.I,
)


# The agent read all 60 "define this word" replies (Thu 29 Oct). The keyword check got 58 right;
# these two are set by hand.
HAND = {
    ("gemma3:1b", "brambletide"): ("hedged", "calls it 'a whimsical and somewhat nonsensical word' before defining it"),
    ("gemma3:1b", "maulcraft"): ("made-up", "says real_word false, then defines it as 'a rare and archaic term'"),
}


def apply_hand(rows: list[dict]) -> None:
    for r in rows:
        hand = HAND.get((r["model"], r["word"])) if r["mode"] == "define" else None
        if hand:
            r["answer"], r["handNote"] = hand


def load(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def cards() -> dict[str, list[dict]]:
    """The fixed questions. Built the same way the game deals them."""
    rng = random.Random(SEED)
    reals, ghosts = load("reals.json"), load("ghosts.json")
    bluffs = {k: [b["text"] for b in v["bluffs"]] for k, v in load("bluffs.json").items() if len(v["bluffs"]) >= 2}

    rog = [{"word": r["word"], "kind": "real", "definition": r["definition"]} for r in rng.sample(reals, N_REAL)]
    rog += [{"word": g["word"], "kind": "ghost", "definition": card_text(g["definition"])} for g in rng.sample(ghosts, N_GHOST)]
    rng.shuffle(rog)

    three = []
    for r in rng.sample([r for r in reals if r["id"] in bluffs], N_THREE):
        options = [r["definition"], *(card_text(b) for b in bluffs[r["id"]][:2])]
        order = [0, 1, 2]
        rng.shuffle(order)
        three.append({"word": r["word"], "kind": "real", "options": [options[j] for j in order],
                      "correct": order.index(0) + 1})

    define = [{"word": g["word"], "kind": "ghost", "pos": g["pos"]} for g in rng.sample(ghosts, N_DEFINE)]
    return {"real-or-ghost": rog, "three-defs": three, "define": define}


def ask(model: str, mode: str, c: dict) -> dict:
    """One answer, timed. Errors and unusable replies are recorded as no answer."""
    t0 = time.time()
    row: dict[str, Any] = {"model": model, "mode": mode, "word": c["word"], "kind": c["kind"]}
    try:
        if mode == "define":
            reply = oc.generate_json(prompts.define_word(c["word"]), model=model, temperature=0, seed=7,
                                     num_predict=120, timeout=90)
            reply = reply if isinstance(reply, dict) else {}
            text = str(reply.get("definition", "")).strip()
            said_real = reply.get("real_word")
            row["definition"] = text
            row["realWord"] = said_real
            if said_real is True and text and not REFUSAL.search(text):
                row["answer"] = "made-up"
            elif said_real is False or REFUSAL.search(text):
                row["answer"] = "not-a-word"
            else:
                row["answer"] = None
        else:
            row["answer"] = ask_gemma(mode, c["word"], c.get("definition", ""), c.get("options"), model=model)
    except Exception as exc:  # Ollama error or bad JSON: no answer
        row["answer"] = None
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
    row["seconds"] = round(time.time() - t0, 2)

    if mode == "real-or-ghost":
        row["truth"] = c["kind"]
    elif mode == "three-defs":
        row["truth"] = c["correct"]
        row["options"] = c["options"]
        # The game shuffles definitions differently every time, so its fallback needs the text.
        row["answerText"] = c["options"][row["answer"] - 1] if isinstance(row["answer"], int) else None
    if mode != "define":
        row["correct"] = row["answer"] == row["truth"]
    return row


def summarise(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for model in MODELS:
        mine = [r for r in rows if r["model"] == model]
        rog = [r for r in mine if r["mode"] == "real-or-ghost"]
        three = [r for r in mine if r["mode"] == "three-defs"]
        define = [r for r in mine if r["mode"] == "define"]
        secs = [r["seconds"] for r in mine if r["answer"] is not None]
        out[model] = {
            "realOrGhost": {
                "cards": len(rog),
                "correct": sum(r["correct"] for r in rog),
                "ghostsCalledReal": sum(r["kind"] == "ghost" and r["answer"] == "real" for r in rog),
                "ghosts": sum(r["kind"] == "ghost" for r in rog),
                "realsCalledGhost": sum(r["kind"] == "real" and r["answer"] == "ghost" for r in rog),
                "reals": sum(r["kind"] == "real" for r in rog),
                "noAnswer": sum(r["answer"] is None for r in rog),
            },
            "threeDefs": {
                "cards": len(three),
                "correct": sum(r["correct"] for r in three),
                "pickedBluff": sum(r["answer"] is not None and not r["correct"] for r in three),
                "noAnswer": sum(r["answer"] is None for r in three),
            },
            "define": {
                "ghosts": len(define),
                "madeUp": sum(r["answer"] == "made-up" for r in define),
                "notAWord": sum(r["answer"] == "not-a-word" for r in define),
                "hedged": sum(r["answer"] == "hedged" for r in define),
                "noAnswer": sum(r["answer"] is None for r in define),
            },
            "secondsPerAnswer": round(statistics.median(secs), 2) if secs else None,
        }
    return out


def table(summary: dict[str, dict]) -> str:
    def pct(a: int, b: int) -> str:
        return f"{a}/{b} ({round(100 * a / b)}%)" if b else "-"

    lines = [
        "| | " + " | ".join(f"`{m}`" for m in summary) + " |",
        "|---|" + "---|" * len(summary),
    ]
    rows = [
        ("Real or Ghost: right", lambda s: pct(s["realOrGhost"]["correct"], s["realOrGhost"]["cards"])),
        ("Ghosts it called real", lambda s: pct(s["realOrGhost"]["ghostsCalledReal"], s["realOrGhost"]["ghosts"])),
        ("Real words it called ghosts", lambda s: pct(s["realOrGhost"]["realsCalledGhost"], s["realOrGhost"]["reals"])),
        ("Three Definitions: right", lambda s: pct(s["threeDefs"]["correct"], s["threeDefs"]["cards"])),
        ("Ghosts it defined with confidence", lambda s: pct(s["define"]["madeUp"], s["define"]["ghosts"])),
        ("Seconds per answer (median)", lambda s: str(s["secondsPerAnswer"])),
    ]
    for label, f in rows:
        lines.append(f"| {label} | " + " | ".join(f(s) for s in summary.values()) + " |")
    return "\n".join(lines)


def save(rows: list[dict], complete: bool) -> dict:
    apply_hand(rows)
    data = {
        "held": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": complete,
        "settings": {"temperature": 0, "seed": 7, "think": False, "cardSeed": SEED, "models": list(MODELS),
                     "prompts": "backend/prompts.py (real_or_ghost, three_definitions, define_word)"},
        "summary": summarise(rows),
        "answers": rows,
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(OUT)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true", help="print the table from the saved results")
    args = ap.parse_args()

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows: list[dict] = old.get("answers", [])
    if args.table:
        apply_hand(rows)
        print(table(summarise(rows)))
        return 0

    done = {(r["model"], r["mode"], r["word"]) for r in rows if "error" not in r}
    rows = [r for r in rows if (r["model"], r["mode"], r["word"]) in done]  # retry the errors
    t_start = time.time()
    for model in MODELS:
        for mode, cs in cards().items():
            todo = [c for c in cs if (model, mode, c["word"]) not in done]
            for i, c in enumerate(todo, 1):
                row = ask(model, mode, c)
                rows.append(row)
                if i % 10 == 0 or i == len(todo):
                    save(rows, complete=False)
                    print(f"{model:<12} {mode:<14} {i}/{len(todo)}  {time.time() - t_start:.0f}s", flush=True)
    data = save(rows, complete=True)
    errors = sum("error" in r for r in rows)
    print(f"done in {time.time() - t_start:.0f}s; {len(rows)} answers; {errors} errors\n")
    print(table(data["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
