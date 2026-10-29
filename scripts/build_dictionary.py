"""Parse the Project Gutenberg text of Webster's 1913 into JSON lines.

    uv run python scripts/build_dictionary.py

Reads  data/raw/webster1913.txt   (from scripts/fetch_dictionary.py)
Writes data/webster1913.jsonl     one entry per line (see Entry below)
       data/headwords.txt         every headword and spelling variant, lowercased, sorted

Entry layout in the source text:

    GALLIMAUFRY                                           <- headword line (caps; variants split by ;)
    Gal`li*mau"fry, n.; pl. Gallimaufries. Etym: [F. ...  <- header: pronunciation, part of speech,
    ragout or mixed hash of different meats.]                etymology, field labels like (Bot.)

    1. A hash of various kinds of meats, a ragout.        <- sense ("Defn:" when there is only one)
    Delighting in hodge-podge, gallimaufries, ... King.   <- quotation, ends with the author

    2. Any absurd medley; a hotchpotch.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "webster1913.txt"
OUT_JSONL = ROOT / "data" / "webster1913.jsonl"
OUT_HEADWORDS = ROOT / "data" / "headwords.txt"

HEADWORD_RE = re.compile(r"^[A-Z][A-Z0-9 ;'\-\.,&]*$")
SENSE_START_RE = re.compile(r"^(?:Defn:\s*|(\d+)\.\s+|\(([a-z])\)\s+)")
ETYM_RE = re.compile(r"Etym:\s*\[")
FIELD_LABEL_RE = re.compile(r"\(([A-Z][A-Za-z\u00c0-\u00ff]*\.?(?:\s*(?:&\s*)?[A-Z][A-Za-z\u00c0-\u00ff]*\.?)*)\)")
BRACKET_LABEL_RE = re.compile(r"\[((?:Obs|R|Archaic|Colloq|Prov\. Eng|Scot|Local|Poetic|Cant|Slang|Vulgar|Low|U\.\s?S|Eng|Dial|Humorous|Jocose|Rare)[^\]]{0,40})\]")
POS_RE = re.compile(
    r",\s*((?:(?:n|a|v|adv|prep|conj|interj|pron|p|pr|imp|vb|pl|sing|superl|compar|t|i|obj|poss|nom|prefix|suffix)\.?(?:\s*[&,]?\s*)?)+?)(?=\s*(?:;|Etym:|\[|\(|$|,|\.\s))"
)
# "... forced meat. King." / "Sir T. Browne." / "... of the Jewish. South." / "Bp. Hall."
AUTHOR = r"((?:[A-Z][a-z']{0,6}\.?\s+){0,3}[A-Z][A-Za-z'\u00c0-\u00ff\-]+)\.?"
QUOTE_AUTHOR_RE = re.compile(r"(?:^|[.!?;:,\"'\u201d)\]]\s*)" + AUTHOR + r"$")
AUTHOR_ONLY_RE = re.compile(r"^" + AUTHOR + r"$")
DEF_LINE_END = (".", "]", "?", "!", ")")


def _strip_accents(s: str) -> str:
    s = s.replace("\u00c6", "AE").replace("\u00e6", "ae").replace("\u0152", "OE").replace("\u0153", "oe")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def letters_only(s: str) -> str:
    """'Gal`li*mau"fry' -> 'gallimaufry'. Used to match headword lines to their header."""
    return re.sub(r"[^a-z]", "", _strip_accents(s).lower())


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Sense:
    text: str  # the definition text, labels kept as printed
    number: str = ""  # "1", "2", "a" ... or "" for a single Defn:
    quote: str = ""  # the first illustrative quotation, if any
    author: str = ""  # its author, if one could be split off


@dataclass
class Entry:
    word: str  # first spelling, lowercased: "gallimaufry"
    variants: list[str]  # all spellings on the headword line, lowercased
    headline: str  # the headword line as printed: "GALLIMAUFRY"
    header: str  # pronunciation / part of speech / etymology block (not written to JSON)
    pron: str  # the printed pronunciation: 'Gal`li*mau"fry'
    pos: str  # "n.", "a.", "v. t." ... ("" if not found)
    etym: str  # text inside Etym: [...]
    labels: list[str]  # field and usage labels found in the header and first sense: Bot., Obs. ...
    senses: list[Sense] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # "Note:", "Syn.", "--" phrase paragraphs
    line: int = 0  # 1-based line number of the headword line in the raw text

    @property
    def first_def(self) -> str:
        return self.senses[0].text if self.senses else ""


def _is_headword(lines: list[str], i: int) -> bool:
    line = lines[i]
    if not line or "  " in line or not HEADWORD_RE.match(line):
        return False
    if i == 0 or lines[i - 1] != "" or i + 1 >= len(lines) or lines[i + 1] == "":
        return False
    first = letters_only(line.split(";")[0])[:2]
    nxt = letters_only(lines[i + 1].lstrip("{ ("))[:2]
    # Single letters (A, B ...) and a handful of odd headers do not echo the headword; accept
    # them only if the header line starts with the same letter.
    return bool(first) and (nxt.startswith(first) or nxt[:1] == first[:1])


def _paragraphs(lines: list[str]) -> Iterator[list[str]]:
    para: list[str] = []
    for line in lines:
        if line.strip() == "":
            if para:
                yield para
                para = []
        else:
            para.append(line)
    if para:
        yield para


def _extract_etym(header: str) -> str:
    m = ETYM_RE.search(header)
    if not m:
        return ""
    depth, start = 1, m.end()
    for j in range(start, len(header)):
        if header[j] == "[":
            depth += 1
        elif header[j] == "]":
            depth -= 1
            if depth == 0:
                return clean_text(header[start:j])
    return clean_text(header[start:])


def _extract_pron(header: str) -> str:
    """'Gal`li*mau"fry, n.; pl. ...' -> 'Gal`li*mau"fry'."""
    return re.split(r",|\s+Etym:|\.\s|\.$|\s\(", header, maxsplit=1)[0].strip(" {}")


def _extract_pos(header: str) -> str:
    # Look only at the part before the etymology; the pronunciation ends at the first comma.
    head = ETYM_RE.split(header, maxsplit=1)[0]
    m = POS_RE.search(head)
    if not m:
        return ""
    return clean_text(m.group(1)).rstrip(",&; ")


def find_labels(text: str) -> list[str]:
    out: list[str] = []
    for m in FIELD_LABEL_RE.finditer(text):
        lab = m.group(1).strip()
        if len(lab) <= 30 and lab[0].isupper() and (lab.endswith(".") or " " in lab or lab in {"Law", "Her", "Mus"}):
            out.append(lab)
    for m in BRACKET_LABEL_RE.finditer(text):
        out.append(clean_text(m.group(1)))
    return out


def _split_quote(para: list[str]) -> tuple[str, str]:
    text = clean_text(" ".join(para))
    m = QUOTE_AUTHOR_RE.search(text)
    if m and len(m.group(1)) <= 40:
        return text[: m.start(1)].strip(), m.group(1).strip().rstrip(".")
    return text, ""


NOT_AUTHOR_START = ("See ", "Cf. ", "Also ", "Written ", "Same ", "Called ", "The ", "A ", "An ")


def _split_sense(lines: list[str]) -> tuple[str, str, str]:
    """Split a sense paragraph into (definition, quotation, author).

    Quotations follow the definition on the next line with no blank line between them
    ("1. A hash of various kinds of meats, a ragout." / "Delighting in ... forced meat. King.").
    A split is made only after a line that ends a sentence, and only if the rest ends with an
    author name.
    """
    # Quotations are at most a few lines; long paragraphs (tables, essays under "A") are left whole.
    for k in range(max(1, len(lines) - 8), len(lines)):
        if not lines[k - 1].rstrip().endswith(DEF_LINE_END):
            continue
        tail = clean_text(" ".join(lines[k:]))
        if tail.startswith(NOT_AUTHOR_START[:5]):
            continue
        m = QUOTE_AUTHOR_RE.search(tail)
        if not m or len(m.group(1)) > 30:
            continue
        quote = tail[: m.start(1)].strip()
        if quote and len(quote.split()) < 3:
            continue
        if not quote and (tail.startswith(NOT_AUTHOR_START) or not AUTHOR_ONLY_RE.match(tail)):
            continue
        return clean_text(" ".join(lines[:k])), quote, m.group(1)
    return clean_text(" ".join(lines)), "", ""


LABEL_ONLY_RE = re.compile(r"^(?:\([^)]{1,40}\)\s*)*$")


def _split_at_senses(para: list[str]) -> Iterator[list[str]]:
    """'(a) ...' / '(b) ...' and '1. ...' lines start a new sense even without a blank line."""
    chunk: list[str] = []
    for line in para:
        if chunk and SENSE_START_RE.match(line):
            yield chunk
            chunk = []
        chunk.append(line)
    if chunk:
        yield chunk


def _parse_body(body: list[str], entry: Entry) -> None:
    current: Sense | None = None
    for big in _paragraphs(body):
        for para in _split_at_senses(big):
            first = para[0]
            m = SENSE_START_RE.match(first)
            if m:
                number = m.group(1) or m.group(2) or ""
                text, quote, author = _split_sense([first[m.end():], *para[1:]])
                # "1. (Arch.)" then a blank line then "Defn: A rod with ...": one sense.
                if (
                    current is not None
                    and first.startswith("Defn:")
                    and current.number
                    and LABEL_ONLY_RE.match(current.text)
                ):
                    current.text = clean_text(f"{current.text} {text}")
                    current.quote, current.author = quote, author
                    continue
                current = Sense(text=text, number=number, quote=quote, author=author)
                entry.senses.append(current)
            elif first.startswith(("Note:", "Syn.")) or first.strip().startswith("--"):
                entry.notes.append(clean_text(" ".join(para)))
            elif current is not None and not current.quote:
                current.quote, current.author = _split_quote(para)
            else:
                entry.notes.append(clean_text(" ".join(para)))


def _parse_block(block: list[str], line_no: int) -> Entry:
    headline = block[0]
    variants = [v.strip().lower() for v in headline.split(";") if v.strip()]
    rest = block[1:]
    # The header runs from the pronunciation line to the first blank line, or to the first line
    # that starts a sense ("(a) The cashew tree ..." can follow the header directly).
    cut = len(rest)
    for j, line in enumerate(rest):
        if line == "" or (j > 0 and SENSE_START_RE.match(line)):
            cut = j
            break
    header_lines, body = rest[:cut], rest[cut:]
    header = clean_text(" ".join(header_lines))
    entry = Entry(
        word=variants[0],
        variants=variants,
        headline=headline,
        header=header,
        pron=_extract_pron(header),
        pos=_extract_pos(header),
        etym=_extract_etym(header),
        labels=[],
        line=line_no,
    )
    _parse_body(body, entry)
    if not entry.senses:
        # A few entries put the sense on the pronunciation line itself:
        # 'A*ë`ri*al rail"way`. (a) A stretched wire ...'. Split there, outside any [brackets].
        inline = _inline_sense_start(header)
        if inline is not None:
            entry.header = header[:inline].strip()
            entry.pron = _extract_pron(entry.header)
            entry.etym = _extract_etym(entry.header)
            _parse_body([header[inline:].strip()], entry)
    labels = find_labels(entry.header)
    if entry.senses:
        labels += find_labels(entry.senses[0].text)
    entry.labels = list(dict.fromkeys(labels))
    return entry


def _inline_sense_start(header: str) -> int | None:
    depth = 0
    for j, ch in enumerate(header):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in "D(1" and j > 0 and header[j - 1] == " ":
            if re.match(r"Defn:|\(a\)\s|1\.\s", header[j:]):
                return j
    return None


def parse_lines(lines: list[str]) -> Iterator[Entry]:
    """Yield entries from the dictionary body (Gutenberg header/footer already removed or not)."""
    start = next((i + 1 for i, l in enumerate(lines) if l.startswith("*** START")), 0)
    end = next((i for i, l in enumerate(lines) if l.startswith("*** END")), len(lines))
    heads = [i for i in range(start, end) if _is_headword(lines, i)]
    for k, i in enumerate(heads):
        stop = heads[k + 1] if k + 1 < len(heads) else end
        yield _parse_block(lines[i:stop], i + 1)


def parse_text(text: str) -> list[Entry]:
    return list(parse_lines(text.splitlines()))


def entry_to_json(e: Entry) -> dict:
    d = asdict(e)
    del d["header"]
    d["senses"] = [{k: v for k, v in s.items() if v or k == "text"} for s in d["senses"]]
    if not d["notes"]:
        del d["notes"]
    return d


def write_outputs(entries: Iterable[Entry]) -> tuple[int, int]:
    words: set[str] = set()
    n = 0
    with OUT_JSONL.open("w", encoding="utf-8", newline="\n") as f:
        for e in entries:
            f.write(json.dumps(entry_to_json(e), ensure_ascii=False) + "\n")
            words.update(e.variants)
            n += 1
    OUT_HEADWORDS.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8", newline="\n")
    return n, len(words)


def main() -> int:
    if not RAW.exists():
        print(f"missing {RAW}; run scripts/fetch_dictionary.py first", file=sys.stderr)
        return 1
    entries = parse_text(RAW.read_text(encoding="utf-8"))
    n, w = write_outputs(entries)
    with_def = sum(1 for e in entries if e.senses)
    single = sum(1 for e in entries if e.word.isalpha())
    print(f"entries {n:,}; with a sense {with_def:,}; single-word {single:,}; headwords {w:,}")
    print(f"{OUT_JSONL.relative_to(ROOT)} {OUT_JSONL.stat().st_size / 1e6:.1f} MB")
    print(f"{OUT_HEADWORDS.relative_to(ROOT)} {OUT_HEADWORDS.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
