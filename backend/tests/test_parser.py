"""Parser tests on 31 hand-picked 1913 entries (fixtures/webster_sample.txt, copied verbatim)."""

from pathlib import Path

import pytest

from scripts.build_dictionary import parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "webster_sample.txt"


@pytest.fixture(scope="module")
def entries():
    return parse_text(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def by_word(entries):
    out = {}
    for e in entries:
        out.setdefault(e.word, []).append(e)
    return out


def one(by_word, word):
    found = by_word[word]
    assert len(found) == 1, f"{word}: {len(found)} entries"
    return found[0]


def test_every_entry_found(entries):
    assert len(entries) == 31
    assert all(e.senses for e in entries), [e.word for e in entries if not e.senses]


def test_gallimaufry_numbered_senses_with_quotes(by_word):
    e = one(by_word, "gallimaufry")
    assert e.pron == 'Gal`li*mau"fry'
    assert e.pos == "n."
    assert e.etym == "F. galimafrée a sort of ragout or mixed hash of different meats."
    assert [s.number for s in e.senses] == ["1", "2"]
    assert e.senses[0].text == "A hash of various kinds of meats, a ragout."
    assert e.senses[0].quote == "Delighting in hodge-podge, gallimaufries, forced meat."
    assert e.senses[0].author == "King"
    assert e.senses[1].text == "Any absurd medley; a hotchpotch."
    assert e.senses[1].author == "South"


def test_quixotism_single_defn_over_four_lines(by_word):
    e = one(by_word, "quixotism")
    assert len(e.senses) == 1
    s = e.senses[0]
    assert s.number == ""
    assert s.text.startswith("That form of delusion which leads to extravagant")
    assert s.text.endswith("the exploits of Don Quixote in knight-errantry.")
    assert s.quote == ""


def test_quixotry(by_word):
    assert one(by_word, "quixotry").first_def == "Quixotism; visionary schemes."


def test_divulsive(by_word):
    e = one(by_word, "divulsive")
    assert e.pos == "a."
    assert e.first_def == "Tending to pull asunder, tear, or rend; distracting."


def test_motte_usage_label(by_word):
    e = one(by_word, "motte")
    assert e.first_def == "A clump of trees in a prairie. [Local, U.S.]"
    assert "Local, U.S." in e.labels
    assert e.etym == "Cf. F. motte a clod, clump, or hillock."


def test_mottle_two_entries(by_word):
    verb, noun = by_word["mottle"]
    assert verb.pos == "v. t."
    assert noun.pos == "n."
    assert noun.first_def == "A mottled appearance."


def test_resultance_trailing_author_kept_in_text(by_word):
    # A one-line sense ending with an author name is left whole; the game filters these.
    assert one(by_word, "resultance").first_def.startswith("The act of resulting;")


def test_perspicuity_author_only_line_and_syn_note(by_word):
    e = one(by_word, "perspicuity")
    assert len(e.senses) == 3
    assert e.senses[0].text == "The quality or state of being transparent or translucent. [Obs.]"
    assert e.senses[0].author == "Sir T. Browne"
    assert e.senses[2].text == "Sagacity; perspicacity."
    assert "Obs." in e.labels
    assert any(n.startswith("Syn. -- Clearness") for n in e.notes)


def test_dizen_inflections_and_two_quotes(by_word):
    e = one(by_word, "dizen")
    assert e.pos == "v. t."
    assert e.etym.startswith("Perh. orig., to dress in a foolish manner")
    assert e.senses[1].text == "To dress gaudily; to overdress; to bedizen; to deck out."
    assert e.senses[1].author == "Emerson"


def test_dixie_label_at_end(by_word):
    e = one(by_word, "dixie")
    assert e.first_def.endswith("esp. during the Civil War. [U.S.]")


def test_field_label_in_header(by_word):
    assert "Chem." in one(by_word, "gallin").labels
    assert "Zoöl." in one(by_word, "aard-vark").labels
    assert "Fort." in one(by_word, "abatis").labels
    assert "Eccl. Hist." in one(by_word, "abelian").labels
    assert "Physiol. Chem." in one(by_word, "zymolysis").labels


def test_variants_split_on_semicolons(by_word):
    assert one(by_word, "abatis").variants == ["abatis", "abattis"]
    assert one(by_word, "aeolipile").variants == ["aeolipile", "aeolipyle"]
    assert one(by_word, "abelian").variants == ["abelian", "abelite", "abelonian"]


def test_ae_ligature_header_matches_headword(by_word):
    e = one(by_word, "aegis")
    assert e.pron == 'Æ"gis'
    assert e.first_def.startswith("A shield or protective armor")
    assert one(by_word, "aecidium").labels == ["Bot."]


def test_note_paragraph(by_word):
    e = one(by_word, "aeolipile")
    assert e.first_def.endswith("[Written also eolipile.]")
    assert any(n.startswith("Note: Such an apparatus was first described by Hero") for n in e.notes)


def test_subsenses_directly_after_header(by_word):
    e = one(by_word, "acajou")
    assert [s.number for s in e.senses] == ["a", "b"]
    assert e.senses[1].text == "The mahogany tree; also, its timber."
    assert "Bot." in e.labels


def test_letters_inside_etymology_are_not_senses(by_word):
    e = one(by_word, "acerose")
    assert e.etym.startswith("(a) L. acerosus chaffy")
    assert [s.number for s in e.senses] == ["a", "b"]
    assert e.senses[0].text == "Having the nature of chaff; chaffy."


def test_label_only_sense_merged_with_defn(by_word):
    e = one(by_word, "aaron's rod")
    assert [s.number for s in e.senses] == ["1", "2"]
    assert e.senses[0].text.startswith("(Arch.) A rod with one serpent")
    assert e.senses[1].text.startswith("(Bot.) A plant with a tall flowering stem")


def test_label_sense_with_quote(by_word):
    e = one(by_word, "aberrant")
    last = e.senses[-1]
    assert last.text == "(Biol.) Deviating from the ordinary or natural type; exceptional; abnormal."
    assert last.author == "Darwin"


def test_sense_on_pronunciation_line(by_word):
    e = one(by_word, "aerial railway")
    assert e.pron == 'A*ë`ri*al rail"way`'
    assert e.first_def.startswith("A stretched wire or rope elevated above the ground")


def test_aerial_inline_quotes_stay_in_text(by_word):
    e = one(by_word, "aerial")
    assert len(e.senses) == 5
    assert e.senses[1].text == (
        "Consisting of air; resembling, or partaking of the nature of air. Hence: Unsubstantial; unreal."
    )


def test_cross_references_and_inflections(by_word):
    assert one(by_word, "abanet").first_def == "See Abnet."
    assert one(by_word, "abegge").first_def == "Same as Aby. [Obs.] Chaucer."
    assert one(by_word, "beaux").first_def == "pl. of Beau."
    assert one(by_word, "begot").first_def == "imp. & p. p. of Beget."


def test_rare_label(by_word):
    e = one(by_word, "abacinate")
    assert "R." in e.labels
    assert e.etym.startswith("LL. abacinatus")


def test_zymology(by_word):
    e = one(by_word, "zymology")
    assert e.first_def.endswith("[Written also zumology.]")


def test_dord_is_not_a_headword(by_word):
    assert "dord" not in by_word
