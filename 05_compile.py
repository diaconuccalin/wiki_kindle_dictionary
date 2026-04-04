"""Stage 5: Compile Kindle dictionary HTML to .mobi using KindleGen."""

import datetime
import logging
import shutil
import subprocess
from pathlib import Path

from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def find_kindlegen() -> Path | None:
    """Locate the kindlegen binary."""
    # Check PATH first
    kg = shutil.which("kindlegen")
    if kg:
        return Path(kg)
    # Check common locations
    common_paths = [
        Path.home() / "kindlegen",
        Path.home() / "bin" / "kindlegen",
        Path("/usr/local/bin/kindlegen"),
        Path("/opt/kindlegen/kindlegen"),
    ]
    for p in common_paths:
        if p.exists() and p.is_file():
            return p
    return None


def run_kindlegen(cfg: Config, opf_path: Path) -> bool:
    """Run KindleGen on an OPF file. Returns True on success."""
    kindlegen = find_kindlegen()
    if kindlegen is None:
        log.error(
            "kindlegen not found. Download it from Amazon or ensure it is in your PATH.\n"
            "Common install locations: ~/kindlegen, /usr/local/bin/kindlegen"
        )
        return False

    log.info("Using kindlegen: %s", kindlegen)

    cmd = [str(kindlegen)]
    cmd.append(f"-c{cfg.compression_level}")
    if cfg.skip_kf8:
        cmd.append("-gen_ff_mobi7")
    if cfg.no_source_embed:
        cmd.append("-dont_append_source")
    cmd.append("-verbose")
    cmd.append(str(opf_path))

    log.info("Running: %s", " ".join(cmd))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                log.info("  kindlegen: %s", line)
        proc.wait(timeout=86400)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        log.error("KindleGen timed out after 24 hours")
        return False

    if proc.returncode == 2:
        log.error("KindleGen failed with errors (see output above)")
        return False

    if proc.returncode == 1:
        log.warning("KindleGen completed with warnings (this is normal for dictionaries)")

    mobi_path = opf_path.with_suffix(".mobi")
    if not mobi_path.exists():
        log.error("Expected .mobi output not found at %s", mobi_path)
        return False

    mobi_size = mobi_path.stat().st_size
    log.info("Generated: %s (%.1f MB)", mobi_path.name, mobi_size / 1024 / 1024)
    return True


def compile_dictionary(cfg: Config):
    """Compile a single-volume dictionary (pocket profile)."""
    kindle_dir = cfg.kindle_dir
    opf_path = kindle_dir / "dictionary.opf"

    if not opf_path.exists():
        log.error("OPF file not found at %s. Run 04_generate_html.py first.", opf_path)
        return False

    if not run_kindlegen(cfg, opf_path):
        return False

    mobi_path = opf_path.with_suffix(".mobi")
    mobi_size = mobi_path.stat().st_size

    # Move to output directory
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.date.today().isoformat()
    output_name = f"wikipedia_dict_{cfg.profile}_{date_str}.mobi"
    output_path = cfg.output_dir / output_name
    shutil.copy2(mobi_path, output_path)
    log.info("Copied to: %s", output_path)

    update_profile_estimates(cfg, mobi_size)
    return True


def compile_complete(cfg: Config):
    """Compile all (or one) complete encyclopedia volumes."""
    complete_base = cfg.data_dir / "kindle" / "complete"

    if cfg.volume is not None:
        vol_dirs = [complete_base / f"vol_{cfg.volume:02d}"]
    else:
        vol_dirs = sorted(complete_base.glob("vol_*"))

    if not vol_dirs:
        log.error("No volume directories found in %s. Run 04_generate_html.py first.", complete_base)
        return False

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.date.today().isoformat()
    success_count = 0

    for vol_dir in vol_dirs:
        opf_path = vol_dir / "dictionary.opf"
        if not opf_path.exists():
            log.warning("No OPF in %s, skipping", vol_dir)
            continue

        vol_num = int(vol_dir.name.split("_")[1])
        log.info("--- Compiling volume %d ---", vol_num)

        if not run_kindlegen(cfg, opf_path):
            log.error("Failed to compile volume %d", vol_num)
            continue

        mobi_path = opf_path.with_suffix(".mobi")
        mobi_size = mobi_path.stat().st_size
        output_name = f"wikipedia_dict_complete_vol{vol_num:02d}_{date_str}.mobi"
        output_path = cfg.output_dir / output_name
        shutil.copy2(mobi_path, output_path)
        log.info("Copied to: %s (%.1f MB)", output_path, mobi_size / 1024 / 1024)
        success_count += 1

    log.info("Compiled %d/%d volumes", success_count, len(vol_dirs))
    return success_count > 0


PROFILE_DISPLAY_NAMES = {
    "pocket": "Pocket",
    "complete": "Complete",
}


def update_profile_estimates(cfg: Config, mobi_size: int):
    """Update PROFILE_ESTIMATES.md with actual measured size."""
    estimates_path = Path("PROFILE_ESTIMATES.md")
    if not estimates_path.exists():
        return

    date_str = datetime.date.today().isoformat()
    size_mb = mobi_size / 1024 / 1024
    total = cfg.total_entries
    display_name = PROFILE_DISPLAY_NAMES.get(cfg.profile, cfg.profile.capitalize())

    log.info("Profile '%s': actual .mobi size = %.1f MB, entries = %s",
             cfg.profile, size_mb, total if total else "all")

    content = estimates_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    # Update profile row in main table: match on display name in first column
    for i, line in enumerate(lines):
        cols = [c.strip() for c in line.split("|")]
        if len(cols) >= 9 and cols[1] == display_name:
            avg_bytes = int(mobi_size / total) if total else 0
            avg_str = str(avg_bytes) if total else "—"
            lines[i] = (
                f"| {cols[1]} | {cols[2]} | {cols[3]} | {cols[4]} | {cols[5]} "
                f"| {size_mb:.1f} MB | {avg_str} | {date_str} |\n"
            )
            break

    # Compute HTML size from content files
    html_size_mb = sum(
        f.stat().st_size for f in cfg.kindle_dir.glob("*.html")
    ) / 1024 / 1024

    # Reconstruct flags string
    flags_parts = [f"-c{cfg.compression_level}"]
    if cfg.skip_kf8:
        flags_parts.append("-gen_ff_mobi7")
    if cfg.no_source_embed:
        flags_parts.append("-dont_append_source")
    flags_str = " ".join(flags_parts)

    entries_str = f"{total // 1000}K" if total else "all"
    new_row = (
        f"| {date_str} | {cfg.profile} | {entries_str} | — "
        f"| {html_size_mb:.1f} MB | {size_mb:.1f} MB | — | `{flags_str}` |\n"
    )

    # Append to build history table (after last | row at end of file)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("|"):
            lines.insert(i + 1, new_row)
            break

    estimates_path.write_text("".join(lines), encoding="utf-8")


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    if cfg.profile == "complete":
        success = compile_complete(cfg)
    else:
        success = compile_dictionary(cfg)

    if success:
        log.info("Compilation complete!")
    else:
        log.error("Compilation failed.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
