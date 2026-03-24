"""Stage 1: Download all required datasets from Wikipedia/Wikimedia dumps.

Downloads:
  - enwiki content dump (XML, for article text)
  - enwiki langlinks SQL dump
  - enwiki page SQL dump
  - enwiki redirect SQL dump
  - Wikipedia pageview data (1-3 months)

All files saved to data/raw/.
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from tqdm import tqdm

from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CONTENT_DUMP_BASE = "https://dumps.wikimedia.org/other/mediawiki_content_current/enwiki/"
LATEST_DUMPS_BASE = "https://dumps.wikimedia.org/enwiki/latest/"
PAGEVIEW_BASE = "https://dumps.wikimedia.org/other/pageview_complete/"
PAGEVIEW_MONTHLY_BASE = "https://dumps.wikimedia.org/other/pageview_complete/monthly/"

# SQL dumps to download (relatively small, always download all)
SQL_DUMPS = [
    "enwiki-latest-langlinks.sql.gz",
    "enwiki-latest-page.sql.gz",
    "enwiki-latest-redirect.sql.gz",
]


def download_file(url: str, dest: Path, desc: str | None = None, max_retries: int = 10):
    """Download a file with resume support, retry on failure, and progress bar."""
    if desc is None:
        desc = dest.name

    for attempt in range(1, max_retries + 1):
        try:
            success = _download_attempt(url, dest, desc)
            if success:
                return True
            # Non-retryable failure (e.g. 404)
            return False
        except (requests.RequestException, ConnectionError, TimeoutError) as e:
            log.warning("  %s: attempt %d/%d failed: %s", desc, attempt, max_retries, e)
            if attempt < max_retries:
                log.info("  Retrying (will resume from %d bytes)...",
                         dest.stat().st_size if dest.exists() else 0)
            else:
                log.error("  %s: all %d attempts failed", desc, max_retries)
                return False


def _download_attempt(url: str, dest: Path, desc: str) -> bool:
    """Single download attempt with resume support."""
    existing_size = dest.stat().st_size if dest.exists() else 0

    headers = {}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    resp = requests.get(url, headers=headers, stream=True, timeout=(15, 300))

    if resp.status_code == 416:
        log.info("  %s already complete (%d bytes)", desc, existing_size)
        return True

    if resp.status_code not in (200, 206):
        log.error("  HTTP %d for %s", resp.status_code, url)
        return False

    if resp.status_code == 206:
        content_range = resp.headers.get("Content-Range", "")
        total = int(content_range.split("/")[-1]) if "/" in content_range else None
        mode = "ab"
    else:
        total = int(resp.headers.get("Content-Length", 0)) or None
        if existing_size > 0 and total and existing_size >= total:
            log.info("  %s already complete (%d bytes)", desc, existing_size)
            return True
        existing_size = 0
        mode = "wb"

    if total:
        remaining = total - existing_size
        log.info("  Downloading %s (%.1f MB remaining of %.1f MB)",
                 desc, remaining / 1024 / 1024, total / 1024 / 1024)

    with open(dest, mode) as f:
        with tqdm(total=total, initial=existing_size, unit="B",
                  unit_scale=True, desc=desc, mininterval=2) as pbar:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                pbar.update(len(chunk))

    return True


def discover_content_dump_urls() -> list[str]:
    """Scrape the content dump index to find XML part file URLs."""
    log.info("Discovering content dump files...")

    # The content dump directory has monthly subdirectories
    try:
        resp = requests.get(CONTENT_DUMP_BASE, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to access content dump index: %s", e)
        return []

    # Find the latest month directory (format: YYYY-MM-DD)
    month_dirs = re.findall(r'href="(\d{4}-\d{2}-\d{2})/"', resp.text)
    if not month_dirs:
        log.error("No monthly directories found at %s", CONTENT_DUMP_BASE)
        return []

    latest_month = sorted(month_dirs)[-1]
    # Files are under {date}/xml/bzip2/
    files_url = f"{CONTENT_DUMP_BASE}{latest_month}/xml/bzip2/"
    log.info("Latest content dump: %s", latest_month)

    # Get file listing
    try:
        resp = requests.get(files_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to access %s: %s", files_url, e)
        return []

    # Find XML bz2 files: enwiki-YYYY-MM-DD-p<start>p<end>.xml.bz2
    files = re.findall(r'href="(enwiki[^"]*\.xml\.bz2)"', resp.text)

    urls = [f"{files_url}{f}" for f in files]
    log.info("Found %d content dump files", len(urls))
    return urls


def discover_pageview_urls(months: int, test_mode: bool = False) -> list[str]:
    """Build URLs for pageview data.

    Uses monthly pre-aggregated files (~5 GB each) instead of daily files
    (~700 MB × 30 = ~21 GB per month). Same data, ~4x less download.

    In test mode, grab 1 daily file (~700 MB) for speed.
    """
    now = datetime.now()

    if test_mode:
        # Just one recent daily file
        dt = now - timedelta(days=3)
        year = dt.strftime("%Y")
        month = dt.strftime("%m")
        day = dt.strftime("%d")
        year_month = f"{year}-{month}"
        fname = f"pageviews-{year}{month}{day}-user.bz2"
        url = f"{PAGEVIEW_BASE}{year}/{year_month}/{fname}"
        return [url]

    # Use monthly pre-aggregated files
    urls = []
    for i in range(1, months + 1):
        dt = now - timedelta(days=30 * i)
        year = dt.strftime("%Y")
        month = dt.strftime("%m")
        year_month = f"{year}-{month}"
        fname = f"pageviews-{year}{month}-user.bz2"
        url = f"{PAGEVIEW_MONTHLY_BASE}{year}/{year_month}/{fname}"
        urls.append(url)

    return urls


def estimate_disk_space(content_urls: list[str], sql_dumps: list[str],
                        pv_urls: list[str], test_mode: bool = False) -> float:
    """Estimate total download size in GB."""
    # Rough estimates
    content_gb = len(content_urls) * 2.5  # ~2.5 GB per part file
    sql_gb = 2.0  # page + langlinks + redirect total ~2 GB
    # Monthly files ~5.5 GB each, daily files ~0.7 GB each
    pv_gb = len(pv_urls) * (0.7 if test_mode else 5.5)
    total = content_gb + sql_gb + pv_gb
    return total


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    raw_dir = cfg.raw_dir

    # 1. Discover and download content dump
    content_urls = discover_content_dump_urls()
    if not content_urls:
        log.error("Could not discover content dump URLs")
        return

    # In test mode, only download the first part file
    if cfg.test_mode:
        log.info("Test mode: downloading only first content dump part")
        content_urls = content_urls[:1]

    # 2. Build pageview URLs
    pv_months = 1 if cfg.test_mode else cfg.pageview_months
    pv_urls = discover_pageview_urls(pv_months, test_mode=cfg.test_mode)

    # 3. Estimate disk space
    est_gb = estimate_disk_space(content_urls, SQL_DUMPS, pv_urls, cfg.test_mode)
    log.info("Estimated total download size: ~%.1f GB", est_gb)
    log.info("Ensure you have at least %.0f GB of free disk space", est_gb * 1.5)

    # 4. Download SQL dumps
    log.info("--- Downloading SQL dumps ---")
    for fname in SQL_DUMPS:
        url = f"{LATEST_DUMPS_BASE}{fname}"
        dest = raw_dir / fname
        download_file(url, dest)

    # 5. Download content dump parts
    log.info("--- Downloading content dump (%d files) ---", len(content_urls))
    for url in content_urls:
        fname = url.split("/")[-1]
        dest = raw_dir / fname
        download_file(url, dest)

    # 6. Download pageview data
    log.info("--- Downloading pageview data (%d months) ---", len(pv_urls))
    for url in pv_urls:
        fname = url.split("/")[-1]
        dest = raw_dir / fname
        success = download_file(url, dest)
        if not success:
            log.warning("Failed to download %s — pageview URL pattern may have changed", fname)
            log.warning("Check %s manually for available files", PAGEVIEW_BASE)

    log.info("Downloads complete! Files saved to %s", raw_dir)


if __name__ == "__main__":
    main()
