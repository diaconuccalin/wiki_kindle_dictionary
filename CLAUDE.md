# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python pipeline that converts Wikipedia dump files into Kindle-compatible `.mobi` dictionaries. Long-pressing a word on Kindle shows the Wikipedia abstract, including lookups via foreign-language titles and redirects.

## Build Commands

```bash
# Full pipeline (download → parse → merge → html → compile)
make all PROFILE=pocket          # 100K entries, ~58 MB
make all PROFILE=standard        # 500K entries (default)

# Fast compression for development
make all PROFILE=pocket FAST=1

# Test mode: ~1000 articles, quick validation
make test

# Individual stages
make download
make parse                       # runs all 4 parse stages in sequence
make merge
make html
make compile

# Custom profile
python3 03_merge.py --profile custom --long-tier 75000 --short-tier 300000
```

## Architecture

The pipeline is a strict linear sequence of numbered scripts (`01_` through `05_`), each reading from and writing to `data/` subdirectories. All scripts share a common `Config` object parsed from CLI args.

**Data flow:** Wikipedia dumps (XML/SQL/pageview) → `data/raw/` → parse stages → `data/processed/*.jsonl` → merge → `data/kindle/*.html` + OPF → KindleGen → `output/*.mobi`

### Stage details

- **01_download.py** — Downloads XML content dump, SQL dumps (page, langlinks, redirect), and pageview complete files. Supports resumable downloads via HTTP Range.
- **02a_parse_articles.py** — Streams XML dump(s) with `iterparse`, extracts lead sections via `mwparserfromhell`, writes per-file checkpoints to `data/processed/abstracts_parts/`. Phase 2 merges checkpoints using external `sort` to avoid OOM on 7M+ articles.
- **02b_parse_langlinks.py** — Parses `page.sql.gz` → `page_id_to_title.jsonl` (reused by 02b2), then streams `langlinks.sql.gz` to a temp file and sorts externally before grouping into `langlinks.jsonl`.
- **02b2_parse_redirects.py** — Parses `redirect.sql.gz` using the `page_id_to_title.jsonl` from 02b. Must run after 02b.
- **02c_parse_pageviews.py** — Parses bz2-compressed pageview complete files (`en.wikipedia` domain only), aggregates counts across months, writes `pageviews.tsv` sorted by views descending.
- **03_merge.py** — Two-pass: pass 1 scans abstract titles only to rank by pageviews; pass 2 loads only needed content. Applies tier strategy, collects orth variants (redirects + langlinks for both main titles and their redirect pages), filters non-Latin orth variants, writes `merged.jsonl`.
- **04_generate_html.py** — Generates batched XHTML content files, attribution page, cover image (from `img/<profile>.png` if present), and OPF package file.
- **05_compile.py** — Runs KindleGen with real-time streaming output. KindleGen exit code 1 = warnings (normal for dictionaries), 2 = error.

### Shared modules

- `config.py` — `Config` dataclass with all paths, profile presets, and CLI arg parsing. Every script uses `Config.from_args()`. Profile presets defined in `PROFILES` dict.
- `sql_utils.py` — Stream parser for gzipped MySQL dump files (handles escaping, NULL values). Used by 02b, 02b2.
- `wiki_utils.py` — `normalize_title()` (underscore→space, URL-decode, NFC, capitalize) and `clean_abstract_text()` (strips wikitext/HTML artifacts). Used by multiple parse stages.

### Key design decisions

- **Two-tier abstract system:** Top-ranked articles (by pageviews) get full lead sections ("long"), the rest get first-paragraph-only ("short"). Tier cutoffs are in `config.py:PROFILES`.
- **Orth variants:** Each entry has multiple lookup forms: primary English title + redirect titles + interlanguage link titles (looked up for both the main article and each of its redirect pages). Capped at `max_orth_variants=30`. Filtered to Latin-only (U+0000–U+02FF) — KindleGen's index overflows with too many non-Latin characters (E25006 error).
- **Intermediate format:** All inter-stage data uses JSONL or TSV, written atomically via `.tmp` rename.
- **Idempotent stages:** Stages skip if output already exists. Delete outputs to reprocess.
- **External sort:** Stages that process 7M+ records use `subprocess` to call the system `sort` command rather than sorting in memory to avoid OOM kills.
- **KindleGen index size:** Dictionary indexes (word lookup tables) are large relative to text — final `.mobi` is ~43% of raw HTML (with `max_orth_variants=100`). Text compresses to ~31% but indexes scale linearly with total orth count and are largely uncompressed for fast random access. More orth variants actually improve compression by giving Huffdic more shared patterns to exploit.

## Prerequisites

- Python 3.10+ (uses `X | None` union syntax)
- KindleGen binary in PATH or common locations (checked by `05_compile.py:find_kindlegen()`)
- ~40 GB disk for full pipeline downloads
- Dependencies: `mwparserfromhell`, `requests`, `Pillow`, `tqdm`

## Profiles

| Profile | Long tier | Short tier | Total | Est. .mobi |
|---|---|---|---|---|
| pocket | 10K | 90K | 100K | ~58 MB |
| compact | 50K | 200K | 250K | ~150 MB |
| standard | 100K | 400K | 500K | ~290 MB |
| large | 100K | 900K | 1M | ~580 MB |
| full_breadth | 0 | 2M | 2M | ~800 MB |

See `PROFILE_ESTIMATES.md` for actual measured sizes and build history.

## Cover images

Place a PNG in `img/<profile>.png` to use a custom cover for that profile. The `full_breadth` and `full_encyclopedia_*` profiles all map to `img/complete.png`. If no image is found, a plain white cover is generated programmatically (requires Pillow).
