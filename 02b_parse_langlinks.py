"""Stage 2b: Parse langlinks and page SQL dumps into interlanguage link mappings.

Input:
  - data/raw/enwiki-latest-page.sql.gz
  - data/raw/enwiki-latest-langlinks.sql.gz
Output:
  - data/processed/page_id_to_title.jsonl (side output, reused by 02b2)
  - data/processed/langlinks.jsonl
"""

import json
import logging
import subprocess
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from config import Config
from sql_utils import parse_sql_dump
from wiki_utils import normalize_title

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def parse_page_table(page_sql_path: Path) -> dict[int, str]:
    """Parse enwiki-latest-page.sql.gz → {page_id: title} for namespace 0."""
    log.info("Parsing page table from %s ...", page_sql_path.name)
    page_map = {}

    for row in tqdm(parse_sql_dump(str(page_sql_path), "page"),
                    desc="page.sql", unit=" rows", mininterval=5):
        # page table schema: (page_id, page_namespace, page_title, ...)
        if len(row) < 3:
            continue
        try:
            page_id = int(row[0])
            namespace = int(row[1])
        except (ValueError, TypeError):
            continue

        if namespace != 0:  # articles only
            continue

        title = row[2]
        if title:
            page_map[page_id] = normalize_title(title)

    log.info("Loaded %d page_id → title mappings (namespace 0)", len(page_map))
    return page_map


def save_page_id_map(page_map: dict[int, str], output_path: Path):
    """Save page_id → title mapping as JSONL for reuse by other scripts."""
    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for page_id, title in page_map.items():
            f.write(json.dumps({"page_id": page_id, "title": title},
                               ensure_ascii=False) + "\n")
    tmp_path.rename(output_path)
    log.info("Saved page_id map to %s", output_path)


def parse_langlinks_streaming(langlinks_path: Path, page_map: dict[int, str],
                              cfg: Config, tmp_path: Path) -> int:
    """Stream langlinks rows to a temp file as `en_title\\tlang\\tforeign_title`.

    Returns number of rows written.
    """
    log.info("Parsing langlinks from %s ...", langlinks_path.name)
    exclude = set(cfg.exclude_languages)
    count = 0

    with open(tmp_path, "w", encoding="utf-8") as out:
        for row in tqdm(parse_sql_dump(str(langlinks_path), "langlinks"),
                        desc="langlinks.sql", unit=" rows", mininterval=5):
            # langlinks schema: (ll_from, ll_lang, ll_title)
            if len(row) < 3:
                continue
            try:
                page_id = int(row[0])
            except (ValueError, TypeError):
                continue

            lang = row[1]
            foreign_title = row[2]

            if not lang or not foreign_title:
                continue
            if lang in exclude:
                continue
            if cfg.include_languages and lang not in cfg.include_languages:
                continue

            en_title = page_map.get(page_id)
            if en_title is None:
                continue

            out.write(f"{en_title}\t{lang}\t{foreign_title}\n")
            count += 1

    log.info("Wrote %d langlink rows to temp file", count)
    return count


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    page_sql = cfg.raw_dir / "enwiki-latest-page.sql.gz"
    langlinks_sql = cfg.raw_dir / "enwiki-latest-langlinks.sql.gz"

    if not page_sql.exists():
        log.error("Page SQL dump not found: %s", page_sql)
        return
    if not langlinks_sql.exists():
        log.error("Langlinks SQL dump not found: %s", langlinks_sql)
        return

    # Step 1: Parse page table
    page_id_path = cfg.page_id_to_title_path
    if page_id_path.exists():
        log.info("Loading cached page_id map from %s", page_id_path)
        page_map = {}
        with open(page_id_path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                page_map[obj["page_id"]] = obj["title"]
        log.info("Loaded %d page_id mappings", len(page_map))
    else:
        page_map = parse_page_table(page_sql)
        save_page_id_map(page_map, page_id_path)

    # Step 2: Parse langlinks
    output_path = cfg.langlinks_path
    if output_path.exists():
        log.info("Output already exists: %s (delete to reprocess)", output_path)
        return

    # Stream rows to temp file, sort externally, then group into final JSONL
    rows_tmp = output_path.with_suffix(".rows.tmp")
    parse_langlinks_streaming(langlinks_sql, page_map, cfg, rows_tmp)

    total_rows = int(subprocess.check_output(["wc", "-l", str(rows_tmp)]).split()[0])
    log.info("Sorting %d langlink rows by en_title ...", total_rows)
    import time
    sorted_tmp = output_path.with_suffix(".sorted.tmp")
    sort_proc = subprocess.Popen(["sort", "-t\t", "-k1,1", str(rows_tmp), "-o", str(sorted_tmp)])
    t0 = time.time()
    while sort_proc.poll() is None:
        time.sleep(30)
        if sort_proc.poll() is None:
            log.info("  sort in progress... %.0f min elapsed", (time.time() - t0) / 60)
    if sort_proc.returncode != 0:
        raise subprocess.CalledProcessError(sort_proc.returncode, "sort")
    log.info("  sort complete in %.0f min", (time.time() - t0) / 60)
    rows_tmp.unlink()

    log.info("Grouping and writing %s ...", output_path)
    tmp_path = output_path.with_suffix(".tmp")
    n_articles = 0
    with open(sorted_tmp, "r", encoding="utf-8") as inp, \
         open(tmp_path, "w", encoding="utf-8") as out:
        current_title = None
        current_links: dict[str, str] = {}
        for line in tqdm(inp, total=total_rows, desc="group", unit=" rows", mininterval=5):
            en_title, lang, foreign_title = line.rstrip("\n").split("\t", 2)
            if en_title != current_title:
                if current_title is not None:
                    out.write(json.dumps({"en_title": current_title, "links": current_links},
                                         ensure_ascii=False) + "\n")
                    n_articles += 1
                current_title = en_title
                current_links = {}
            current_links[lang] = foreign_title
        if current_title is not None:
            out.write(json.dumps({"en_title": current_title, "links": current_links},
                                  ensure_ascii=False) + "\n")
            n_articles += 1
    sorted_tmp.unlink()
    tmp_path.rename(output_path)
    log.info("Wrote langlinks for %d articles", n_articles)


if __name__ == "__main__":
    main()
