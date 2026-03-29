"""Stage 2b2: Parse redirect SQL dump into redirect title mappings.

Input:
  - data/raw/enwiki-latest-redirect.sql.gz
  - data/processed/page_id_to_title.jsonl (from 02b_parse_langlinks.py)
Output:
  - data/processed/redirects.jsonl
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from config import Config
from sql_utils import parse_sql_dump
from wiki_utils import normalize_title

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_page_id_map(path: Path) -> dict[int, str]:
    """Load page_id → title mapping from JSONL."""
    page_map = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            page_map[obj["page_id"]] = obj["title"]
    return page_map


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    output_path = cfg.redirects_path
    if output_path.exists():
        log.info("Output already exists: %s (delete to reprocess)", output_path)
        return

    redirect_sql = cfg.raw_dir / "enwiki-latest-redirect.sql.gz"
    page_id_path = cfg.page_id_to_title_path

    if not redirect_sql.exists():
        log.error("Redirect SQL dump not found: %s", redirect_sql)
        return
    if not page_id_path.exists():
        log.error("Page ID map not found: %s. Run 02b_parse_langlinks.py first.", page_id_path)
        return

    # Load page_id → title map (for source page titles)
    log.info("Loading page_id map...")
    page_map = load_page_id_map(page_id_path)
    log.info("Loaded %d page_id mappings", len(page_map))

    # Parse redirect dump
    # redirect table schema: (rd_from, rd_namespace, rd_title, rd_interwiki, rd_fragment)
    log.info("Parsing redirects from %s ...", redirect_sql.name)
    redirects: dict[str, list[str]] = defaultdict(list)
    count = 0

    for row in tqdm(parse_sql_dump(str(redirect_sql), "redirect"),
                    desc="redirect.sql", unit=" rows", mininterval=5):
        if len(row) < 3:
            continue
        try:
            source_page_id = int(row[0])
            target_namespace = int(row[1])
        except (ValueError, TypeError):
            continue

        # Only article namespace redirects
        if target_namespace != 0:
            continue

        target_title = normalize_title(row[2])
        source_title = page_map.get(source_page_id)

        if not source_title or not target_title:
            continue
        if source_title == target_title:
            continue

        redirects[target_title].append(source_title)
        count += 1

    log.info("Parsed %d redirects pointing to %d unique targets", count, len(redirects))

    # Write output sorted by target title
    log.info("Writing redirects to %s ...", output_path)
    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for target in sorted(redirects.keys()):
            obj = {
                "target_title": target,
                "redirect_titles": redirects[target]
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    tmp_path.rename(output_path)
    log.info("Wrote redirect mappings for %d target articles", len(redirects))


if __name__ == "__main__":
    main()
