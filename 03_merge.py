"""Stage 3: Rank articles by pageviews, apply tier strategy, merge all data.

Input:
  - data/processed/pageviews.tsv
  - data/processed/abstracts.jsonl
  - data/processed/langlinks.jsonl
  - data/processed/redirects.jsonl
Output:
  - data/processed/merged.jsonl
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Average bytes per entry estimates for size projection
AVG_BYTES_SHORT_5_ORTH = 700
AVG_BYTES_SHORT_15_ORTH = 1100
AVG_BYTES_LONG_5_ORTH = 3000
AVG_BYTES_LONG_15_ORTH = 3400


def load_pageviews(path: Path) -> dict[str, int]:
    """Load pageviews TSV into {title: views} dict."""
    log.info("Loading pageviews from %s ...", path)
    views = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2:
                title, count = parts[0], int(parts[1])
                views[title] = count
    log.info("Loaded %d pageview entries", len(views))
    return views


def load_langlinks(path: Path) -> dict[str, dict[str, str]]:
    """Load langlinks JSONL into {en_title: {lang: foreign_title}} dict."""
    log.info("Loading langlinks from %s ...", path)
    links = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            links[obj["en_title"]] = obj["links"]
    log.info("Loaded langlinks for %d articles", len(links))
    return links


def load_redirects(path: Path) -> dict[str, list[str]]:
    """Load redirects JSONL into {target_title: [redirect_titles]} dict."""
    log.info("Loading redirects from %s ...", path)
    redirects = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            redirects[obj["target_title"]] = obj["redirect_titles"]
    log.info("Loaded redirects for %d target articles", len(redirects))
    return redirects


def load_abstracts(path: Path) -> dict[str, dict]:
    """Load abstracts JSONL into {title: {short, long}} dict."""
    log.info("Loading abstracts from %s ...", path)
    abstracts = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            abstracts[obj["title"]] = {"short": obj["short"], "long": obj["long"]}
    log.info("Loaded %d abstracts", len(abstracts))
    return abstracts


def is_disambiguation(title: str) -> bool:
    """Check if a title is a disambiguation page."""
    return title.endswith("(disambiguation)") or title.endswith("(disambiguation page)")


def strip_disambiguation(title: str) -> str:
    """Strip (disambiguation) suffix from a title."""
    return re.sub(r"\s*\(disambiguation(?:\s+page)?\)\s*$", "", title)


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    output_path = cfg.merged_path
    if output_path.exists():
        log.info("Output already exists: %s (delete to reprocess)", output_path)
        return

    # Load all data sources
    if not cfg.pageviews_path.exists():
        log.error("Pageviews not found: %s. Run 02c_parse_pageviews.py first.", cfg.pageviews_path)
        return
    if not cfg.abstracts_path.exists():
        log.error("Abstracts not found: %s. Run 02a_parse_articles.py first.", cfg.abstracts_path)
        return

    pageviews = load_pageviews(cfg.pageviews_path)
    abstracts = load_abstracts(cfg.abstracts_path)

    langlinks = {}
    if cfg.langlinks_path.exists():
        langlinks = load_langlinks(cfg.langlinks_path)
    else:
        log.warning("Langlinks not found, proceeding without interlanguage links")

    redirects: dict[str, list[str]] = {}
    if cfg.include_redirects and cfg.redirects_path.exists():
        redirects = load_redirects(cfg.redirects_path)
    elif cfg.include_redirects:
        log.warning("Redirects not found, proceeding without redirect titles")

    # Build set of all English article titles (for collision detection)
    all_en_titles = set(abstracts.keys())
    log.info("Total articles with abstracts: %d", len(all_en_titles))

    # Rank articles by pageviews
    log.info("Ranking articles by pageviews...")
    ranked = []
    for title in abstracts:
        if is_disambiguation(title):
            continue
        views = pageviews.get(title, 0)
        ranked.append((title, views))

    ranked.sort(key=lambda x: x[1], reverse=True)
    log.info("Ranked %d articles (excluding disambiguation pages)", len(ranked))

    # Apply tier thresholds
    long_tier = cfg.long_tier
    total_limit = cfg.total_entries  # None for full encyclopedia

    entries = []
    long_count = 0
    short_count = 0
    total_orth = 0
    skipped_collisions = 0
    estimated_bytes = 0

    for rank, (title, views) in enumerate(tqdm(ranked, desc="Merging", unit=" articles")):
        if total_limit is not None and (long_count + short_count) >= total_limit:
            break

        art = abstracts[title]

        # Determine tier
        if rank < long_tier:
            tier = "long"
            abstract = art["long"]
            long_count += 1
        else:
            tier = "short"
            abstract = art["short"]
            # Apply max length for short abstracts
            if cfg.max_short_abstract_length and len(abstract) > cfg.max_short_abstract_length:
                abstract = abstract[:cfg.max_short_abstract_length].rsplit(" ", 1)[0] + "..."
            short_count += 1

        # Collect orth variants
        orth_variants = []

        # Add redirect titles (high value, add first)
        if title in redirects:
            for redir in redirects[title]:
                # Skip if collision with a different English article
                if redir in all_en_titles and redir != title:
                    skipped_collisions += 1
                    continue
                # Strip disambiguation suffix
                cleaned = strip_disambiguation(redir)
                if cleaned.lower() != title.lower():
                    orth_variants.append(cleaned)

        # Add interlanguage link titles
        if title in langlinks:
            for lang, foreign_title in langlinks[title].items():
                # Skip if collision with a different English article
                if foreign_title in all_en_titles and foreign_title != title:
                    skipped_collisions += 1
                    continue
                if foreign_title.lower() != title.lower():
                    orth_variants.append(foreign_title)

        # Deduplicate and cap
        seen = {title.lower()}
        unique_orth = []
        for v in orth_variants:
            key = v.lower()
            if key not in seen:
                seen.add(key)
                unique_orth.append(v)
        # Cap at max (minus 1 for the primary English title)
        unique_orth = unique_orth[:cfg.max_orth_variants - 1]
        total_orth += len(unique_orth)

        # Estimate size
        n_orth = 1 + len(unique_orth)
        if tier == "long":
            est = AVG_BYTES_LONG_5_ORTH if n_orth <= 5 else AVG_BYTES_LONG_15_ORTH
        else:
            est = AVG_BYTES_SHORT_5_ORTH if n_orth <= 5 else AVG_BYTES_SHORT_15_ORTH
        estimated_bytes += est

        entry = {
            "en_title": title,
            "tier": tier,
            "abstract": abstract,
            "orth_variants": unique_orth,
            "pageviews": views,
        }
        entries.append(entry)

    # Log statistics
    log.info("--- Merge Statistics ---")
    log.info("Long tier entries: %d", long_count)
    log.info("Short tier entries: %d", short_count)
    log.info("Total entries: %d", long_count + short_count)
    log.info("Total orth variants: %d (avg %.1f per entry)",
             total_orth, total_orth / max(1, len(entries)))
    log.info("Skipped title collisions: %d", skipped_collisions)
    log.info("Estimated raw HTML size: %.1f MB", estimated_bytes / 1024 / 1024)
    log.info("Estimated .mobi size (with -c2 -dont_append_source): %.1f MB",
             estimated_bytes * 0.30 / 1024 / 1024)

    # Write output
    log.info("Writing %d entries to %s ...", len(entries), output_path)
    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    tmp_path.rename(output_path)

    log.info("Merge complete!")


if __name__ == "__main__":
    main()
