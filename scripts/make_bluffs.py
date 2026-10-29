"""Have Gemma write bluff definitions for the real words (the Three Definitions mode).

    uv run python scripts/make_bluffs.py --calibrate 20   # print similarities, save nothing
    uv run python scripts/make_bluffs.py                  # resumes until every real word has 2

Gemma sees only the word, its part of speech and the language it came from, never the 1913
definition. Each bluff is embedded with qwen3-embedding:0.6b; a bluff whose cosine similarity
with the true definition is above THRESHOLD is too close to the truth and is dropped.

Writes data/bluffs.json  {real id: {"word", "bluffs": [2 kept], "dropped": [...]}}
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import ollama_client as oc  # noqa: E402
from backend import prompts  # noqa: E402
from backend.checks import definition_problem, pos_problem, tidy_definition  # noqa: E402

REALS = ROOT / "data" / "reals.json"
OUT = ROOT / "data" / "bluffs.json"
# Calibrated by hand on 20 words / 60 bluffs (Thu 29 Oct): median 0.60, p90 0.72, max 0.91.
# Every bluff above 0.70 restated the truth (incension 0.91 "the act of setting alight",
# obumbration 0.78, delirament 0.76, ticktack 0.74 "a small rhythmic striking sound"); the plan's
# starting value of 0.80 let most of those through.
THRESHOLD = 0.70
PAIR_MAX = 0.88  # two kept bluffs this similar to each other are the same bluff
KEEP = 2
TRIES = 3
TEMPERATURE = 0.9

LANGS = {
    "L.": "Latin", "LL.": "Late Latin", "NL.": "New Latin", "ML.": "Medieval Latin",
    "Gr.": "Greek", "F.": "French", "OF.": "Old French", "LG.": "Low German", "G.": "German",
    "AS.": "Anglo-Saxon", "OE.": "Old English", "It.": "Italian", "Sp.": "Spanish",
    "Pg.": "Portuguese", "D.": "Dutch", "Icel.": "Icelandic", "Scot.": "Scottish",
    "W.": "Welsh", "Ir.": "Irish", "Gael.": "Gaelic", "Ar.": "Arabic", "Heb.": "Hebrew",
    "Per.": "Persian", "Pers.": "Persian", "Hind.": "Hindi", "Skr.": "Sanskrit", "Russ.": "Russian",
    "Sw.": "Swedish", "Dan.": "Danish", "Prov.": "Provencal", "Turk.": "Turkish",
}


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z']+", s.lower())


def copies_example(text: str) -> bool:
    """A bluff that reuses a phrase from the prompt's examples repeats across cards: a tell.

    Caught: any three words in a row from an example, the same first two words as a 1913 style
    example ("Clouded with vapor" after "Clouded with, or as with, mist"), or a quoted example.
    """
    tw = _words(text)
    grams = {tuple(tw[i:i + 3]) for i in range(len(tw) - 2)}
    for _, _, d in prompts.STYLE_EXAMPLES:
        ew = _words(d)
        if tw[:2] == ew[:2] or grams & {tuple(ew[i:i + 3]) for i in range(len(ew) - 2)}:
            return True
    t = text.lower()
    phrases = [d for _, _, d in prompts.STYLE_EXAMPLES] + [s for _, s in prompts.POS_GUIDE.values()]
    old = ["Secret; lonely; sad."]  # the first adjective example, kept so old bluffs are caught
    for p in phrases + old:
        # Only quoted examples count, not one-word quotes such as "To" or "A".
        for chunk in [c for c in re.findall(r'"([^"]+)"', p) if len(c) > 8] or [p]:
            if chunk.lower().strip(" .") in t:
                return True
            for part in chunk.lower().split(";"):
                part = part.strip(" .")
                if len(part) > 8 and part in t:
                    return True
    return False


def origin_language(etym: str) -> str:
    """'L. adustio, fr. adurere to set on fire' -> 'Latin'. The gloss itself is never shown."""
    for tok in re.findall(r"[A-Z][A-Za-z]*\.", etym):
        if tok in LANGS:
            return LANGS[tok]
    if "+" in etym or etym.startswith(("Pref.", "Prefix")):
        return "an English compound"
    return ""


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def generate(real: dict, attempt: int) -> list[str]:
    reply = oc.generate_json(
        prompts.bluffs(real["word"], real["pos"], origin_language(real.get("etym", ""))),
        temperature=TEMPERATURE,
        seed=5000 + int(real["id"][1:]) * 10 + attempt,
        num_predict=500,
    )
    return [tidy_definition(x) for x in prompts.parse_list(reply, "definitions") if isinstance(x, str)]


def score(real: dict, texts: list[str]) -> list[float]:
    return [round(s, 3) for s in score_vectors(real, texts)[0]]


def score_vectors(real: dict, texts: list[str]) -> tuple[list[float], list[list[float]]]:
    vecs = oc.embed([real["definition"], *texts])
    return [cosine(vecs[0], v) for v in vecs[1:]], vecs[1:]


def calibrate(reals: list[dict], n: int) -> int:
    rows = []
    for real in reals[:: max(1, len(reals) // n)][:n]:
        texts = generate(real, 0)
        sims = score(real, texts) if texts else []
        print(f"\n{real['word']} ({real['pos']}, {origin_language(real.get('etym', '')) or '?'})")
        print(f"   TRUE  {real['definition']}")
        for t, s in zip(texts, sims):
            print(f"   {s:.3f} {t}")
            rows.append(s)
    rows.sort()
    if rows:
        q = lambda p: rows[min(len(rows) - 1, int(p * len(rows)))]  # noqa: E731
        print(f"\n{len(rows)} bluffs: min {rows[0]:.3f}  median {q(0.5):.3f}  p90 {q(0.9):.3f}  max {rows[-1]:.3f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", type=int, default=0)
    ap.add_argument("--tries", type=int, default=TRIES, help="model calls per word (max 10)")
    args = ap.parse_args()
    tries = max(1, min(10, args.tries))
    reals = json.loads(REALS.read_text(encoding="utf-8"))
    if args.calibrate:
        return calibrate(reals, args.calibrate)

    out: dict = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    # Bluffs saved under an older rule are re-checked; a word left with fewer than KEEP is redone.
    for rid, rec in out.items():
        bad = [b for b in rec["bluffs"] if copies_example(b["text"])]
        if bad:
            rec["bluffs"] = [b for b in rec["bluffs"] if b not in bad]
            rec["dropped"] += [{**b, "reason": "copies a phrase from the prompt example"} for b in bad]
    t_start = time.time()
    for real in reals:
        rec = out.get(real["id"])
        if rec and len(rec["bluffs"]) >= KEEP:
            continue
        rec = {"word": real["word"], "bluffs": [], "dropped": []}
        kept_vecs: list[list[float]] = []
        for attempt in range(tries):
            try:
                texts = generate(real, attempt)
                sims, vecs = score_vectors(real, texts) if texts else ([], [])
            except (ValueError, oc.OllamaError) as exc:
                rec["dropped"].append({"text": "", "reason": f"reply unusable: {str(exc)[:120]}"})
                continue
            for text, sim, vec in zip(texts, sims, vecs):
                sim = round(sim, 3)
                problem = definition_problem(real["word"], text) or pos_problem(real["pos"], text)
                if problem is None and copies_example(text):
                    problem = "copies a phrase from the prompt example"
                if problem is None and sim > THRESHOLD:
                    problem = f"too close to the true definition (similarity {sim:.2f})"
                if problem is None and any(cosine(vec, k) > PAIR_MAX for k in kept_vecs):
                    problem = "same as a bluff already kept"
                if problem:
                    rec["dropped"].append({"text": text, "similarity": sim, "reason": problem})
                elif len(rec["bluffs"]) < KEEP:
                    rec["bluffs"].append({"text": text, "similarity": sim})
                    kept_vecs.append(vec)
            if len(rec["bluffs"]) >= KEEP:
                break
        out[real["id"]] = rec
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        tmp.replace(OUT)
        print(f"{real['id']} {real['word']:<16} kept {len(rec['bluffs'])}, dropped {len(rec['dropped'])}", flush=True)

    short = [r["word"] for r in out.values() if len(r["bluffs"]) < KEEP]
    print(f"done in {time.time() - t_start:.0f}s; {len(out)} words; short of {KEEP} bluffs: {short}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
