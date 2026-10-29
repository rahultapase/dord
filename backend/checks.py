"""Every real/fake rule in one place, shared by the data scripts and the API.

Code, not the model, decides what is real. A word Gemma invents is a ghost only if all of these
pass:

  1. shape       5-14 letters, a-z only
  2. 1913        not a headword (or spelling variant) in Webster's 1913
  3. modern      not in wordfreq's modern English list (zipf frequency exactly 0)
  4. near-1913   not one edit (letter added, dropped or changed) from a 1913 headword
  5. inflection  not a 1913 headword plus -s, -es, -ed, -ing, -er, -ly, -ness ...
  6. duplicate   not already in the deck

Known gap: a word can pass every check and still be a term in some specialist glossary that
neither list covers (in the first test Gemma offered "chronolect", which wordfreq does not know).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from rapidfuzz import process
from rapidfuzz.distance import Levenshtein
from wordfreq import zipf_frequency

from backend.dictionary import Dictionary, get_dictionary, normalize

MIN_LEN, MAX_LEN = 5, 14
DEF_MIN, DEF_MAX = 25, 140
WORD_RE = re.compile(r"^[a-z]+$")
SUFFIXES = ("s", "es", "ed", "d", "ing", "er", "ers", "ly", "ness", "ment", "ish", "ful", "less", "y")

CHECK_NAMES = {
    "shape": "5-14 letters",
    "1913": "Webster's 1913 headwords",
    "modern": "modern English word list (wordfreq)",
    "near-1913": "one letter from a 1913 headword",
    "inflection": "1913 headword + ending",
    "duplicate": "already in the deck",
}


@dataclass
class Verdict:
    word: str
    ghost: bool  # True = passed every check: no trace anywhere
    code: str = ""  # which check failed: shape / 1913 / modern / near-1913 / inflection / duplicate
    reason: str = ""  # one plain sentence for the log and the UI
    match: str = ""  # the real word it collided with, if any
    zipf: float = 0.0
    checks: list[str] = field(default_factory=list)  # checks that ran, in order
    entry: dict[str, Any] | None = None  # the 1913 entry when code == "1913"

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, "", [])}
        d["ghost"] = self.ghost
        return d


class Checker:
    def __init__(self, dictionary: Dictionary | None = None) -> None:
        self.d = dictionary or get_dictionary()
        self._by_len: dict[int, list[str]] = {}
        for w in self.d.single_words:
            self._by_len.setdefault(len(w), []).append(w)

    @property
    def headword_count(self) -> int:
        return len(self.d)

    def proof_text(self) -> str:
        return f"Searched {self.headword_count:,} headwords of Webster's 1913 and a modern word list: no trace."

    def near_headword(self, word: str) -> str | None:
        """A 1913 headword at Levenshtein distance 1 (rapidfuzz, only lengths n-1..n+1)."""
        pool: list[str] = []
        for n in (len(word) - 1, len(word), len(word) + 1):
            pool.extend(self._by_len.get(n, ()))
        hit = process.extractOne(word, pool, scorer=Levenshtein.distance, score_cutoff=1)
        return hit[0] if hit else None

    def inflected_headword(self, word: str) -> str | None:
        for suf in SUFFIXES:
            if word.endswith(suf) and len(word) - len(suf) >= 3:
                stem = word[: -len(suf)]
                for cand in (stem, stem + "e", stem[:-1] if len(stem) > 3 and stem[-1] == stem[-2] else None,
                             stem[:-1] + "y" if stem.endswith("i") else None):
                    if cand and cand in self.d.single_words:
                        return cand
        return None

    def check(self, raw_word: str, deck: Iterable[str] = ()) -> Verdict:
        word = normalize(raw_word)
        v = Verdict(word=word, ghost=False)

        v.checks.append("shape")
        if not WORD_RE.match(word) or not MIN_LEN <= len(word) <= MAX_LEN:
            v.code, v.reason = "shape", f"'{raw_word}' is not a single word of {MIN_LEN}-{MAX_LEN} letters."
            return v

        v.checks.append("1913")
        if word in self.d:
            v.code, v.match = "1913", word
            v.reason = f"'{word}' is a real headword in Webster's 1913."
            entries = self.d.lookup(word)
            v.entry = entries[0] if entries else None
            return v

        v.checks.append("modern")
        v.zipf = zipf_frequency(word, "en")
        if v.zipf > 0:
            v.code, v.reason = "modern", f"'{word}' is in the modern English word list (zipf {v.zipf:.2f})."
            return v

        v.checks.append("near-1913")
        near = self.near_headword(word)
        if near:
            v.code, v.match = "near-1913", near
            v.reason = f"'{word}' is one letter away from the 1913 headword '{near}'."
            return v

        v.checks.append("inflection")
        stem = self.inflected_headword(word)
        if stem:
            v.code, v.match = "inflection", stem
            v.reason = f"'{word}' is the 1913 headword '{stem}' with an ending added."
            return v

        v.checks.append("duplicate")
        if word in {normalize(w) for w in deck}:
            v.code, v.reason = "duplicate", f"'{word}' is already in the deck."
            return v

        v.ghost = True
        v.reason = self.proof_text()
        return v


def definition_problem(word: str, definition: str) -> str | None:
    """Card rules for a definition Gemma wrote (ghosts and bluffs). None if it is usable."""
    d = definition.strip()
    if not DEF_MIN <= len(d) <= DEF_MAX:
        return f"definition is {len(d)} characters (needs {DEF_MIN}-{DEF_MAX})"
    if re.search(r"[\"\[\]0-9]", d):
        return "definition has quotes, brackets or digits"
    # The word itself, or nearly all of it ("appetiteous" -> "appetite"), but not a shared
    # prefix ("contendia" may say "contest").
    w = normalize(word)
    stem = w[: max(5, len(w) - 3)]
    if any(tok.lower().startswith(stem) for tok in re.findall(r"[A-Za-z]+", d)):
        return "definition uses the word itself"
    return None


def pos_problem(pos: str, definition: str) -> str | None:
    """1913 verb senses start with "To ..."; other parts of speech never do. A mismatch is a tell."""
    is_verb = pos.strip().startswith("v.")
    starts_to = definition.strip().startswith("To ")
    if is_verb and not starts_to:
        return "verb definition does not start with 'To'"
    if not is_verb and starts_to:
        return f"'{pos}' definition starts with 'To'"
    if pos.strip() == "a." and re.match(r"(?:A|An|The)\s", definition.strip()):
        return "adjective defined like a noun"
    return None


def tidy_definition(text: str) -> str:
    """Trim whitespace, one trailing full stop, capital first letter."""
    s = re.sub(r"\s+", " ", str(text)).strip().strip("\"'").rstrip(";,: .").strip()
    if not s:
        return s
    s = s[0].upper() + s[1:]
    # 1913 style: "Secret; hence, lonely; sad." Gemma writes "...woe; Having a ..." (a tell).
    s = re.sub(r"([;,]\s+)([A-Z])(?=[a-z])", lambda m: m.group(1) + m.group(2).lower(), s)
    s = re.sub(r";\s*;", ";", s)
    if s[-1] not in ".!?":
        s += "."
    return s
