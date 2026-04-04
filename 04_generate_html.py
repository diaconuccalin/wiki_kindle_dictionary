"""Stage 4: Generate Kindle dictionary HTML, OPF, cover, and attribution."""

import html
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from config import Config
from volumes import VOLUMES, assign_volumes, get_volume, sort_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

XHTML_HEADER = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:idx="http://www.mobipocket.com/idx">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <title>Wikipedia Dictionary</title>
</head>
<body>
"""

XHTML_FOOTER = """\
</body>
</html>
"""

ATTRIBUTION_HTML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <title>Attribution</title>
</head>
<body>
  <h2>Wikipedia Kindle Dictionary</h2>
  <p>This dictionary contains content from <b>Wikipedia</b>, the free encyclopedia.</p>
  <p>Content is available under the
  <b>Creative Commons Attribution-ShareAlike 3.0 Unported License</b> (CC BY-SA 3.0).</p>
  <p>For more information, visit: https://en.wikipedia.org/</p>
  <p>This dictionary was generated automatically from Wikipedia dump files.
  It is not affiliated with or endorsed by the Wikimedia Foundation.</p>
</body>
</html>
"""


def generate_entry(entry: dict) -> str:
    """Generate idx:entry HTML for a single dictionary entry."""
    lines = ['<idx:entry name="default" scriptable="yes">']

    # All orth variants use value= so they are indexed but not rendered as visible text.
    # The title is already displayed as bold text in the content below.
    en_title = html.escape(entry["en_title"], quote=True)
    lines.append(f'  <idx:orth value="{en_title}" />')

    seen = {entry["en_title"].lower()}
    for variant in entry.get("orth_variants", []):
        key = variant.lower()
        if key not in seen:
            seen.add(key)
            lines.append(f'  <idx:orth value="{html.escape(variant, quote=True)}" />')

    # Abstract content
    abstract_text = re.sub(r"\(\s*[;,]?\s*\)", "", entry["abstract"])
    tier = entry.get("tier", "short")

    if tier == "long":
        # Long tier: title as header, then paragraphs
        lines.append(f"  <p><b>{en_title}</b></p>")
        paragraphs = re.split(r"\n\n+", abstract_text)
        for para in paragraphs:
            para = para.strip()
            if para:
                lines.append(f"  <p>{html.escape(para)}</p>")
    else:
        # Short tier: title + em dash + abstract in one paragraph
        lines.append(f"  <p><b>{en_title}</b> \u2014 {html.escape(abstract_text)}</p>")

    lines.append("</idx:entry>")
    return "\n".join(lines)


def generate_content_files(entries: list[dict], kindle_dir: Path,
                           entries_per_file: int) -> list[str]:
    """Generate batched XHTML content files. Returns list of filenames."""
    content_files = []
    total_bytes = 0
    file_idx = 0

    for batch_start in range(0, len(entries), entries_per_file):
        file_idx += 1
        batch = entries[batch_start : batch_start + entries_per_file]
        fname = f"content_{file_idx:03d}.html"
        content_files.append(fname)

        fpath = kindle_dir / fname
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(XHTML_HEADER)
            for entry in batch:
                entry_html = generate_entry(entry)
                f.write(entry_html)
                f.write("\n<hr/>\n")
            f.write(XHTML_FOOTER)

        fsize = fpath.stat().st_size
        total_bytes += fsize
        log.info("  %s: %d entries, %.1f KB", fname, len(batch), fsize / 1024)

    log.info("Total HTML content: %.1f MB across %d files",
             total_bytes / 1024 / 1024, len(content_files))
    return content_files


def write_attribution(kindle_dir: Path):
    """Write the attribution HTML page."""
    attr_path = kindle_dir / "attribution.html"
    attr_path.write_text(ATTRIBUTION_HTML, encoding="utf-8")
    log.info("Generated %s", attr_path)


