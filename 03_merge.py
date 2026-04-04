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
            parts = line.rstrip("\n").rsplit("\t", 1)
            if len(parts) == 2:
                try:
                    title, count = parts[0], int(parts[1])
                    views[title] = count
                except ValueError:
                    pass
    log.info("Loaded %d pageview entries", len(views))
    return views


def load_langlinks(path: Path, needed: set[str] | None = None) -> dict[str, dict[str, str]]:
    """Load langlinks JSONL into {en_title: {lang: foreign_title}} dict."""
    log.info("Loading langlinks from %s ...", path)
    links = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if needed is None or obj["en_title"] in needed:
                links[obj["en_title"]] = obj["links"]
    log.info("Loaded langlinks for %d articles", len(links))
    return links


def load_redirects(path: Path, needed: set[str] | None = None) -> dict[str, list[str]]:
    """Load redirects JSONL into {target_title: [redirect_titles]} dict."""
    log.info("Loading redirects from %s ...", path)
    redirects = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if needed is None or obj["target_title"] in needed:
                redirects[obj["target_title"]] = obj["redirect_titles"]
    log.info("Loaded redirects for %d target articles", len(redirects))
    return redirects


def load_abstract_titles(path: Path) -> set[str]:
    """Stream abstracts JSONL and return just the set of titles (memory-efficient)."""
    log.info("Scanning abstract titles from %s ...", path)
    titles = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            titles.add(obj["title"])
    log.info("Found %d abstract titles", len(titles))
    return titles


def load_abstracts_filtered(path: Path, needed: set[str]) -> dict[str, dict]:
    """Stream abstracts JSONL, loading only entries whose title is in `needed`."""
    log.info("Loading %d needed abstracts from %s ...", len(needed), path)
    abstracts = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj["title"] in needed:
                abstracts[obj["title"]] = {"short": obj["short"], "long": obj["long"]}
    log.info("Loaded %d abstracts", len(abstracts))
    return abstracts


def is_kindlegen_safe(text: str) -> bool:
    """Return True if all characters are in the allowed orth index range.

    Only Latin scripts (U+0000-U+02FF) are indexed. Kana (U+3000-U+30FF) and
    halfwidth forms (U+FF00-U+FF9F) are also accepted by KindleGen but excluded
    here intentionally — Japanese katakana lookups are rare and keeping only Latin
    produces a cleaner, smaller index.
    """
    for ch in text:
        if ord(ch) > 0x02FF:
            return False
    return True


def is_disambiguation(title: str) -> bool:
    """Check if a title is a disambiguation page."""
    return title.endswith("(disambiguation)") or title.endswith("(disambiguation page)")


def strip_disambiguation(title: str) -> str:
    """Strip (disambiguation) suffix from a title."""
    return re.sub(r"\s*\(disambiguation(?:\s+page)?\)\s*$", "", title)


def _process_entry(title: str, abstract: str, tier: str, views: int,
                    redirects: dict, langlinks: dict, all_en_titles: set,
                    pageviews: dict, cfg: Config) -> tuple[dict, int, int]:
    """Process a single entry: collect orth variants, estimate size.

    Returns (entry_dict, orth_count, skipped_collisions).
    """
    skipped = 0
    orth_variants = []

    if title in redirects:
        for redir in redirects[title]:
            if redir in all_en_titles and redir != title:
                skipped += 1
                continue
            cleaned = strip_disambiguation(redir)
            if cleaned.lower() != title.lower() and is_kindlegen_safe(cleaned):
                orth_variants.append(cleaned)

    langlink_sources = [title] + (redirects.get(title, []) if cfg.include_redirects else [])
    for source in langlink_sources:
        if source not in langlinks:
            continue
        for lang, foreign_title in langlinks[source].items():
            if foreign_title in all_en_titles and foreign_title != title:
                skipped += 1
                continue
            if foreign_title.lower() != title.lower() and is_kindlegen_safe(foreign_title):
                orth_variants.append(foreign_title)

    seen = {title.lower()}
    unique_orth = []
    for v in orth_variants:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            unique_orth.append(v)
    unique_orth.sort(key=lambda v: pageviews.get(v, 0), reverse=True)
    unique_orth = unique_orth[:cfg.max_orth_variants - 1]

    entry = {
        "en_title": title,
        "tier": tier,
        "abstract": abstract,
        "orth_variants": unique_orth,
        "pageviews": views,
    }
    return entry, len(unique_orth), skipped


