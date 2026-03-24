# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python pipeline that converts Wikipedia dump files into Kindle-compatible `.mobi` dictionaries. Long-pressing a word on Kindle shows the Wikipedia abstract, including lookups via foreign-language titles and redirects.

## Build Commands

```bash
# Full pipeline (download → parse → merge → html → compile)
make all PROFILE=pocket          # 100K entries, ~30 MB
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

**Key design decisions:**
- **Two-tier abstract system:** Top articles get full lead sections ("long"), the rest get first-paragraph-only ("short"). Tier cutoffs are controlled by profile presets in `config.py:PROFILES`.
- **Orth variants:** Each dictionary entry can have multiple lookup forms (redirects + interlanguage titles), capped at `max_orth_variants`. Collisions with existing English titles are skipped.
- **Intermediate format:** All inter-stage data uses JSONL (one JSON object per line) or TSV, written atomically via `.tmp` rename.
- **Idempotent stages:** Most stages skip if output already exists. Delete outputs to reprocess.

**Shared modules:**
- `config.py` — `Config` dataclass with all paths, profile presets, and CLI arg parsing. Every script uses `Config.from_args()`.
- `sql_utils.py` — Stream parser for gzipped MySQL dump files (handles escaping, NULL values). Used by langlinks and redirects parsers.
- `wiki_utils.py` — Title normalization (underscore→space, URL-decode, NFC, capitalize) and abstract text cleanup (strip wikitext/HTML artifacts via regex).

## Prerequisites

- Python 3.10+ (uses `X | None` union syntax)
- KindleGen binary in PATH or common locations (checked by `05_compile.py:find_kindlegen()`)
- ~40 GB disk for full pipeline downloads
- Dependencies: `mwparserfromhell`, `requests`, `Pillow`, `tqdm`
