"""Utilities for parsing MySQL dump files (gzipped SQL with INSERT INTO statements).

Handles MySQL escaping: escaped quotes (\'), backslashes (\\), NULL values,
numeric unquoted values, and values containing parentheses inside strings.
"""

import gzip
import logging
from typing import Generator

log = logging.getLogger(__name__)


def parse_sql_dump(filepath: str, table_name: str) -> Generator[tuple, None, None]:
    """Stream-parse a gzipped MySQL dump file and yield row tuples.

    Looks for lines like:
        INSERT INTO `table_name` VALUES (val1,val2,...),(val1,val2,...),...;

    Yields tuples of strings (or None for NULL). Callers cast types as needed.
    """
    prefix = f"INSERT INTO `{table_name}` VALUES "

    with gzip.open(filepath, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith(prefix):
                continue
            # Strip the prefix and trailing ";\n"
            values_str = line[len(prefix):].rstrip().rstrip(";")
            yield from _parse_values(values_str)


def _parse_values(s: str) -> Generator[tuple, None, None]:
    """Parse the VALUES portion: (v1,v2,...),(v1,v2,...),... into tuples."""
    i = 0
    n = len(s)

    while i < n:
        # Find opening paren
        if s[i] != "(":
            i += 1
            continue

        i += 1  # skip '('
        row = []
        while i < n:
            if s[i] == ")":
                # End of this tuple
                i += 1
                yield tuple(row)
                break
            elif s[i] == ",":
                # separator between values (or between tuples)
                i += 1
                continue
            elif s[i] == "'":
                # Quoted string value
                val, i = _parse_quoted(s, i)
                row.append(val)
            elif s[i] == "N" and s[i:i+4] == "NULL":
                row.append(None)
                i += 4
            else:
                # Unquoted numeric value
                val, i = _parse_unquoted(s, i)
                row.append(val)


def _parse_quoted(s: str, start: int) -> tuple[str, int]:
    """Parse a single-quoted MySQL string starting at position start.

    Handles \\' (escaped quote) and \\\\ (escaped backslash).
    Returns (value, new_position_after_closing_quote).
    """
    i = start + 1  # skip opening quote
    chars = []
    n = len(s)

    while i < n:
        c = s[i]
        if c == "\\":
            # Escape sequence
            if i + 1 < n:
                next_c = s[i + 1]
                if next_c == "'":
                    chars.append("'")
                elif next_c == "\\":
                    chars.append("\\")
                elif next_c == "n":
                    chars.append("\n")
                elif next_c == "r":
                    chars.append("\r")
                elif next_c == "t":
                    chars.append("\t")
                elif next_c == "0":
                    chars.append("\0")
                else:
                    chars.append(next_c)
                i += 2
            else:
                chars.append(c)
                i += 1
        elif c == "'":
            # End of string
            i += 1
            return "".join(chars), i
        else:
            chars.append(c)
            i += 1

    # Shouldn't reach here in well-formed SQL
    return "".join(chars), i


def _parse_unquoted(s: str, start: int) -> tuple[str, int]:
    """Parse an unquoted value (number) until comma or closing paren."""
    i = start
    n = len(s)
    while i < n and s[i] not in (",", ")"):
        i += 1
    return s[start:i], i