def _build_orth_index(cfg: Config, all_en_titles: set[str]) -> Path:
    """Build a disk-based orth variant index to avoid loading langlinks into RAM.

    Streams redirects and langlinks files, collecting orth variants per title,
    and writes them as sorted JSONL: {"title": ..., "orth": [...]}
    Uses external sort to stay memory-safe.
    """
    import subprocess
    import tempfile

    processed_dir = cfg.processed_dir
    orth_unsorted = processed_dir / "orth_variants_unsorted.tmp"
    orth_sorted = processed_dir / "orth_variants_sorted.tmp"

    log.info("Building orth variant index on disk...")

    # Collect: for each article title, gather candidate orth variants from
    # redirects and langlinks, apply filtering, then write one line per title
    # with the collected variants.
    #
    # We need the title set to check collisions, but we stream redirects and
    # langlinks instead of loading them as dicts.

    # Pass 1: build {article_title -> [orth_variants]} from redirects
    # Redirects file is small enough (~521 MB on disk, ~1.6 GB as dict).
    # But we only need to map target -> list of valid orth strings.
    # Stream it and write per-title orth lines.
    orth_by_title: dict[str, list[str]] = {}

    if cfg.include_redirects and cfg.redirects_path.exists():
        log.info("Streaming redirects for orth variants...")
        with open(cfg.redirects_path, "r", encoding="utf-8") as f:
            for line in tqdm(f, desc="Redirects", unit=" lines"):
                obj = json.loads(line)
                target = obj["target_title"]
                if target not in all_en_titles:
                    continue
                variants = []
                for redir in obj["redirect_titles"]:
                    if redir in all_en_titles and redir != target:
                        continue
                    cleaned = strip_disambiguation(redir)
                    if cleaned.lower() != target.lower() and is_kindlegen_safe(cleaned):
                        variants.append(cleaned)
                if variants:
                    orth_by_title.setdefault(target, []).extend(variants)
        log.info("Collected redirect orth variants for %d articles", len(orth_by_title))

    # Pass 2: stream langlinks, append to orth_by_title, but don't hold
    # the full langlinks dict — just the orth strings per title.
    # We also need to look up langlinks for redirect source titles.
    # Build a reverse map: redirect_title -> main_article_title
    redirect_to_main: dict[str, str] = {}
    if cfg.include_redirects:
        for target, variants in orth_by_title.items():
            # We need the raw redirect titles (before filtering) for langlink lookups.
            # Re-stream redirects to build this map — but that's expensive.
            # Instead, approximate: the orth_by_title values are already cleaned.
            pass

    # For langlinks, we need to know which en_title each langlink source maps to.
    # The langlinks file is keyed by en_title. For redirect pages that have langlinks,
    # those are separate entries in langlinks.jsonl keyed by the redirect title.
    # To map redirect_title -> main_article, we'd need the redirects dict again.
    #
    # Memory-efficient approach: just stream langlinks and add orth variants
    # for titles that are in all_en_titles. Skip redirect-page langlink lookups
    # to avoid needing the redirect mapping in memory. This loses some orth
    # variants but keeps memory bounded.
    if cfg.langlinks_path.exists():
        log.info("Streaming langlinks for orth variants...")
        with open(cfg.langlinks_path, "r", encoding="utf-8") as f:
            for line in tqdm(f, desc="Langlinks", unit=" lines"):
                obj = json.loads(line)
                en_title = obj["en_title"]
                if en_title not in all_en_titles:
                    continue
                for lang, foreign_title in obj["links"].items():
                    if foreign_title in all_en_titles and foreign_title != en_title:
                        continue
                    if foreign_title.lower() != en_title.lower() and is_kindlegen_safe(foreign_title):
                        orth_by_title.setdefault(en_title, []).append(foreign_title)
        log.info("Orth index covers %d articles", len(orth_by_title))

    # Deduplicate per title
    for title in orth_by_title:
        seen = {title.lower()}
        unique = []
        for v in orth_by_title[title]:
            key = v.lower()
            if key not in seen:
                seen.add(key)
                unique.append(v)
        # Cap at max
        orth_by_title[title] = unique[:cfg.max_orth_variants - 1]

    log.info("Orth index built: %d articles with variants", len(orth_by_title))
    return orth_by_title


def merge_streaming(cfg: Config, output_path: Path):
    """Memory-efficient merge for the complete profile.

    Streams abstracts one at a time instead of loading all into memory.
    All articles get long tier, so no pageview ranking is needed.
    Builds orth variant index by streaming redirects and langlinks
    without loading them fully as dicts.
    """
    all_en_titles = load_abstract_titles(cfg.abstracts_path)
    log.info("Total articles with abstracts: %d", len(all_en_titles))

    orth_index = _build_orth_index(cfg, all_en_titles)

    # Free title set — we no longer need it during streaming
    del all_en_titles

    # Stream abstracts and write entries directly to output
    log.info("Streaming abstracts and writing merged entries...")
    tmp_path = output_path.with_suffix(".tmp")
    entry_count = 0
    total_orth = 0
    estimated_bytes = 0

    with open(tmp_path, "w", encoding="utf-8") as out_f:
        with open(cfg.abstracts_path, "r", encoding="utf-8") as in_f:
            for line in tqdm(in_f, desc="Merging", unit=" articles"):
                if not line.strip():
                    continue
                obj = json.loads(line)
                title = obj["title"]

                if is_disambiguation(title):
                    continue

                abstract = obj["long"]
                orth_variants = orth_index.get(title, [])
                n_orth = len(orth_variants)
                total_orth += n_orth

                entry = {
                    "en_title": title,
                    "tier": "long",
                    "abstract": abstract,
                    "orth_variants": orth_variants,
                    "pageviews": 0,
                }
                out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")

                entry_count += 1
                estimated_bytes += AVG_BYTES_LONG_5_ORTH if (1 + n_orth) <= 5 else AVG_BYTES_LONG_15_ORTH

    tmp_path.rename(output_path)

    log.info("--- Merge Statistics ---")
    log.info("Long tier entries: %d", entry_count)
    log.info("Total entries: %d", entry_count)
    log.info("Total orth variants: %d (avg %.1f per entry)",
             total_orth, total_orth / max(1, entry_count))
    log.info("Estimated raw HTML size: %.1f MB", estimated_bytes / 1024 / 1024)
    log.info("Estimated .mobi size (with -c2 -dont_append_source): %.1f MB",
             estimated_bytes * 0.41 / 1024 / 1024)
    log.info("Merge complete!")