def generate_opf(content_files: list[str], kindle_dir: Path,
                 profile: str = "pocket", volume_info: dict | None = None) -> Path:
    """Generate the OPF package file."""
    manifest_items = []
    spine_items = []

    # Attribution page first
    manifest_items.append(
        '    <item id="attribution" href="attribution.html" media-type="application/xhtml+xml" />'
    )
    spine_items.append('    <itemref idref="attribution" />')

    # Cover
    manifest_items.append(
        '    <item id="cover" href="cover.jpg" media-type="image/jpeg" properties="cover-image" />'
    )

    # Content files
    for i, fname in enumerate(content_files, 1):
        item_id = f"content{i:03d}"
        manifest_items.append(
            f'    <item id="{item_id}" href="{fname}" media-type="application/xhtml+xml" />'
        )
        spine_items.append(f'    <itemref idref="{item_id}" />')

    if volume_info:
        title = f"Wikipedia Dictionary (Complete) - {volume_info['label']}"
        uid = f"wikipedia-kindle-dict-complete-vol{volume_info['num']:02d}"
    else:
        title = f"Wikipedia Dictionary ({profile.capitalize()})"
        uid = f"wikipedia-kindle-dict-{profile}"

    opf = f"""\
<?xml version="1.0" encoding="utf-8"?>
<package unique-identifier="uid">
  <metadata>
    <dc:title>{title}</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Wikipedia</dc:creator>
    <dc:identifier id="uid">{uid}</dc:identifier>
    <meta name="cover" content="cover" />
    <x-metadata>
      <DictionaryInLanguage>en</DictionaryInLanguage>
      <DictionaryOutLanguage>en</DictionaryOutLanguage>
      <DefaultLookupIndex>default</DefaultLookupIndex>
    </x-metadata>
  </metadata>
  <manifest>
{chr(10).join(manifest_items)}
  </manifest>
  <spine>
{chr(10).join(spine_items)}
  </spine>
</package>
"""
    opf_path = kindle_dir / "dictionary.opf"
    opf_path.write_text(opf, encoding="utf-8")
    log.info("Generated %s", opf_path)
    return opf_path


