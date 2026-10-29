"""Every prompt sent to the models. Kept in Python so the shell never has to quote them."""

from __future__ import annotations

import json

# Real 1913 entries shown to Gemma as a style guide. None of them is in data/reals.json.
STYLE_EXAMPLES = [
    ("gallimaufry", "n.", "Any absurd medley; a hotchpotch."),
    ("divulsive", "a.", "Tending to pull asunder, tear, or rend; distracting."),
    ("motte", "n.", "A clump of trees in a prairie."),
    ("mistful", "a.", "Clouded with, or as with, mist."),
    ("comprint", "n.", "The surreptitious printing of another's copy or book; a work thus printed."),
]

GHOST_THEMES = [
    "death, graves and burial",
    "night, the moon and darkness",
    "everyday household things",
    "weather, wind and water",
    "food, drink and cookery",
    "quarrels, fighting and weapons",
    "moods and feelings",
    "magic, charms and fortune-telling",
    "trades, tools and workshops",
    "fire, smoke and ashes",
    "talk, lies and gossip",
    "travel, roads and wandering",
    "sleep, dreams and waking",
    "plants, woods and fields",
    "fear, dread and haunting",
]

POS_CHOICES = ["n.", "a.", "v. t.", "v. i.", "adv."]

# How a 1913 definition of each part of speech begins, so bluffs match the real one's shape.
_VERB = 'Every definition must begin with "To", like "To set on fire; to kindle."'
POS_GUIDE = {
    "n.": ("a noun", 'Every definition must describe a thing, person or act, like "A stupid fellow; a blockhead."'),
    "a.": ("an adjective", 'Every definition must describe a quality, like "Inclined to eat; hungry; voracious.", '
           'and must NOT begin with "A", "An" or "The". Begin each of your definitions differently.'),
    "v. t.": ("a verb", _VERB),
    "v. i.": ("a verb", _VERB),
    "v. t. & i.": ("a verb", _VERB),
    "adv.": ("an adverb", 'Every definition must describe a manner, like "In a heap; huddled together."'),
}


def _examples() -> str:
    return "\n".join(f"{w} ({p}): {d}" for w, p, d in STYLE_EXAMPLES)


def ghost_batch(n: int, theme: str) -> str:
    """Ask for n invented words in 1913 style. JSON reply: {"words": [...]}"""
    return f"""You are helping build a dictionary game set in the year 1913.

Invent {n} English words that do NOT exist and never existed, but that look and sound as if they
came from Webster's Revised Unabridged Dictionary of 1913. Each must be believable enough to fool
a reader who knows old books. Mix the styles: most built from Latin or Greek roots with old
prefixes and suffixes, some old English compounds. Never glue two everyday modern words together
(no "chiselmark", "brawlmark"), and never give a word that really exists, however rare.

Theme for this batch: {theme}.

For each word give:
- "word": 5 to 14 lowercase letters, no hyphens or spaces
- "pos": one of {", ".join(POS_CHOICES)}
- "definition": one dictionary definition in the 1913 style, 30 to 120 characters, short
  phrases separated by semicolons, never using the word itself, no quotation marks, no examples
- "etym": a short invented origin in the 1913 style, for example "L. umbra shade + -ose"

This is how real 1913 entries read. These words are real; do not reuse them:
{_examples()}

Reply with JSON only, in exactly this shape:
{{"words": [{{"word": "...", "pos": "...", "definition": "...", "etym": "..."}}]}}"""


def summon_one(theme: str) -> str:
    """One fresh ghost for the live "Summon" button."""
    return ghost_batch(1, theme)


def bluffs(word: str, pos: str, origin: str, n: int = 3) -> str:
    """Bluff definitions for a real word whose true meaning Gemma is not shown."""
    origin_line = f"It comes from {origin}." if origin else "Its origin is unknown."
    name, shape = POS_GUIDE.get(pos.strip(), POS_GUIDE["n."])
    return f"""You are playing the dictionary bluffing game. A real but forgotten English word from
Webster's 1913 dictionary is read out, and each player writes a fake definition that sounds so
convincing the others will believe it is the real one.

The word: {word}
It is {name}. {shape}
{origin_line}

Write {n} different fake definitions for it, each with a different meaning. Each must be in the
1913 dictionary style: 30 to 120 characters, short phrases separated by semicolons, never using
the word itself, no quotation marks, no examples. Make them plausible for the word's sound and
origin, and only about things that existed before 1913 (no motor cars, no electronics).

This is how real 1913 entries read:
{_examples()}

Reply with JSON only, in exactly this shape:
{{"definitions": ["...", "...", "..."]}}"""


def real_or_ghost(word: str, definition: str) -> str:
    """Seance / live opponent: is this word in Webster's 1913, or invented? One-word JSON answer."""
    return f"""This card shows a word and a definition. Either the word is a real entry in Webster's
Revised Unabridged Dictionary of 1913, with its true definition, or the word was invented
recently and does not exist.

Word: {word}
Definition: {definition}

Is the word real or invented? Reply with JSON only: {{"answer": "real"}} or {{"answer": "ghost"}}"""


def three_definitions(word: str, options: list[str]) -> str:
    """Seance / live opponent: which of three definitions is the true 1913 one."""
    lines = "\n".join(f"{i}. {d}" for i, d in enumerate(options, 1))
    return f"""The word "{word}" is a real entry in Webster's Revised Unabridged Dictionary of 1913.
Only one of these definitions is the true one; the other two were made up.

{lines}

Which number is the true definition? Reply with JSON only: {{"answer": 1}}, {{"answer": 2}} or {{"answer": 3}}"""


def define_word(word: str) -> str:
    """Seance: ask for a definition of a ghost, to see if the model makes one up."""
    return f"""Define the English word "{word}" in one sentence. If it is not a real word, say so.
Reply with JSON only: {{"real_word": true or false, "definition": "..."}}"""


def parse_list(payload: object, key: str) -> list:
    """Pull a list out of a model's JSON reply, tolerating a bare list."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        val = payload.get(key)
        if isinstance(val, list):
            return val
        for v in payload.values():
            if isinstance(v, list):
                return v
    raise ValueError(f"no list under {key!r}: {json.dumps(payload)[:200]}")
