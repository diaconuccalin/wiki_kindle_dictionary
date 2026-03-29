"""Centralized configuration for wiki-kindle-dictionary pipeline."""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

PROFILES = {
    "pocket":                {"long_tier": 10_000,  "short_tier": 90_000},
    "compact":               {"long_tier": 50_000,  "short_tier": 200_000},
    "standard":              {"long_tier": 100_000, "short_tier": 400_000},
    "large":                 {"long_tier": 100_000, "short_tier": 900_000},
    "full_breadth":          {"long_tier": 0,       "short_tier": 2_000_000},
    "full_encyclopedia_10k": {"long_tier": 10_000,  "short_tier": None},
    "full_encyclopedia_50k": {"long_tier": 50_000,  "short_tier": None},
    "full_encyclopedia_100k":{"long_tier": 100_000, "short_tier": None},
}


@dataclass
class Config:
    profile: str = "standard"
    long_tier: int = 100_000
    short_tier: int | None = 400_000

    max_short_abstract_length: int = 1000
    max_abstract_length: int | None = None
    max_orth_variants: int = 100
    include_redirects: bool = True

    include_languages: list[str] | None = None  # None = all
    exclude_languages: list[str] = field(default_factory=list)

    compression_level: int = 2
    skip_kf8: bool = True
    no_source_embed: bool = True
    volume_split_threshold_mb: int = 600
    entries_per_html_file: int = 10_000

    pageview_months: int = 3

    data_dir: Path = Path("data")
    output_dir: Path = Path("output")

    test_mode: bool = False
    test_entries: int = 1000

    @property
    def total_entries(self) -> int | None:
        """Total entries for this profile, or None for full encyclopedia."""
        if self.short_tier is None:
            return None
        return self.long_tier + self.short_tier

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def kindle_dir(self) -> Path:
        return self.data_dir / "kindle" / self.profile

    @property
    def abstracts_path(self) -> Path:
        return self.processed_dir / "abstracts.jsonl"

    @property
    def langlinks_path(self) -> Path:
        return self.processed_dir / "langlinks.jsonl"

    @property
    def page_id_to_title_path(self) -> Path:
        return self.processed_dir / "page_id_to_title.jsonl"

    @property
    def redirects_path(self) -> Path:
        return self.processed_dir / "redirects.jsonl"

    @property
    def pageviews_path(self) -> Path:
        return self.processed_dir / "pageviews.tsv"

    @property
    def merged_path(self) -> Path:
        return self.processed_dir / f"merged_{self.profile}.jsonl"

    def ensure_dirs(self):
        """Create all necessary directories."""
        for d in [self.raw_dir, self.processed_dir, self.kindle_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_args(cls, extra_args=None) -> "Config":
        """Parse CLI args, apply profile presets, return Config."""
        parser = argparse.ArgumentParser(
            description="Wiki Kindle Dictionary pipeline configuration"
        )
        parser.add_argument(
            "--profile", default="standard",
            choices=list(PROFILES) + ["custom"],
            help="Dictionary size profile (default: standard)"
        )
        parser.add_argument("--long-tier", type=int, default=None,
                            help="Number of articles getting long abstracts")
        parser.add_argument("--short-tier", type=int, default=None,
                            help="Number of articles getting short abstracts")
        parser.add_argument("--test", action="store_true",
                            help="Test mode: process only ~1000 articles")
        parser.add_argument("--fast", action="store_true",
                            help="Use fast compression (-c1) instead of huffdic (-c2)")
        parser.add_argument("--data-dir", type=Path, default=Path("data"),
                            help="Base data directory (default: data)")
        parser.add_argument("--output-dir", type=Path, default=Path("output"),
                            help="Output directory for .mobi files (default: output)")
        parser.add_argument("--entries-per-file", type=int, default=10_000,
                            help="Entries per HTML content file (default: 10000)")
        parser.add_argument("--pageview-months", type=int, default=3,
                            help="Number of recent months of pageview data (default: 3)")

        args = parser.parse_args(extra_args)

        cfg = cls()
        cfg.profile = args.profile
        cfg.data_dir = args.data_dir
        cfg.output_dir = args.output_dir
        cfg.entries_per_html_file = args.entries_per_file
        cfg.pageview_months = args.pageview_months

        # Apply profile preset
        if args.profile != "custom":
            preset = PROFILES[args.profile]
            cfg.long_tier = preset["long_tier"]
            cfg.short_tier = preset["short_tier"]

        # CLI overrides
        if args.long_tier is not None:
            cfg.long_tier = args.long_tier
        if args.short_tier is not None:
            cfg.short_tier = args.short_tier
        if args.test:
            cfg.test_mode = True
        if args.fast:
            cfg.compression_level = 1

        return cfg
