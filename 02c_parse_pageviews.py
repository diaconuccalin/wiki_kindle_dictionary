"""Stage 2c: Parse Wikipedia pageview dump(s) into aggregated pageview counts.

Input: data/raw/pageviews-*.bz2 (monthly pageview complete files)
Output: data/processed/pageviews.tsv (title<TAB>views, sorted by views descending)
"""

import bz2
import glob
import logging
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from config import Config
from wiki_utils import normalize_title

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def parse_pageview_file(filepath: Path, counts: dict[str, int]):
    """Parse a single pageview complete file and accumulate counts.

    Format: domain_code page_title count_views total_response_size
    We filter for domain_code == 'en.wikipedia' (article namespace).
    """
    log.info("Parsing %s ...", filepath.name)
    opener = bz2.open if filepath.suffix == ".bz2" else open

    with opener(filepath, "rt", encoding="utf-8", errors="replace") as f:
        for line in tqdm(f, desc=filepath.name, unit=" lines", mininterval=5):
            parts = line.rstrip("\n").split(" ")
            if len(parts) < 5:
                continue

            domain = parts[0]
            # Filter to English Wikipedia articles only
            if domain != "en.wikipedia":
                continue

            title = parts[1]
            # parts[2] = page_id, parts[3] = access_method, parts[4] = views
            try:
                views = int(parts[4])
            except ValueError:
                continue

            # Skip namespace-prefixed pages (non-article)
            if ":" in title:
                prefix = title.split(":")[0]
                if prefix in ("User", "Talk", "Wikipedia", "Template", "File",
                              "MediaWiki", "Help", "Category", "Portal", "Draft",
                              "Module", "Special", "User_talk", "Wikipedia_talk",
                              "Template_talk", "File_talk", "Category_talk",
                              "Book", "TimedText", "Gadget", "Gadget_definition"):
                    continue

            # Skip main page
            if title in ("-", "Main_Page"):
                continue

            normalized = normalize_title(title)
            if normalized:
                counts[normalized] += views


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    output_path = cfg.pageviews_path
    if output_path.exists():
        log.info("Output already exists: %s (delete to reprocess)", output_path)
        return

    # Find pageview files
    raw_dir = cfg.raw_dir
    pv_files = sorted(raw_dir.glob("pageviews-*"))
    if not pv_files:
        log.error("No pageview files found in %s", raw_dir)
        log.error("Expected files matching: pageviews-*.bz2")
        return

    log.info("Found %d pageview file(s)", len(pv_files))

    # Aggregate counts across all files
    counts: dict[str, int] = defaultdict(int)
    for pv_file in pv_files:
        parse_pageview_file(pv_file, counts)

    log.info("Total unique titles with pageviews: %d", len(counts))

    # Sort by views descending and write
    log.info("Sorting by views...")
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for title, views in sorted_items:
            f.write(f"{title}\t{views}\n")
    tmp_path.rename(output_path)

    log.info("Wrote %d entries to %s", len(sorted_items), output_path)
    if sorted_items:
        log.info("Top 10 by pageviews:")
        for title, views in sorted_items[:10]:
            log.info("  %s: %d views", title, views)


if __name__ == "__main__":
    main()
