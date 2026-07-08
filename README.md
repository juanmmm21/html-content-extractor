# html-content-extractor

**Project 2/10 of the [`beacon-search-engine`](https://github.com/juanmmm21/beacon-search-engine) ecosystem** — *Ingestion* category.
Repository: [`github.com/juanmmm21/html-content-extractor`](https://github.com/juanmmm21/html-content-extractor)

A boilerplate-removal pipeline: it takes the raw, often broken HTML produced
by [`web-crawler-scheduler`](https://github.com/juanmmm21/web-crawler-scheduler)
and turns it into clean main content — title, body text, author, publication
date, language — by scoring blocks of text according to their density and
their position in the DOM, not by scraping a handful of fragile CSS
selectors. No `readability-lxml`, `trafilatura`, `boilerpy3` or any other
extraction library: the DOM tree, the HTML parsing and the density heuristic
are all implemented from scratch.

## What problem it solves

Real web pages are not "an article inside a `<div>`". They are navigation
menus, cookie banners, related-article widgets, comment sections, ads and
footers, wrapped around a relatively small amount of actual content — and the
HTML itself is often malformed (unclosed tags, orphan closing tags,
inconsistent nesting). A search engine that indexes raw HTML indexes noise:
menu labels score as highly as real prose, and boilerplate shared across
every page on a site pollutes term statistics for all of them. This project
solves exactly that layer: given one crawled page, decide what part of it is
worth indexing.

## Role in `beacon-search-engine`

```text
web-crawler-scheduler
        │ pages.jsonl (raw HTML + metadata)
        ▼
┌───────────────────────────┐
│  html-content-extractor   │   (this project)
│  raw HTML → clean text    │
└─────────────┬─────────────┘
              │ documents.jsonl (title, main_text, author, date, language...)
              ▼
   inverted-index-builder → index-compression-codec → bm25-ranking-engine
                                                                 │
                                                                 ▼
                                                  (converges in beacon-search-console)
```

Together with `web-crawler-scheduler`, this is the ingestion base every other
piece of the ecosystem depends on: without a clean corpus there is no
meaningful vocabulary to tokenize, index or rank.

## Goal and skills demonstrated

- A from-scratch, readability-style text-density heuristic: leaf text blocks
  (`<p>`, `<li>`, `<td>`...) are scored by length, punctuation and
  `class`/`id` hints, propagated to their parent and grandparent containers,
  and the highest-scoring container wins as the main content root.
- A minimal DOM tree built directly on top of the standard library's
  `html.parser.HTMLParser`, tolerant of real-world malformed HTML (unclosed
  `<p>` tags, orphan closing tags, deeply inconsistent nesting) using
  simplified HTML5 recovery rules, not a third-party parser.
- Link-density filtering to drop boilerplate embedded *inside* an otherwise
  good content container (a "related articles" list living inside the
  `<article>` tag, for instance).
- Mojibake detection and corrective re-decoding when a page's declared
  charset (HTTP header vs. in-document `<meta>`) doesn't match the encoding
  actually used to decode it.
- Explicit, auditable handling of anything that isn't clean, indexable text:
  non-HTML content types, decode/parse failures and pages with insufficient
  main content are recorded as discards, never silently dropped or allowed to
  crash the batch.

## How it works

1. **Content-type filtering** (`pipeline.py`): pages whose `Content-Type` is
   clearly not HTML (`image/*`, `application/pdf`, ...) are discarded before
   any parsing is attempted.
2. **Encoding resolution** (`encoding.py`): compares the charset declared in
   the HTTP `Content-Type` header against the one declared in the
   in-document `<meta charset>` (or `<meta http-equiv="Content-Type">`). If
   mojibake markers are detected and a re-decoding with a candidate charset
   objectively reduces them, the corrected text is used; otherwise the
   original text is kept unchanged. This function never raises.
3. **Tolerant DOM parsing** (`htmlparse.py` + `domtree.py`): the HTML is fed
   to a hand-written `html.parser.HTMLParser` subclass that builds a
   lightweight `DomNode` tree, applying simplified HTML5 recovery rules
   (implicit `<p>` closing, ignoring orphan closing tags) so a single broken
   tag never aborts parsing.
4. **Main content extraction** (`density.py`): every leaf text block is
   scored; scores propagate to parent and grandparent containers; the
   winning container (plus its own `class`/`id` hint) is used as the root of
   the article, with structurally boilerplate sub-trees (`nav`, `header`,
   `footer`, `aside`, `form`) and link-heavy sub-trees pruned out. If no
   container scores highly enough, the whole document is used as a
   fallback so short, legitimate pages aren't lost to an over-strict
   heuristic.
5. **Metadata extraction** (`metadata.py`): title (`og:title` → first `<h1>`
   → `<title>`), author, published date and language, each resolved from the
   most explicit signal available.
6. **Normalization** (`normalize.py`): Unicode NFC normalization and
   whitespace collapsing, so the tokenizer in `inverted-index-builder`
   doesn't have to deal with equivalent-but-differently-encoded characters.
7. A page that fails at any of these stages (parse recursion blown past
   Python's limit on pathologically nested HTML, or insufficient main
   content after the heuristic) is written to `discarded.jsonl` with a
   specific `DiscardReason`, never silently lost.

## Architecture

```text
src/html_content_extractor/
├── models.py       # ExtractionConfig, ExtractedDocument, DiscardedPage, ExtractionStats
├── protocols.py    # interfaces: MainContentExtractor, MetadataExtractor
├── domtree.py       # DomNode: minimal hand-built DOM tree
├── htmlparse.py      # tolerant HTML → DomNode parsing (stdlib html.parser)
├── encoding.py         # mojibake detection and corrective re-decoding
├── density.py           # from-scratch text-density boilerplate-removal heuristic
├── metadata.py            # title / author / published date / language extraction
├── normalize.py             # Unicode NFC + whitespace normalization
├── pipeline.py                # ExtractionPipeline: orchestrates everything above
└── __main__.py                 # CLI (`extract`, `stats`)
```

## Requirements and installation

- Python `>=3.11`
- No runtime dependencies — everything (DOM tree, HTML parsing, density
  heuristic) is built on the standard library.

```bash
git clone https://github.com/juanmmm21/html-content-extractor.git
cd html-content-extractor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage (CLI)

```bash
# Extract clean documents from a pages.jsonl produced by web-crawler-scheduler
html-content-extractor extract ./crawl-output/pages.jsonl --output-dir ./extracted

# Tune the density heuristic
html-content-extractor extract ./crawl-output/pages.jsonl \
  --output-dir ./extracted \
  --min-main-content-chars 300 \
  --link-density-threshold 0.4

# Quick stats on an already-extracted documents.jsonl
html-content-extractor stats ./extracted/documents.jsonl
```

It can also be invoked as a module: `python -m html_content_extractor extract ...`.

## Data formats

`--output-dir` produces two JSONL files (one line = one record):

**`documents.jsonl`** — a successfully extracted document, the direct input
of [`inverted-index-builder`](https://github.com/juanmmm21/inverted-index-builder):

```json
{
  "url": "http://example.com/article",
  "final_url": "http://example.com/article",
  "title": "A Long Article About Search",
  "main_text": "This paragraph contains a substantial amount of real prose...",
  "language": "en",
  "author": "Jane Doe",
  "published_at": "2024-01-15T10:00:00+00:00",
  "fetched_at": "2024-01-15T09:00:00+00:00",
  "extracted_at": "2026-07-08T17:00:00+00:00",
  "encoding_used": "utf-8",
  "depth": 1,
  "word_count": 214
}
```

**`discarded.jsonl`** — pages that did not produce an indexable document,
for auditing:

```json
{
  "url": "http://example.com/brochure.pdf",
  "reason": "non_html_content",
  "detail": "application/pdf",
  "discarded_at": "2026-07-08T17:00:00+00:00"
}
```

`reason` is one of `non_html_content`, `parse_error` (pathological HTML
nesting) or `empty_main_content` (nothing scored highly enough under the
density heuristic).

## Programmatic usage

```python
from pathlib import Path

from html_content_extractor.models import ExtractionConfig
from html_content_extractor.pipeline import ExtractionPipeline

config = ExtractionConfig(min_main_content_chars=200, link_density_threshold=0.5)
output = Path("./extracted")

with ExtractionPipeline(
    config,
    documents_output_path=output / "documents.jsonl",
    discarded_output_path=output / "discarded.jsonl",
) as pipeline:
    stats = pipeline.run(Path("./crawl-output/pages.jsonl"))

print(stats.pages_extracted, stats.pages_discarded)
```

## Development

```bash
pytest
ruff check .
mypy --strict src/
```

76 tests cover the domain models (JSON round-trips, config validation), the
tolerant DOM parser (malformed HTML fixtures: unclosed `<p>`, orphan closing
tags, pathological nesting), the density heuristic (boilerplate exclusion,
positive/negative class hints, fallback behavior), metadata extraction,
Unicode normalization, encoding correction (real mojibake fixtures built by
round-tripping known text through the wrong codec) and the end-to-end
pipeline and CLI.

## Troubleshooting

- **A whole page ends up in `discarded.jsonl` with `empty_main_content`:**
  the density heuristic didn't find any container scoring above
  `min_main_content_chars`. This is common on pages that are mostly a link
  list (category/tag pages) — lower `--min-main-content-chars` if that class
  of page is expected to still be worth indexing, or leave it as-is if it
  genuinely isn't an article.
- **The extracted text is missing a section I'd expect to see:** the
  density heuristic isolates a single winning container; content that lives
  outside of it (e.g. a stray paragraph directly under `<body>`, sitting
  next to the real `<article>`) is intentionally dropped, mirroring how
  classic readability-style algorithms behave.
- **`encoding_used` isn't what I expected:** `resolve_encoding` only
  corrects mojibake when it can objectively verify the fix reduces garbled
  characters; if the original bytes were already lost upstream (`aiohttp`
  decodes with `errors="replace"` in `web-crawler-scheduler`), no
  re-decoding can recover them, so the text is left as-is.
- **`mypy` fails under `tests/`:** expected — only `src/` is type-checked in
  `--strict` mode; test doubles and fixtures use deliberately looser typing.

## License

MIT — see [`LICENSE`](./LICENSE).
