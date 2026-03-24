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


def compile_dictionary(cfg: Config):
    """Run KindleGen on the generated OPF file."""
    kindle_dir = cfg.kindle_dir
    opf_path = kindle_dir / "dictionary.opf"

    if not opf_path.exists():
        log.error("OPF file not found at %s. Run 04_generate_html.py first.", opf_path)
        return False

    kindlegen = find_kindlegen()
    if kindlegen is None:
        log.error(
            "kindlegen not found. Download it from Amazon or ensure it is in your PATH.\n"
            "Common install locations: ~/kindlegen, /usr/local/bin/kindlegen"
        )
        return False

    log.info("Using kindlegen: %s", kindlegen)

    # Build command
    cmd = [str(kindlegen)]
    cmd.append(f"-c{cfg.compression_level}")
    if cfg.skip_kf8:
        cmd.append("-gen_ff_mobi7")
    if cfg.no_source_embed:
        cmd.append("-dont_append_source")
    cmd.append(str(opf_path))

    log.info("Running: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

    # KindleGen exit codes: 0 = success, 1 = warnings, 2 = error
    if result.returncode == 2:
        log.error("KindleGen failed with errors:")
        log.error(result.stdout)
        log.error(result.stderr)
        return False

    if result.returncode == 1:
        log.warning("KindleGen completed with warnings (this is normal for dictionaries)")

    if result.stdout:
        # Log last few lines which contain the summary
        for line in result.stdout.strip().split("\n")[-10:]:
            log.info("  kindlegen: %s", line)

    # Find the output .mobi file
    mobi_path = opf_path.with_suffix(".mobi")
    if not mobi_path.exists():
        log.error("Expected .mobi output not found at %s", mobi_path)
        return False

    mobi_size = mobi_path.stat().st_size
    log.info("Generated: %s (%.1f MB)", mobi_path.name, mobi_size / 1024 / 1024)

    # Move to output directory
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.date.today().isoformat()
    output_name = f"wikipedia_dict_{cfg.profile}_{date_str}.mobi"
    output_path = cfg.output_dir / output_name
    shutil.copy2(mobi_path, output_path)
    log.info("Copied to: %s", output_path)

    # Update PROFILE_ESTIMATES.md
    update_profile_estimates(cfg, mobi_size)

    return True


def update_profile_estimates(cfg: Config, mobi_size: int):
    """Update PROFILE_ESTIMATES.md with actual measured size."""
    estimates_path = Path("PROFILE_ESTIMATES.md")
    if not estimates_path.exists():
        return

    date_str = datetime.date.today().isoformat()
    size_mb = mobi_size / 1024 / 1024
    total = cfg.total_entries

    log.info("Profile '%s': actual .mobi size = %.1f MB, entries = %s",
             cfg.profile, size_mb, total if total else "all")


def main():
    cfg = Config.from_args()
    cfg.ensure_dirs()

    success = compile_dictionary(cfg)
    if success:
        log.info("Compilation complete!")
    else:
        log.error("Compilation failed.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
