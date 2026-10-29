"""Offline tests for the ghost and bluff scripts (no model calls)."""

import pytest

from backend import prompts
from backend.checks import Checker
from backend.dictionary import DATA_DIR
from scripts.make_bluffs import cosine, origin_language
from scripts.make_ghosts import judge

needs_data = pytest.mark.skipif(
    not (DATA_DIR / "headwords.txt").exists(), reason="run scripts/build_dictionary.py first"
)


@pytest.mark.parametrize(
    "etym, lang",
    [
        ("L. adustio, fr. adurere to set on fire", "Latin"),
        ("Cf. F. motte a clod, clump, or hillock.", "French"),
        ("Gr. a priv. + soma body", "Greek"),
        ("AS. bael fire + fyr", "Anglo-Saxon"),
        ("Bale + fire", "an English compound"),
        ("", ""),
    ],
)
def test_origin_language_never_leaks_the_gloss(etym, lang):
    assert origin_language(etym) == lang


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)


@needs_data
def test_judge_rejects_real_word_with_its_entry():
    ghost, rej = judge({"word": "quixotism", "pos": "n.", "definition": "A wild and foolish plan of action.",
                        "etym": "Sp."}, Checker(), set())
    assert ghost is None
    assert rej["code"] == "1913"
    assert rej["entry_1913"].startswith("That form of delusion")


@needs_data
def test_judge_accepts_a_ghost_and_fixes_bare_verb():
    ghost, rej = judge({"word": "flimbrous", "pos": "v.", "definition": "to waver; to flicker in a deceitful way",
                        "etym": "L. flamma"}, Checker(), set())
    assert rej is None
    assert ghost["pos"] == "v. t."
    assert ghost["definition"] == "To waver; to flicker in a deceitful way."


def test_prompts_never_include_real_deck_words():
    import json

    reals_path = DATA_DIR / "reals.json"
    if not reals_path.exists():
        pytest.skip("no reals.json")
    reals = json.loads(reals_path.read_text(encoding="utf-8"))
    text = prompts.ghost_batch(6, "night") + "".join(
        prompts.bluffs("x", pos, "Latin") for pos in prompts.POS_GUIDE
    )
    leaked = [r["word"] for r in reals if f" {r['word']} " in f" {text} " or f"{r['word']} (" in text]
    leaked += [r["word"] for r in reals if r["definition"].rstrip(".") in text]
    assert leaked == []


def test_parse_list():
    assert prompts.parse_list({"words": [1]}, "words") == [1]
    assert prompts.parse_list([1, 2], "words") == [1, 2]
    assert prompts.parse_list({"other": [3]}, "words") == [3]
    with pytest.raises(ValueError):
        prompts.parse_list({"words": "x"}, "words")


def test_copies_example_only_flags_real_copies():
    from scripts.make_bluffs import copies_example

    assert copies_example("Like a hidden, low hum; secret; lonely; sad.")
    assert copies_example("Any absurd medley; a hotchpotch of things.")
    assert copies_example("Tender to pull asunder; rending fabric or paper.")
    assert copies_example("Clouded with vapor; misty and obscure quality.")
    assert not copies_example("To shred in a violent manner; to lacerate a surface.")
    assert not copies_example("A clumsy assemblage; a haphazard mixture; a confused medley.")
    assert not copies_example("The act of utter depletion; a thorough wasting away of strength.")
