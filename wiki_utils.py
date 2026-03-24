"""Shared utilities for title normalization and text processing."""

import re
import unicodedata
from urllib.parse import unquote


def normalize_title(title: str) -> str:
    """Normalize a Wikipedia title to canonical form.

    - Replace underscores with spaces
    - URL-decode percent-encoded characters
    - Apply Unicode NFC normalization
    - Strip leading/trailing whitespace
    - Capitalize first letter (Wikipedia convention)
    """
    title = title.replace("_", " ")
    title = unquote(title)
    title = unicodedata.normalize("NFC", title)
    title = title.strip()
    if title:
        title = title[0].upper() + title[1:]
    return title


def clean_abstract_text(text: str) -> str:
    """Post-processing cleanup of extracted abstract text.

    Removes remaining wikitext/HTML artifacts after mwparserfromhell processing.
    """
    # Remove remaining template fragments {{...}}
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # Remove remaining wikilink fragments [[...]]
    text = re.sub(r"\[\[[^\]]*\]\]", "", text)
    # Remove <ref> tags and content
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/>", "", text)
    # Remove any remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove category links
    text = re.sub(r"\[\[Category:[^\]]*\]\]", "", text, flags=re.IGNORECASE)
    # Collapse multiple whitespace
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse multiple newlines into double newline (paragraph separator)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # NFC normalize
    text = unicodedata.normalize("NFC", text)
    return text.strip()


def split_short_long(lead_text: str) -> tuple[str, str]:
    """Split cleaned lead section into short and long abstracts.

    Short = first paragraph (up to first blank line).
    Long = full lead section.
    """
    long_abstract = lead_text.strip()
    # First paragraph: split on double newline
    parts = re.split(r"\n\n+", long_abstract, maxsplit=1)
    short_abstract = parts[0].strip()
    return short_abstract, long_abstract
