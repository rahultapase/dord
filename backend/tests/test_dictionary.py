"""Checks on the built data files (data/webster1913.jsonl, data/headwords.txt)."""

import pytest

from backend.dictionary import DATA_DIR, Dictionary, normalize

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "headwords.txt").exists(), reason="run scripts/build_dictionary.py first"
)


@pytest.fixture(scope="module")
def d():
    return Dictionary()


def test_counts(d):
    assert 95_000 < len(d) < 110_000
    assert 90_000 < len(d.single_words) < 100_000


@pytest.mark.parametrize(
    "word", ["gallimaufry", "quixotism", "divulsive", "resultance", "motte", "perspicuity", "abattis"]
)
def test_known_headwords(d, word):
    assert word in d
    assert d.lookup(word)


def test_dord_absent(d):
    assert "dord" not in d
    assert d.lookup("dord") == []


def test_invented_words_absent(d):
    for fake in ["flimbrous", "quanticle", "sorrowmere", "glistock", "floccinaut", "chronolect"]:
        assert fake not in d


def test_lookup_returns_every_entry(d):
    pos = [e["pos"] for e in d.lookup("mottle")]
    assert pos == ["v. t.", "n."]


def test_case_and_accents(d):
    assert "Gallimaufry" in d
    assert normalize("A\u00ebrial") == "aerial"
    assert "a\u00ebrial" in d
