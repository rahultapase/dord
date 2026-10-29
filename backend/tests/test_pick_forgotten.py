"""Tests for the forgotten-word filters (scripts/pick_forgotten.py)."""

import json

import pytest

from scripts.pick_forgotten import (
    CURATED,
    REALS_OUT,
    card_definition,
    has_typo,
    reject_reason,
    stem_in_definition,
)


def entry(word, text, pos="n.", labels=(), etym=""):
    return {"word": word, "pos": pos, "labels": list(labels), "etym": etym, "line": 1,
            "senses": [{"text": text}]}


GOOD = entry("coranach", "A lamentation for the dead; a dirge.")


def test_good_entry_passes():
    assert reject_reason(GOOD, zipf=0.0) is None


@pytest.mark.parametrize(
    "e, reason",
    [
        (entry("dord", "Density."), "length"),
        (entry("aard-vark", "An edentate mammal of Southern Africa, it burrows."), "not letters only"),
        (entry("abanet", "See Abnet."), "cross-reference"),
        (entry("beauxes", "pl. of Beau, a fine gentleman."), "cross-reference"),
        (entry("abegge", "Same as Aby, to pay the penalty of."), "cross-reference"),
        (entry("gallin", "A substance obtained by the reduction of gallein.", labels=["Chem."]), "field label"),
        (entry("abelmosk", "An evergreen shrub of the East, whose seeds smell of musk."), "jargon"),
        (entry("quixotry", "Quixotism; visionary schemes of the most absurd kind."), "explains itself"),
        (entry("prefixy", "A beginning placed before words.", pos="prefix"), "part of speech"),
        (entry("shortish", "Brief."), "definition length"),
        (entry("brigue", "A cabal, intrigue, faction, contention, strife. Chesterfield."), "messy definition"),
        (entry("mixedly", "Having numbers (in pairs) of 2 or 3 at a time."), "messy definition"),
    ],
)
def test_rejections(e, reason):
    assert reject_reason(e, zipf=0.0) == reason


def test_still_in_modern_use():
    assert reject_reason(entry("lantern", "A case for carrying a light at night."), zipf=None) == "still in modern use"


@pytest.mark.parametrize(
    "text",
    [
        "One of a sect of savage heathens of the east.",
        "A scolding woman; a shrew of the village.",
        "A name formerly given to an idiot or a fool.",
    ],
)
def test_blocklist(text):
    assert reject_reason(entry("oldword", text), zipf=0.0) == "blocklist"


def test_obsolete_label_is_allowed_and_stripped_from_card():
    e = entry("dernful", "Secret; hence, lonely; sad; mournful. [Obs.]", pos="a.", labels=["Obs."])
    assert reject_reason(e, zipf=0.0) is None
    assert card_definition(e["senses"][0]["text"]) == "Secret; hence, lonely; sad; mournful."


def test_card_definition_strips_quotes_examples_and_authors():
    assert card_definition('Light as air; ethereal. "Aerial spirits." Milton.') == "Light as air; ethereal."
    assert card_definition("Rising aloft in air; high; lofty; as, aerial spires.") == "Rising aloft in air; high; lofty."
    assert card_definition("To dress; to attire. [Obs.] Beau. & Fl.") == "To dress; to attire."
    assert card_definition("The act of resulting; a result. Donne.") == "The act of resulting; a result."


def test_stem_in_definition():
    assert stem_in_definition("quixotry", "Quixotism; visionary schemes.")
    assert not stem_in_definition("coranach", "A lamentation for the dead; a dirge.")


def test_typo_detector():
    known = frozenset({"clan", "chieftain"})
    assert has_typo("Full of daring or of defiance; adveturous.", known)
    assert has_typo("A repository for holding things; a hinding place.", known)
    # Common misspellings are in wordfreq, so they slip through; curation catches those.
    assert not has_typo("A state of being united togheter as in a clan.", known)
    assert not has_typo("An association under a chieftain.", known)
    assert not has_typo("Associations under chieftains.", known)


def test_curated_list_is_unique():
    assert len(CURATED) == len(set(CURATED)) == 150


@pytest.mark.skipif(not REALS_OUT.exists(), reason="run pick_forgotten.py --curate first")
def test_reals_file_matches_curated_and_rules():
    reals = json.loads(REALS_OUT.read_text(encoding="utf-8"))
    assert sorted(r["word"] for r in reals) == sorted(CURATED)
    for r in reals:
        assert 5 <= len(r["word"]) <= 14 and r["word"].isalpha()
        assert 25 <= len(r["definition"]) <= 140
        assert "[" not in r["definition"] and '"' not in r["definition"]
