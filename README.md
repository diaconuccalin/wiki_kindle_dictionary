# Wikipedia Kindle Dictionary

A Python pipeline that converts Wikipedia dump files into a Kindle-compatible `.mobi` dictionary. When you long-press any word on your Kindle, the dictionary popup shows the English Wikipedia abstract for that topic — including lookups via foreign-language titles (e.g., "București" shows the Bucharest article).

[![Download](https://img.shields.io/github/v/release/diaconuccalin/wiki_kindle_dictionary?label=Download&logo=kindle&style=for-the-badge)](https://github.com/diaconuccalin/wiki_kindle_dictionary/releases/latest)

## Prerequisites

- **Python 3.10+**
- **KindleGen** — download from Amazon or use the one bundled with Kindle Previewer 3
- **~40 GB disk space** for raw downloads + intermediate data (less for smaller profiles)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
# Build the Pocket profile (100K entries, ~55 MB .mobi)
make all PROFILE=pocket

# Or run with fast compression during development
make all PROFILE=pocket FAST=1

# Test mode: process only ~1000 articles for quick validation
make test
```

## Pipeline Stages

| Stage | Script | Description |
|---|---|---|
| 1 | `01_download.py` | Download Wikipedia dumps (~30 GB for full pipeline) |
| 2a | `02a_parse_articles.py` | Parse XML dump → article abstracts |
| 2b | `02b_parse_langlinks.py` | Parse langlinks SQL → interlanguage title mappings |
| 2b2 | `02b2_parse_redirects.py` | Parse redirect SQL → redirect title mappings |
| 2c | `02c_parse_pageviews.py` | Parse pageview data → popularity rankings |
| 3 | `03_merge.py` | Rank, tier, and merge all data |
| 4 | `04_generate_html.py` | Generate Kindle dictionary HTML + OPF |
| 5 | `05_compile.py` | Compile to `.mobi` with KindleGen |

Run individual stages: `make download`, `make parse`, `make merge`, `make html`, `make compile`.

## Profiles

| Profile | Long abstracts | Short abstracts | Total | Est. size |
|---|---|---|---|---|
| **Pocket** | 10K | 90K | 100K | ~55 MB |
| **Compact** | 50K | 200K | 250K | ~150 MB |
| **Standard** (default) | 100K | 400K | 500K | ~290 MB |
| **Large** | 100K | 900K | 1M | ~580 MB |
| **Full breadth** | 0 | 2M | 2M | ~800 MB |

See [PROFILE_ESTIMATES.md](PROFILE_ESTIMATES.md) for detailed estimates and build history.

## Custom Profiles

```bash
python 03_merge.py --profile custom --long-tier 75000 --short-tier 300000
```

## Installing on Kindle

1. Connect Kindle via USB
2. Copy the `.mobi` file to the `documents/dictionaries/` folder
3. On Kindle: Settings → Language & Dictionaries → Dictionaries
4. Select "Wikipedia Dictionary" as your default dictionary

## Orth variant filtering

Each dictionary entry can have multiple lookup forms (orth variants) sourced from Wikipedia redirects and interlanguage links. Variants are filtered to **Latin scripts only** (Unicode U+0000–U+02FF), which covers English, French, Spanish, German, Romanian, Vietnamese, and all other Latin-alphabet languages.

Non-Latin scripts (Cyrillic, Arabic, Chinese, Hebrew, Korean, Devanagari, etc.) are excluded because KindleGen's dictionary index has a hard Unicode overflow limit (E25006) when too many non-Latin characters are indexed. Japanese Kana (U+3000–U+30FF) and halfwidth forms (U+FF00–U+FF9F) are also excluded intentionally — they are technically accepted by KindleGen but katakana lookups are uncommon and omitting them keeps the index smaller.

Abstract body text is not filtered — all Unicode is preserved there.

## Data Sources

All data comes from official Wikipedia/Wikimedia dump files, updated monthly:

- Article text: `dumps.wikimedia.org/other/mediawiki_content_current/enwiki/`
- Interlanguage links: `enwiki-latest-langlinks.sql.gz`
- Redirects: `enwiki-latest-redirect.sql.gz`
- Pageviews: `dumps.wikimedia.org/other/pageview_complete/`

## License

Wikipedia content is licensed under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
The generated dictionary includes an attribution page.
