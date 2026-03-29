"""Stage 4: Generate Kindle dictionary HTML, OPF, cover, and attribution."""

import html
import json
import logging
import re
from pathlib import Path

from config import Config

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


def generate_opf(content_files: list[str], kindle_dir: Path, profile: str = "standard") -> Path:
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

    opf = f"""\
<?xml version="1.0" encoding="utf-8"?>
<package unique-identifier="uid">
  <metadata>
    <dc:title>Wikipedia Dictionary ({profile.capitalize()})</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Wikipedia</dc:creator>
    <dc:identifier id="uid">wikipedia-kindle-dict-{profile}</dc:identifier>
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


# Maps profile names to cover image filenames (without .png extension).
# Profiles not listed here use their own name directly.
PROFILE_COVER_MAP = {
    "full_breadth":          "complete",
    "full_encyclopedia_10k": "complete",
    "full_encyclopedia_50k": "complete",
    "full_encyclopedia_100k":"complete",
}


def generate_cover(kindle_dir: Path, profile: str = "standard"):
    """Generate a simple cover image."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Use profile-specific cover image if available
        image_name = PROFILE_COVER_MAP.get(profile, profile)
        cover_src = Path(__file__).parent / "img" / f"{image_name}.png"
        if cover_src.exists():
            img = Image.open(cover_src).convert("RGB")
            cover_path = kindle_dir / "cover.jpg"
            img.save(cover_path, "JPEG", quality=85)
            log.info("Generated %s (from %s)", cover_path, cover_src)
            return

        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Try common font paths (Linux then macOS), fall back to bitmap font
        _bold_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
            "/Library/Fonts/Arial Bold.ttf",                          # macOS (Office)
            "/System/Library/Fonts/Helvetica.ttc",                    # macOS system
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
        # Minimal JPEG bytes (1x1 white pixel)
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


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    merged_path = cfg.merged_path
    if not merged_path.exists():
        log.error("Merged data not found at %s. Run 03_merge.py first.", merged_path)
        return

    kindle_dir = cfg.kindle_dir
    entries_per_file = cfg.entries_per_html_file

    # Read all entries
    entries = []
    with open(merged_path, "r", encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))
    log.info("Loaded %d entries from %s", len(entries), merged_path)

    # Generate content HTML files
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

    # Generate attribution page
    attr_path = kindle_dir / "attribution.html"
    attr_path.write_text(ATTRIBUTION_HTML, encoding="utf-8")
    log.info("Generated %s", attr_path)

    # Generate cover
    generate_cover(kindle_dir, cfg.profile)

    # Generate OPF
    generate_opf(content_files, kindle_dir, cfg.profile)

    log.info("Kindle HTML generation complete. Output in %s", kindle_dir)


if __name__ == "__main__":
    main()