def generate_cover(kindle_dir: Path, profile: str = "pocket",
                   volume_info: dict | None = None):
    """Generate a cover image, optionally overlaying volume label."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Determine source image
        if profile == "complete":
            cover_src = Path(__file__).parent / "img" / "complete.png"
        else:
            cover_src = Path(__file__).parent / "img" / f"{profile}.png"

        if cover_src.exists():
            img = Image.open(cover_src).convert("RGBA")

            # Overlay volume label for complete profile
            if volume_info:
                draw = ImageDraw.Draw(img)
                label = volume_info["label"]

                # Try common bold font paths, fall back to bitmap
                _bold_candidates = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/Library/Fonts/Arial Bold.ttf",
                    "/System/Library/Fonts/Helvetica.ttc",
                ]

                font_size = 108
                font = next(
                    (ImageFont.truetype(p, font_size)
                     for p in _bold_candidates if Path(p).exists()),
                    ImageFont.load_default(),
                )

                # Shrink font if text is too wide (>80% of image width)
                max_width = int(img.width * 0.8)
                bbox = draw.textbbox((0, 0), label, font=font)
                while bbox[2] - bbox[0] > max_width and font_size > 24:
                    font_size -= 4
                    font = next(
                        (ImageFont.truetype(p, font_size)
                         for p in _bold_candidates if Path(p).exists()),
                        font,
                    )
                    bbox = draw.textbbox((0, 0), label, font=font)

                text_height = bbox[3] - bbox[1]
                text_width = bbox[2] - bbox[0]

                # Semi-transparent black band across full width
                band_padding = 30
                band_y_top = 1880 - band_padding
                band_y_bottom = 1880 + text_height + band_padding
                band_center_y = (band_y_top + band_y_bottom) // 2

                band = Image.new("RGBA", img.size, (0, 0, 0, 0))
                band_draw = ImageDraw.Draw(band)
                band_draw.rectangle(
                    [0, band_y_top, img.width, band_y_bottom],
                    fill=(0, 0, 0, 77),  # 30% opacity
                )
                img = Image.alpha_composite(img, band)

                # Center text on band
                draw = ImageDraw.Draw(img)
                x = (img.width - text_width) // 2
                y = band_center_y - text_height // 2
                draw.text((x, y), label, fill=(255, 255, 255, 255), font=font)

            cover_path = kindle_dir / "cover.jpg"
            img.convert("RGB").save(cover_path, "JPEG", quality=85)
            log.info("Generated %s (from %s)", cover_path, cover_src)
            return

        # Fallback: programmatic cover
        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        _bold_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        _regular_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        font_title = next(
            (ImageFont.truetype(p, 36) for p in _bold_candidates if Path(p).exists()),
            ImageFont.load_default(),
        )
        font_sub = next(
            (ImageFont.truetype(p, 20) for p in _regular_candidates if Path(p).exists()),
            font_title,
        )
        draw.text((300, 300), "Wikipedia\nDictionary", fill=(0, 0, 0), font=font_title, anchor="mm")
        draw.text((300, 450), "Kindle Edition", fill=(100, 100, 100), font=font_sub, anchor="mm")
        cover_path = kindle_dir / "cover.jpg"
        img.save(cover_path, "JPEG", quality=85)
        log.info("Generated %s", cover_path)
    except ImportError:
        # Pillow not installed — create a minimal 1x1 JPEG placeholder
        log.warning("Pillow not installed, creating minimal cover placeholder")
        cover_path = kindle_dir / "cover.jpg"
        cover_path.write_bytes(
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
            b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
            b'\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04'
            b'\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07'
            b'"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17'
            b'\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz'
            b'\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99'
            b'\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7'
            b'\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5'
            b'\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1'
            b'\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\xae\x8a(\x03\xff\xd9'
        )


def generate_complete(cfg: Config):
    """Generate HTML for complete encyclopedia volumes.

    Two-pass approach to avoid loading all 7M entries into memory:
    Pass 1: stream titles only to compute volume assignments (~500 MB)
    Pass 2: stream entries, loading only the target volume(s) into memory
    """
    merged_path = cfg.merged_path
    if not merged_path.exists():
        log.error("Merged data not found at %s. Run 03_merge.py first.", merged_path)
        return

    # Pass 1: read titles only and assign volumes
    log.info("Pass 1: reading titles for volume assignment...")
    titles = []
    with open(merged_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            titles.append(obj["en_title"])
    log.info("Read %d titles", len(titles))

    vol_assignments = assign_volumes(titles)
    del titles

    # Determine which volumes to build
    if cfg.volume is not None:
        volumes_to_build = {cfg.volume}
    else:
        volumes_to_build = set(range(1, 69))

    # Pass 2: stream entries, collect only those in target volumes
    log.info("Pass 2: loading entries for %d volume(s)...", len(volumes_to_build))
    vol_entries: dict[int, list] = defaultdict(list)
    with open(merged_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            vol_num = vol_assignments[entry["en_title"]]
            if vol_num in volumes_to_build:
                vol_entries[vol_num].append(entry)

    del vol_assignments

    # Sort entries within each volume alphabetically
    for vol_num in vol_entries:
        vol_entries[vol_num].sort(key=lambda e: sort_key(e["en_title"]))

    for vol_num in sorted(volumes_to_build):
        vol_info = get_volume(vol_num)
        entries_for_vol = vol_entries.get(vol_num, [])

        if not entries_for_vol:
            log.warning("Volume %d (%s) has no entries, skipping", vol_num, vol_info["label"])
            continue

        vol_dir = cfg.data_dir / "kindle" / "complete" / f"vol_{vol_num:02d}"
        vol_dir.mkdir(parents=True, exist_ok=True)

        log.info("--- Volume %d: %s (%d entries) ---", vol_num, vol_info["label"], len(entries_for_vol))

        content_files = generate_content_files(entries_for_vol, vol_dir, cfg.entries_per_html_file)
        write_attribution(vol_dir)
        generate_cover(vol_dir, "complete", vol_info)
        generate_opf(content_files, vol_dir, "complete", vol_info)

    log.info("Complete encyclopedia HTML generation finished.")


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    if cfg.profile == "complete":
        generate_complete(cfg)
        return

    merged_path = cfg.merged_path
    if not merged_path.exists():
        log.error("Merged data not found at %s. Run 03_merge.py first.", merged_path)
        return

    kindle_dir = cfg.kindle_dir

    # Read all entries
    entries = []
    with open(merged_path, "r", encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))
    log.info("Loaded %d entries from %s", len(entries), merged_path)

    # Generate content HTML files
    content_files = generate_content_files(entries, kindle_dir, cfg.entries_per_html_file)

    # Generate attribution page
    write_attribution(kindle_dir)

    # Generate cover
    generate_cover(kindle_dir, cfg.profile)

    # Generate OPF
    generate_opf(content_files, kindle_dir, cfg.profile)

    log.info("Kindle HTML generation complete. Output in %s", kindle_dir)


if __name__ == "__main__":
    main()
