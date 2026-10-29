# Ghost Words

In 1934 Webster's printed a word that never existed: **dord**, a misread slip for
"D or d = density". It stayed in the dictionary until 1947. Editors call these **ghost words**.

Ghost Words is a candlelit horror card game that runs on your laptop. You tell real forgotten
words from the 1913 Webster's (public domain) apart from fakes that Gemma invents locally. Gemma
plays the same cards against you. Code, not the model, decides what is real.

## How to play

- **Real or Ghost?** Twenty cards, one word and its meaning each. Is it a forgotten word from
  1913, or a ghost Gemma made up? Press **R** or **G**.
- **Three Definitions.** Twenty real words. One meaning is from 1913; Gemma wrote the other two.
  Press **1**, **2** or **3**.
- Every reveal shows the proof: the original 1913 entry (with its line in the Project Gutenberg
  text), or "no trace" and the checks a ghost passed.
- **Summon a fresh ghost** asks Gemma for a new fake word live and runs the same checks on it.
  Sometimes the "fake" turns out to be a real 1913 word.
- **The séance** shows how often two small open models believe their own ghosts.
- **Enter** moves on, **M** mutes. The game ends on the story of dord.

## Run it

You need [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/) and Node.js 22. It was
built on Windows with an RTX 2050 (4 GB VRAM).

```sh
ollama pull gemma4:e2b
ollama pull gemma3:1b
ollama pull qwen3-embedding:0.6b

uv sync
cd frontend
npm install
npm run build
cd ..

uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. FastAPI serves the built front end, so that one command runs the game.
`gemma4:e2b` is the only model the game itself calls; the other two are used by the scripts below,
and `/api/health` reports all three. If Gemma is slow or offline, its answer for a card comes from
the séance results instead.

For front-end work, run `npm run dev` in `frontend/` (Vite on :5173, `/api` proxied to :8000).

Tests: `uv run pytest -m "not ollama"` (the `ollama` marker needs the models running).

## How it works

```
Browser (React + TypeScript + Vite, Motion, Web Audio)
   │  /api/*
   ▼
FastAPI on 127.0.0.1:8000  ── game state in memory, answers sent only after you answer
   ├── dictionary.py   102,461 headwords parsed from Webster's 1913
   ├── checks.py       every real/fake rule, shared by the scripts and the API
   └── ollama_client.py  127.0.0.1:11434, one request at a time, timeout, one retry
```

The data is built once by scripts and committed (except the raw text):

| Script | Does |
|---|---|
| `scripts/fetch_dictionary.py` | Downloads Project Gutenberg #29765 with resume, checks the end marker, records SHA-256. Writes `data/raw/` (gitignored). |
| `scripts/build_dictionary.py` | Parses entries into `data/webster1913.jsonl` and `data/headwords.txt`. |
| `scripts/pick_forgotten.py` | 500 candidate real words that modern English no longer uses (not in wordfreq), with a clean first sense; curated by hand to 150 in `data/reals.json`. |
| `scripts/make_ghosts.py` | Gemma invents fake words in 1913 style. Each must pass the checks below. 449 offered, 152 kept; every rejection and its reason is in `data/ghost-rejections.json`. |
| `scripts/make_bluffs.py` | For each real word Gemma sees only the word, part of speech and origin, and writes fake definitions. Each is embedded with `qwen3-embedding:0.6b`; a bluff with cosine similarity above 0.70 to the true definition is dropped as too close. |
| `scripts/run_seance.py` | The benchmark: `gemma4:e2b` and `gemma3:1b` play 100 Real or Ghost cards, 50 Three Definitions words and 30 "define this word" ghosts at temperature 0. Writes `data/seance-results.json`; `--table` prints the markdown table. |

A ghost is only a ghost if code says so (`backend/checks.py`):

1. 5-14 letters, a-z only.
2. Not a headword or spelling variant in Webster's 1913.
3. Not in wordfreq's modern English list.
4. Not one letter added, dropped or changed from a 1913 headword.
5. Not a 1913 headword plus an ending (-s, -ed, -ing, -ly, -ness ...).
6. Not a duplicate. Then a hand review removed plain Latin and real words wordfreq misses.

Of Gemma's 449 "fakes", 96 were real 1913 headwords and 71 were one letter away from one.

## Credits

- Webster's Revised Unabridged Dictionary (1913), from
  [Project Gutenberg #29765](https://www.gutenberg.org/ebooks/29765). Public domain in the US.
  The raw text is not redistributed here; `fetch_dictionary.py` downloads it from Project
  Gutenberg, whose licence covers that file.
- The story of dord: Merriam-Webster,
  ["Dord": a ghost word](https://www.merriam-webster.com/wordplay/dord-a-ghost-word) (linked and
  paraphrased).
- [wordfreq](https://github.com/rspeer/wordfreq) by Robyn Speer: code Apache 2.0, word-list data
  CC BY-SA 4.0. It includes data from the
  [Google Books Ngram Viewer](http://books.google.com/ngrams).
- [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) (MIT) for edit distance.
- Fonts: IM Fell English and IM Fell English SC (Igino Marini) and EB Garamond, SIL Open Font
  License, bundled through @fontsource.
- Models: Gemma 4 (`gemma4:e2b`) and Gemma 3 (`gemma3:1b`) under the Gemma terms of use;
  Qwen3-Embedding 0.6B under its licence. Run locally with Ollama.

## Licence

MIT. See [LICENSE](LICENSE).