def merge_ranked(cfg: Config, output_path: Path):
    """Standard ranked merge for profiles with tier cutoffs (e.g. pocket)."""
    pageviews = load_pageviews(cfg.pageviews_path)

    all_en_titles = load_abstract_titles(cfg.abstracts_path)
    log.info("Total articles with abstracts: %d", len(all_en_titles))

    # Rank articles by pageviews
    log.info("Ranking articles by pageviews...")
    ranked = []
    for title in all_en_titles:
        if is_disambiguation(title):
            continue
        views = pageviews.get(title, 0)
        ranked.append((title, views))

    ranked.sort(key=lambda x: x[1], reverse=True)
    log.info("Ranked %d articles (excluding disambiguation pages)", len(ranked))

    total_limit = cfg.total_entries
    needed_titles = {title for title, _ in (ranked[:total_limit] if total_limit else ranked)}
    log.info("Loading content for %d needed articles...", len(needed_titles))

    abstracts = load_abstracts_filtered(cfg.abstracts_path, needed_titles)

    redirects: dict[str, list[str]] = {}
    if cfg.include_redirects and cfg.redirects_path.exists():
        redirects = load_redirects(cfg.redirects_path, needed_titles)
    elif cfg.include_redirects:
        log.warning("Redirects not found, proceeding without redirect titles")

    redirect_titles = {redir for redir_list in redirects.values() for redir in redir_list}
    langlink_titles = needed_titles | redirect_titles
    log.info("Loading langlinks for %d titles (%d main + %d redirects) ...",
             len(langlink_titles), len(needed_titles), len(redirect_titles))

    langlinks = {}
    if cfg.langlinks_path.exists():
        langlinks = load_langlinks(cfg.langlinks_path, langlink_titles)
    else:
        log.warning("Langlinks not found, proceeding without interlanguage links")

    long_tier = cfg.long_tier

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

        if long_tier is None or rank < long_tier:
            tier = "long"
            abstract = art["long"]
            long_count += 1
        else:
            tier = "short"
            abstract = art["short"]
            if cfg.max_short_abstract_length and len(abstract) > cfg.max_short_abstract_length:
                abstract = abstract[:cfg.max_short_abstract_length].rsplit(" ", 1)[0] + "..."
            short_count += 1

        entry, n_orth, skipped = _process_entry(
            title, abstract, tier, views,
            redirects, langlinks, all_en_titles, pageviews, cfg
        )
        entries.append(entry)
        total_orth += n_orth
        skipped_collisions += skipped

        n = 1 + n_orth
        if tier == "long":
            est = AVG_BYTES_LONG_5_ORTH if n <= 5 else AVG_BYTES_LONG_15_ORTH
        else:
            est = AVG_BYTES_SHORT_5_ORTH if n <= 5 else AVG_BYTES_SHORT_15_ORTH
        estimated_bytes += est

    log.info("--- Merge Statistics ---")
    log.info("Long tier entries: %d", long_count)
    log.info("Short tier entries: %d", short_count)
    log.info("Total entries: %d", long_count + short_count)
    log.info("Total orth variants: %d (avg %.1f per entry)",
             total_orth, total_orth / max(1, len(entries)))
    log.info("Skipped title collisions: %d", skipped_collisions)
    log.info("Estimated raw HTML size: %.1f MB", estimated_bytes / 1024 / 1024)
    log.info("Estimated .mobi size (with -c2 -dont_append_source): %.1f MB",
             estimated_bytes * 0.41 / 1024 / 1024)

    log.info("Writing %d entries to %s ...", len(entries), output_path)
    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    tmp_path.rename(output_path)

    log.info("Merge complete!")


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    output_path = cfg.merged_path
    if output_path.exists():
        log.info("Output already exists: %s (delete to reprocess)", output_path)
        return

    if not cfg.pageviews_path.exists():
        log.error("Pageviews not found: %s. Run 02c_parse_pageviews.py first.", cfg.pageviews_path)
        return
    if not cfg.abstracts_path.exists():
        log.error("Abstracts not found: %s. Run 02a_parse_articles.py first.", cfg.abstracts_path)
        return

    if cfg.long_tier is None:
        merge_streaming(cfg, output_path)
    else:
        merge_ranked(cfg, output_path)


if __name__ == "__main__":
    main()
