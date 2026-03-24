"""Stage 2a: Parse MediaWiki XML content dump and extract article abstracts.

Input: data/raw/enwiki-NS0-*.xml*.bz2 (MediaWiki XML export, bz2 compressed)
Output: data/processed/abstracts.jsonl

Uses mwparserfromhell for wikitext parsing with post-processing cleanup.
"""

import bz2
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import mwparserfromhell
from tqdm import tqdm

from config import Config
from wiki_utils import clean_abstract_text, normalize_title, split_short_long

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# MediaWiki XML namespace
MW_NS = "http://www.mediawiki.org/xml/export-0.11/"


def extract_lead_section(wikitext: str) -> str:
    """Extract the lead section (everything before first == heading) from wikitext."""
    # Split on section headings (== ... ==)
    # Use \n== to avoid matching == inside text
    parts = re.split(r"\n==", wikitext, maxsplit=1)
    lead = parts[0]
    return lead


def parse_wikitext_to_plaintext(wikitext: str) -> str:
    """Parse wikitext and extract clean plaintext using mwparserfromhell."""
    try:
        code = mwparserfromhell.parse(wikitext)
    except Exception as e:
        log.debug("mwparserfromhell parse error: %s", e)
        return ""

    # Remove file/image links before stripping
    for link in code.filter_wikilinks():
        title = str(link.title).strip()
        if title.lower().startswith(("file:", "image:", "category:")):
            try:
                code.remove(link)
            except ValueError:
                pass

    # Strip to plaintext (removes templates, tags, etc.)
    text = code.strip_code(normalize=True, collapse=True)
    return str(text)


def process_xml_dump(xml_path: Path, cfg: Config):
    """Stream-parse an XML dump file and yield (title, short, long) tuples."""
    log.info("Processing %s ...", xml_path.name)

    # Determine opener based on extension
    if xml_path.suffix == ".bz2" or ".bz2" in xml_path.suffixes:
        opener = lambda p: bz2.open(p, "rb")
    else:
        opener = lambda p: open(p, "rb")

    count = 0
    skipped_redirect = 0
    skipped_empty = 0

    with opener(xml_path) as f:
        # Use iterparse for memory efficiency
        context = ET.iterparse(f, events=("end",))

        for event, elem in context:
            # Handle both namespaced and non-namespaced tags
            tag = elem.tag
            if "}" in tag:
                tag = tag.split("}", 1)[1]

            if tag != "page":
                continue

            try:
                # Extract namespace
                ns_elem = elem.find(f"{{{MW_NS}}}ns")
                if ns_elem is None:
                    ns_elem = elem.find("ns")
                if ns_elem is not None and ns_elem.text != "0":
                    continue

                # Extract title
                title_elem = elem.find(f"{{{MW_NS}}}title")
                if title_elem is None:
                    title_elem = elem.find("title")
                if title_elem is None or not title_elem.text:
                    continue
                title = normalize_title(title_elem.text)

                # Extract text content
                revision = elem.find(f"{{{MW_NS}}}revision")
                if revision is None:
                    revision = elem.find("revision")
                if revision is None:
                    continue

                text_elem = revision.find(f"{{{MW_NS}}}text")
                if text_elem is None:
                    text_elem = revision.find("text")
                if text_elem is None or not text_elem.text:
                    continue
                wikitext = text_elem.text

                # Skip redirects
                if wikitext.strip().upper().startswith("#REDIRECT"):
                    skipped_redirect += 1
                    continue

                # Extract lead section
                lead = extract_lead_section(wikitext)
                if not lead.strip():
                    skipped_empty += 1
                    continue

                # Parse to plaintext
                plaintext = parse_wikitext_to_plaintext(lead)

                # Post-processing cleanup
                plaintext = clean_abstract_text(plaintext)

                if not plaintext or len(plaintext) < 10:
                    skipped_empty += 1
                    continue

                # Split into short and long
                short_abstract, long_abstract = split_short_long(plaintext)

                if not short_abstract:
                    skipped_empty += 1
                    continue

                count += 1
                yield title, short_abstract, long_abstract

                if count % 100_000 == 0:
                    log.info("  Processed %d articles...", count)

                # Test mode: stop early
                if cfg.test_mode and count >= cfg.test_entries:
                    log.info("Test mode: stopping after %d articles", count)
                    break

            finally:
                # Free memory
                elem.clear()

    log.info("  %s: %d articles extracted, %d redirects skipped, %d empty skipped",
             xml_path.name, count, skipped_redirect, skipped_empty)


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    output_path = cfg.abstracts_path
    if output_path.exists():
        log.info("Output already exists: %s (delete to reprocess)", output_path)
        return

    # Find XML dump files
    raw_dir = cfg.raw_dir
    xml_files = sorted(raw_dir.glob("enwiki-NS0-*.xml*"))
    if not xml_files:
        # Also check for non-NS0 naming patterns
        xml_files = sorted(raw_dir.glob("enwiki-*.xml*"))
        # Filter out SQL dumps
        xml_files = [f for f in xml_files if ".sql" not in f.name]

    if not xml_files:
        log.error("No XML dump files found in %s", raw_dir)
        log.error("Expected files matching: enwiki-NS0-*.xml*.bz2")
        return

    log.info("Found %d XML dump file(s)", len(xml_files))

    # Process all files and collect results
    articles: dict[str, tuple[str, str]] = {}  # title -> (short, long)

    for xml_path in xml_files:
        for title, short_abstract, long_abstract in process_xml_dump(xml_path, cfg):
            # Deduplicate: keep the first occurrence
            if title not in articles:
                articles[title] = (short_abstract, long_abstract)

        if cfg.test_mode and len(articles) >= cfg.test_entries:
            break

    log.info("Total unique articles: %d", len(articles))

    # Write sorted by title
    log.info("Writing to %s ...", output_path)
    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for title in sorted(articles.keys()):
            short, long = articles[title]
            obj = {"title": title, "short": short, "long": long}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    tmp_path.rename(output_path)

    log.info("Wrote %d articles to %s", len(articles), output_path)


if __name__ == "__main__":
    main()
