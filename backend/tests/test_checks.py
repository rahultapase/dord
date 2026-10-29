"""Tests for backend/checks.py: what counts as a ghost."""

import pytest

from backend.checks import Checker, definition_problem, tidy_definition
from backend.dictionary import DATA_DIR

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "headwords.txt").exists(), reason="run scripts/build_dictionary.py first"
)


@pytest.fixture(scope="module")
def c():
    return Checker()


def test_quixotism_is_rejected_as_real(c):
    # Gemma offered "quixotism" as an invented word in the first test. It is a 1913 headword.
    v = c.check("quixotism")
    assert not v.ghost
    assert v.code == "1913"
    assert v.entry and v.entry["senses"][0]["text"].startswith("That form of delusion")


@pytest.mark.parametrize("word", ["flimbrous", "quanticle", "sorrowmere", "glistock", "floccinaut", "veridantize"])
def test_invented_words_pass(c, word):
    v = c.check(word)
    assert v.ghost, v.reason
    assert v.checks == ["shape", "1913", "modern", "near-1913", "inflection", "duplicate"]
    assert "no trace" in v.reason


def test_dord_is_a_ghost(c):
    # Not in 1913 (it was printed in 1934), but only four letters: the finale card, not a deck card.
    v = c.check("dord")
    assert v.code == "shape"


def test_modern_word_rejected(c):
    v = c.check("selfie")
    assert v.code == "modern"
    assert v.zipf > 0


@pytest.mark.xfail(reason="wordfreq does not list 'chronolect' (zipf 0.0); known gap, see checks.py", strict=True)
def test_chronolect_caught_by_wordfreq(c):
    assert c.check("chronolect").code == "modern"


def test_one_letter_from_headword(c):
    v = c.check("gallimaufra")
    assert v.code == "near-1913"
    assert v.match == "gallimaufry"


def test_inflection_of_headword(c):
    v = c.check("divulsiveness")
    assert v.code == "inflection"
    assert v.match == "divulsive"


def test_shape(c):
    assert c.check("ab").code == "shape"
    assert c.check("two words").code == "shape"
    assert c.check("hyphen-word").code == "shape"
    assert c.check("a" * 15).code == "shape"


def test_case_and_whitespace(c):
    assert c.check("  Quixotism ").code == "1913"


def test_duplicate(c):
    assert c.check("flimbrous", deck=["Flimbrous"]).code == "duplicate"


def test_proof_text_counts_headwords(c):
    assert f"{c.headword_count:,}" in c.proof_text()
    assert c.headword_count > 100_000


def test_definition_rules():
    assert definition_problem("flimbrous", "Wavering or flickering in appearance; deceitful.") is None
    assert "characters" in definition_problem("flimbrous", "Wavering.")
    assert "itself" in definition_problem("flimbrous", "The state of being flimbrous; flickering light.")
    assert "itself" in definition_problem("appetiteous", "Appealing to the appetite; delicious and tempting.")
    assert definition_problem("contendia", "A trifling quarrel or dispute; a small contest.") is None
    assert "quotes" in definition_problem("flimbrous", 'Wavering, as in "a flimbrous light" of old.')


def test_tidy_definition():
    assert tidy_definition("  wavering in   appearance ") == "Wavering in appearance."
    assert tidy_definition("Full of woe; Having a melancholic air;.") == "Full of woe; having a melancholic air."


def test_pos_rule():
    from backend.checks import pos_problem

    assert pos_problem("v. t.", "To die, or cause to die; to perish.") is None
    assert pos_problem("v. t.", "A mild sorrow; a fleeting regret.")
    assert pos_problem("n.", "To frown down; to overbear.")
    assert pos_problem("n.", "A lamentation for the dead; a dirge.") is None
