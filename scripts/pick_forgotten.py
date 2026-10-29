"""Pick candidate "forgotten" real words from the parsed 1913 Webster's.

    uv run python scripts/pick_forgotten.py            # candidates
    uv run python scripts/pick_forgotten.py --curate   # hand-picked list -> data/reals.json

Reads  data/webster1913.jsonl
Writes data/forgotten-candidates.json  (~500, for hand curation into data/reals.json)
       data/reals.json                 (the CURATED words below)

A candidate must be a single word of 5-14 letters that modern English no longer uses (wordfreq
does not know it: zipf below ZIPF_MAX, and every wordfreq zipf is >= 1.0 or exactly 0), with a
first sense that reads cleanly on a card once the 1913 labels and quotations are stripped.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any

from wordfreq import zipf_frequency

ROOT = Path(__file__).resolve().parent.parent
IN_JSONL = ROOT / "data" / "webster1913.jsonl"
OUT = ROOT / "data" / "forgotten-candidates.json"

ZIPF_MAX = 1.0  # below this = not in wordfreq's modern English list at all
MIN_LEN, MAX_LEN = 5, 14
DEF_MIN, DEF_MAX = 25, 140
TARGET = 500
SEED = 1913
POS_OK = {"n.", "a.", "v. t.", "v. i.", "adv.", "v. t. & i.", "v. i. & t."}

# Usage labels that are fine (they are what "forgotten" means); every other label is a field
# label (Bot., Zool., Chem., Law ...) and marks jargon.
USAGE_LABELS = {"Obs.", "R.", "Archaic", "Colloq.", "Poetic", "Prov. Eng.", "Scot.", "Obs. or R.", "Obs. or Archaic"}

CROSS_REF_RE = re.compile(
    r"^(?:See |Same as|pl\. of|imp\.|p\. p\.|p\. pr\.|Alt\. of|An obsolete|Obs\. form|of |"
    r"superl\.|compar\.|A variant|Variant of|Plural of|A form of|An old form|Corrupt)",
    re.IGNORECASE,
)
# Phrases that point at a field even without a label.
JARGON_RE = re.compile(
    r"\b(?:genus|genera|species|family|order of|suborder|class of|tribe of|larva|mollusk|"
    r"crustacean|alkaloid|compound|acid|salt of|ester|radical|mineral|crystal|alloy|"
    r"hydrocarbon|the plant|a plant|shrub|a tree|herb|fungus|insect|beetle|moth|fish|"
    r"sea|bird|mammal|zool|bot|chem|anat|med|naut|her\.|mus\.|geom|math|surgery|disease|"
    r"inflammation|ligament|bone|muscle|nerve|gland|membrane|tumor|ulcer|ointment)\b",
    re.IGNORECASE,
)
# 1913 attitudes on race, religion, gender and disability, slurs, and sexual content.
BLOCK_RE = re.compile(
    r"(?:negro|negress|mulatto|quadroon|octoroon|savage|barbarian|heathen|pagan|infidel|"
    r"papist|popish|romish|jew|jewish|hebrew|mahomet|moham|moslem|musulman|turk|moor|gypsy|"
    r"gipsy|hindoo|hindu|oriental|chinese|chinaman|coolie|indian|african|aborigin|native|"
    r"tribe|race|slave|idiot|imbecile|lunatic|insane|madman|cripple|deform|dwarf|hunchback|"
    r"deaf|dumb|blind|woman|women|wife|wives|female|girl|maid|wench|harlot|whore|strumpet|"
    r"prostitut|concubine|mistress|courtesan|lewd|lust|lecher|venere|copulat|sodom|bastard|"
    r"incest|adulter|eunuch|castrat|sexual|pederast|effemin|negroid|caste|christ|church|"
    r"god|bible|scripture|clergy|priest|monk|nun\b|pope|bishop|sect|heresy|heretic|"
    r"idolat|worship|sacrament|baptis|catholic|protestant|lord|king|queen|liturg|gospel|"
    r"faith|divine\b|sacred|holy|saint|anglican|china|\bhag|lame\b|cripple|leper|"
    r"servant|beggar|pauper)",
    re.IGNORECASE,
)
# Definitions on these themes go into the candidate list first; the rest is a random sample.
THEME_RE = re.compile(
    r"\b(?:ghost|spirit|spectr|specter|phantom|apparition|death|dead|die|dying|grave|tomb|"
    r"sepulch|corpse|burial|bury|funeral|coffin|skull|night|dark|shadow|gloom|witch|wizard|"
    r"sorcer|magic|charm|spell|enchant|divination|omen|portent|prophe|demon|devil|fiend|"
    r"fear|dread|terror|horror|fright|blood|doom|curse|haunt|howl|wail|moan|mourn|grief|"
    r"poison|murder|kill|slay|owl|raven|wolf|moon|dream|sleep|nightmare|mad|rot|decay|"
    r"ruin|wraith|soul|hell|torment|crypt|cellar|candle|smoke|mist|fog|cold|chill|shriek|"
    r"scream|lament|weep|tear|sorrow|wicked|evil|secret|hidden|conceal|lonely|sad|fire|"
    r"burn|ash|bone)\w*",
    re.IGNORECASE,
)
THEME_MAX = 220

BRACKET_RE = re.compile(r"\s*\[[^\]]*\]")
QUOTE_RE = re.compile(r"\s*\"[^\"]*\"(?:\s+[A-Z][\w.&' ]{0,25}\.)?")
EXAMPLE_RE = re.compile(r"[;,]?\s+as,\s.*$")
TRAILING_AUTHOR_RE = re.compile(r"([.;])\s+(?:[A-Z][a-z']{0,8}\.?\s*(?:&\s*)?){1,4}\.?$")


def card_definition(text: str) -> str:
    """The 1913 first sense as a card shows it: no [labels], quotations, examples or authors.

    The full entry is shown on the reveal; the card must not give the answer away (a ghost's
    definition has no "[Obs.] Chaucer." after it).
    """
    s = BRACKET_RE.sub("", text)
    s = QUOTE_RE.sub("", s)
    s = EXAMPLE_RE.sub(".", s)
    s = TRAILING_AUTHOR_RE.sub(r"\1", s)
    s = re.sub(r"\s+", " ", s).strip().rstrip(";,: ")
    if s and s[-1] not in ".!?":
        s += "."
    return s


def stem_in_definition(word: str, definition: str) -> bool:
    """'quixotry: Quixotism; visionary schemes.' explains itself; such cards are dull."""
    stem = word[:5].lower()
    return any(tok.lower().startswith(stem) for tok in re.findall(r"[A-Za-z]+", definition))


def reject_reason(
    entry: dict[str, Any],
    zipf: float | None = None,
    known_words: frozenset[str] | None = None,
) -> str | None:
    """None if the entry is a usable forgotten word, else a short reason."""
    word = entry["word"]
    if not word.isalpha() or not word.isascii():
        return "not letters only"
    if not MIN_LEN <= len(word) <= MAX_LEN:
        return "length"
    if entry.get("pos") not in POS_OK:
        return "part of speech"
    if not entry.get("senses"):
        return "no sense"
    raw = entry["senses"][0]["text"]
    if CROSS_REF_RE.match(raw):
        return "cross-reference"
    labels = entry.get("labels", [])
    if any(lab not in USAGE_LABELS for lab in labels) or re.match(r"^\(", raw):
        return "field label"
    definition = card_definition(raw)
    if not DEF_MIN <= len(definition) <= DEF_MAX:
        return "definition length"
    if re.search(r"[\"()0-9]|--|\bfig\.|\bi\. e\.|\be\. g\.|\bcf\.", definition, re.IGNORECASE):
        return "messy definition"
    # A trailing author or cross-reference the cleaner missed: "... quarrel. Chesterfield."
    if re.search(r"\.\s+[A-Z].{0,40}$", definition):
        return "messy definition"
    if JARGON_RE.search(definition):
        return "jargon"
    if BLOCK_RE.search(definition) or BLOCK_RE.search(word):
        return "blocklist"
    if stem_in_definition(word, definition):
        return "explains itself"
    if zipf is None:
        zipf = zipf_frequency(word, "en")
    if zipf >= ZIPF_MAX:
        return "still in modern use"
    if known_words is not None and has_typo(definition, known_words):
        return "typo in definition"
    return None


def has_typo(definition: str, known_words: frozenset[str]) -> bool:
    """Gutenberg's text has typos ("Toughtless", "hinding"). A definition word that neither
    wordfreq nor the 1913 headword list knows is treated as a typo. Common misspellings
    ("togheter", "succed") are in wordfreq and get through; hand curation catches those."""
    for tok in re.findall(r"[A-Za-z\u00c0-\u00ff]+", definition):
        t = tok.lower()
        if len(t) <= 2 or zipf_frequency(t, "en") > 0:
            continue
        forms = {t} | {t[: -len(suf)] for suf in ("s", "es", "ed", "d", "ing", "ly", "er") if t.endswith(suf)}
        if not forms & known_words:
            return True
    return False


def is_themed(definition: str) -> bool:
    return bool(THEME_RE.search(definition))


def candidate(entry: dict[str, Any]) -> dict[str, Any]:
    s = entry["senses"][0]
    return {
        "word": entry["word"],
        "pos": entry["pos"],
        "definition": card_definition(s["text"]),
        "sense": s["text"],
        "quote": s.get("quote", ""),
        "author": s.get("author", ""),
        "etym": entry.get("etym", ""),
        "labels": entry.get("labels", []),
        "pron": entry.get("pron", ""),
        "line": entry["line"],
        "themed": is_themed(card_definition(s["text"])),
    }


REALS_OUT = ROOT / "data" / "reals.json"

# Hand-picked from data/forgotten-candidates.json (read one by one, Thu 29 Oct 2026). Dropped:
# words still in use (crepitate, frowzy, pandowdy, ululate), OCR typos in the definition
# (cheve "succed", crimeful "dury", unwitch "fee from"), definitions naming a real place, person
# or book (angelot, sobranje, tirrit), religious or gendered ones (preadamite, evangelistary),
# dull "-ness" / "mis-" forms, and most of the divination words (-mancy) so they are not a tell.
# Leans towards the dark themes (death, night, spirits, fire) on purpose; it is a ghost game.
CURATED = """
abscondence abusion adustion affabrous alepole aleuromancy amort anagogic animastic
arreptitious asomatous awless balefire beblubber benight bestraught beweep bibliotaph
birthnight bragget bridestake carmot carnivoracity cerement ceromancy clinquant cloop
commorient coranach coscinomancy cruciation darkle dastardize deadhearted decharm delirament
demiwolf digladiate dilacerate dilaniate diremption dominicide effascination egritude eloge
embeam eremacausis exustion fascinous fatiferous figary fogbow foretoken frumenty fuliginous
funebrial fustilarian gashful geloscopy girandole grume hariolation hearsecloth hellbroth
hippocras horrisonous hyperphysical idolum ignigenous immask incension incremate infelt
infestive infestuous infrigidation insoul interlunar internecion inustion lachrymation
latitation leasy lexiphanicism litherly lunarian lunet manqueller mellifluence metheglin
mistide misween monomachist moonglade nihility nugacity nunchion obreptitious obumbration
occision ogrism omnivagant omophagic oneirocritic oneiromancy outfrown outquench owlery
parietine pernoctalian pesanted queach rawhead ruinate sanguineless saulie sauseflem scarmage
sciagraphy scotograph sepiment sideromancy skelder somniculous sororicide spright sterve
stomachous stramazoun sublunar telesm thanatoid thurification ticktack tourbillion trunkwork
umbrate unclew uncreate uncurse undercreep undersong ungrave unseel unsoul ustorious
vermiculose vigesimation warison wileful
""".split()


def curate() -> int:
    """Write data/reals.json: the CURATED words, with their 1913 entries, from the candidates."""
    cands = {c["word"]: c for c in json.loads(OUT.read_text(encoding="utf-8"))}
    missing = [w for w in CURATED if w not in cands]
    if missing:
        print(f"not in candidates: {missing}", file=sys.stderr)
        return 1
    if len(set(CURATED)) != len(CURATED):
        print("duplicate words in CURATED", file=sys.stderr)
        return 1
    reals = [{"id": f"r{i:03d}", **cands[w]} for i, w in enumerate(sorted(CURATED), 1)]
    for r in reals:
        r.pop("themed", None)
    REALS_OUT.write_text(json.dumps(reals, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(reals)} real words to {REALS_OUT.relative_to(ROOT)}")
    return 0


def main() -> int:
    if "--curate" in sys.argv:
        return curate()
    known = frozenset(
        w for w in (ROOT / "data" / "headwords.txt").read_text(encoding="utf-8").split("\n") if w
    )
    seen: set[str] = set()
    pool: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    with IN_JSONL.open(encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry["word"] in seen:
                continue  # first entry of a spelling only (MOTTLE v. t. before MOTTLE n.)
            seen.add(entry["word"])
            why = reject_reason(entry, known_words=known)
            if why:
                reasons[why] = reasons.get(why, 0) + 1
            else:
                pool.append(candidate(entry))
    rng = random.Random(SEED)
    themed = [c for c in pool if c["themed"]]
    plain = [c for c in pool if not c["themed"]]
    take_themed = rng.sample(themed, min(THEME_MAX, len(themed)))
    take_plain = rng.sample(plain, min(TARGET - len(take_themed), len(plain)))
    picked = sorted(take_themed + take_plain, key=lambda c: c["word"])
    OUT.write_text(json.dumps(picked, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(
        f"pool {len(pool):,} ({len(themed):,} on dark themes); wrote {len(picked)} "
        f"({len(take_themed)} themed) to {OUT.relative_to(ROOT)}"
    )
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  rejected {n:>6,}  {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
