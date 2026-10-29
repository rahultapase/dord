"""Have Gemma invent fake 1913-style words, and let code decide which are really fake.

    uv run python scripts/make_ghosts.py            # resumes until data/ghosts.json has TARGET
    uv run python scripts/make_ghosts.py --target 20

Writes data/ghosts.json            accepted ghosts
       data/ghost-rejections.json  every word Gemma offered that failed a check, with the reason

Batches of 6 at temperature 0.9 with a fixed seed per batch, so a rerun repeats itself. Both files
are saved after every batch; the script picks up from the last batch on the next run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import ollama_client as oc  # noqa: E402
from backend import prompts  # noqa: E402
from backend.checks import Checker, definition_problem, pos_problem, tidy_definition  # noqa: E402

GHOSTS = ROOT / "data" / "ghosts.json"
REJECTIONS = ROOT / "data" / "ghost-rejections.json"
REALS = ROOT / "data" / "reals.json"
TARGET = 150
BATCH = 6
TEMPERATURE = 0.9
MAX_BATCHES = 160  # about 3 in 10 offered words survive the checks

# Read one by one after the first run (Thu 29 Oct). The code checks passed these, but each is a
# real word that neither list covers, plain Latin or Spanish, too close to a real word in the
# deck, or a near-copy of another ghost. They go to the rejection log with code "hand".
HAND_DROP = {
    "threnodic": "a real modern English word (threnody + -ic) that wordfreq does not list",
    "aetherial": "a real spelling of ethereal",
    "veridicality": "a real modern English word (philosophy)",
    "necrophage": "a real word in biology (a carrion eater); 1913 has necrophagous",
    "ignifuge": "a real word (a fireproofing agent)",
    "nectarium": "a real botanical Latin word for a nectary",
    "crepusculean": "too close to the real 1913 headword crepusculine",
    "umbration": "too close to obumbration, a real word in the deck",
    "augurium": "plain Latin (augury)",
    "occultum": "plain Latin",
    "fluvius": "plain Latin (river)",
    "mortuarium": "plain medieval Latin (a mortuary fee)",
    "tranquilum": "plain Latin (calm)",
    "marineria": "plain Spanish and Italian (seamanship)",
    "luminares": "plain Spanish (lights)",
    "smoggule": "built on smog, a word coined in 1905",
    "melancholyce": "near-copy of the ghost melancholyne",
    "somniflux": "near-copy of the ghost somnifluence",
    "somniflow": "near-copy of the ghost somnifluence",
    "oneiricize": "near-copy of the ghost oneiricate",
    "aetherwind": "near-copy of the ghost aethervane",
    "forgecraft": "near-copy of the ghost forgewright",
    "voyageant": "near-copy of the ghost voyagant",
    "itinerium": "near-copy of the ghost itinerantia",
    "gossipia": "near-copy of the ghost gossipule",
    "savorial": "near-copy of the ghost savorium",
    "veriditas": "near-copy of the ghost veridance",
    "cinderfall": "near-copy of the ghost cinderium",
    "cindergleam": "near-copy of the ghost cinderium",
    "lunarglow": "two modern words glued together",
    "hypnosisce": "a modern word (hypnosis) with an ending stuck on",
    "pavementor": "a modern word (pavement) with an ending stuck on",
    "pyroclast": "a real word in geology (a fragment of volcanic rock)",
    "selenian": "a real, if rare, word for lunar",
    "fluvium": "plain Latin (river)",
    "trenchmaker": "an everyday compound, not an invention",
}


def hand_review(ghosts: list[dict], log: dict) -> list[dict]:
    """Move HAND_DROP words and any ghost that now fails a rule into the rejection log."""
    keep = []
    for g in ghosts:
        why = HAND_DROP.get(g["word"])
        code = "hand"
        if why is None:
            why = pos_problem(g["pos"], g["definition"])
            code = "definition"
        if why:
            rej = {k: g[k] for k in ("word", "pos", "definition", "etym", "batch", "theme") if k in g}
            log["items"].append({**rej, "code": code, "reason": why})
        else:
            keep.append(g)
    for i, g in enumerate(keep, 1):
        g["id"] = f"g{i:03d}"
    return keep


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def judge(item: dict, checker: Checker, deck: set[str]) -> tuple[dict | None, dict | None]:
    """Return (ghost, None) or (None, rejection)."""
    word = str(item.get("word", "")).strip()
    definition = tidy_definition(item.get("definition", ""))
    pos = str(item.get("pos", "")).strip()
    etym = str(item.get("etym", "")).strip()
    v = checker.check(word, deck=deck)
    base = {"word": v.word or word, "pos": pos, "definition": definition, "etym": etym}
    if not v.ghost:
        rej = {**base, "code": v.code, "reason": v.reason}
        if v.match:
            rej["match"] = v.match
        if v.zipf:
            rej["zipf"] = round(v.zipf, 2)
        if v.entry:
            rej["entry_1913"] = v.entry["senses"][0]["text"] if v.entry.get("senses") else ""
        return None, rej
    if pos in ("v.", "v"):  # Gemma sometimes drops the t./i.
        pos = "v. t."
        base["pos"] = pos
    if v.word in HAND_DROP:
        return None, {**base, "code": "hand", "reason": HAND_DROP[v.word]}
    problem = definition_problem(v.word, definition) or pos_problem(pos, definition)
    if problem is None and pos not in prompts.POS_CHOICES:
        problem = f"part of speech {pos!r}"
    if problem:
        return None, {**base, "code": "definition", "reason": problem}
    return {**base, "checks": v.checks}, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=TARGET)
    args = ap.parse_args()

    checker = Checker()
    ghosts: list[dict] = load(GHOSTS, [])
    log: dict = load(REJECTIONS, {"offered": 0, "items": []})
    reals = {r["word"] for r in load(REALS, [])}
    before = len(ghosts)
    ghosts = hand_review(ghosts, log)
    if len(ghosts) != before:
        print(f"hand review moved {before - len(ghosts)} ghosts to the rejection log", flush=True)
        save(GHOSTS, ghosts)
        save(REJECTIONS, log)
    deck = {g["word"] for g in ghosts} | reals | {r["word"] for r in log["items"] if r.get("word")}
    done_batches = max([g["batch"] for g in ghosts] + [r["batch"] for r in log["items"]] + [-1])
    batch = done_batches + 1
    t_start = time.time()

    while len(ghosts) < args.target and batch < MAX_BATCHES:
        theme = prompts.GHOST_THEMES[batch % len(prompts.GHOST_THEMES)]
        t0 = time.time()
        try:
            reply = oc.generate_json(
                prompts.ghost_batch(BATCH, theme),
                temperature=TEMPERATURE,
                seed=1000 + batch,
                num_predict=900,
            )
            items = prompts.parse_list(reply, "words")
        except (ValueError, oc.OllamaError) as exc:
            print(f"batch {batch}: model reply unusable ({exc}); skipping", flush=True)
            log["items"].append({"batch": batch, "code": "reply", "reason": str(exc)[:200], "word": ""})
            save(REJECTIONS, log)
            batch += 1
            continue
        took = time.time() - t0
        kept = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            log["offered"] += 1
            ghost, rej = judge(item, checker, deck)
            if rej is None and ghost and any(ghost["word"][:6] == g["word"][:6] for g in ghosts):
                ghost, rej = None, {**ghost, "code": "hand", "reason": "same first six letters as a ghost already kept"}
                rej.pop("checks", None)
            if ghost:
                ghost.update({"id": f"g{len(ghosts) + 1:03d}", "batch": batch, "theme": theme, "model": oc.GEN_MODEL})
                ghosts.append(ghost)
                deck.add(ghost["word"])
                kept += 1
            else:
                rej.update({"batch": batch, "theme": theme})
                log["items"].append(rej)
        log["accepted"] = len(ghosts)
        log["by_code"] = dict(Counter(r["code"] for r in log["items"]))
        save(GHOSTS, ghosts)
        save(REJECTIONS, log)
        print(f"batch {batch:>2} [{theme}] {took:4.1f}s: kept {kept}/{len(items)}; total {len(ghosts)}", flush=True)
        batch += 1

    print(f"done: {len(ghosts)} ghosts, {log['offered']} offered, {time.time() - t_start:.0f}s this run")
    print("rejections by check:", log.get("by_code", {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
