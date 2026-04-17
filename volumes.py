"""Volume definitions for the Complete encyclopedia profile.

Encodes the 68 volumes from ENCYCLOPEDIA_VOLUMES.md and provides
title-to-volume assignment using bisect on start-key boundaries.
"""

from bisect import bisect_right

# Letter-based volumes (1-63): each defined by (start_prefix, end_prefix, label).
# For assignment, we use bisect on start prefixes — a title belongs to the last
# volume whose start prefix is <= the title's sort key.
_LETTER_VOLUMES = [
    (1,  "AA",       "AJ",       "AA – AJ"),
    (2,  "AK",       "AL",       "AK – AL"),
    (3,  "AM",       "ANS",      "AM – ANS"),
    (4,  "ANT",      "AR",       "ANT – AR"),
    (5,  "AS",       "AZ",       "AS – AZ"),
    (6,  "BA",       "BD",       "BA – BD"),
    (7,  "BE",       "BI",       "BE – BI"),
    (8,  "BJ",       "BRE",      "BJ – BRE"),
    (9,  "BRF",      "CAM",      "BRF – CAM"),
    (10, "CAN",      "CG",       "CAN – CG"),
    (11, "CHA",      "CHO",      "CHA – CHO"),
    (12, "CHR",      "COL",      "CHR – COL"),
    (13, "COM",      "CT",       "COM – CT"),
    (14, "CU",       "DA",       "CU – DA"),
    (15, "DE",       "DI",       "DE – DI"),
    (16, "DO",       "EC",       "DO – EC"),
    (17, "ED",       "EN",       "ED – EN"),
    (18, "EP",       "FAR",      "EP – FAR"),
    (19, "FAS",      "FO",       "FAS – FO"),
    (20, "FR",       "GAR",      "FR – GAR"),
    (21, "GAS",      "GI",       "GAS – GI"),
    (22, "GL",       "GR",       "GL – GR"),
    (23, "GU",       "HA",       "GU – HA"),
    (24, "HE",       "HM",       "HE – HM"),
    (25, "HO",       "IM",       "HO – IM"),
    (26, "IN",       "IV",       "IN – IV"),
    (27, "JA",       "JEL",      "JA – JEL"),
    (28, "JEN",      "JOHN R",   "JEN – JOHN R"),
    (29, "JOHN S",   "KAL",      "JOHN S – KAL"),
    (30, "KAM",      "KH",       "KAM – KH"),
    (31, "KI",       "KY",       "KI – KY"),
    (32, "LA",       "LEO",      "LA – LEO"),
    (33, "LEP",      "LIST OF F","LEP – LIST OF F"),
    (34, "LIST OF G","LIV",      "LIST OF G – LIV"),
    (35, "LO",       "MAD",      "LO – MAD"),
    (36, "MAG",      "MARJ",     "MAG – MARJ"),
    (37, "MARK",     "MEL",      "MARK – MEL"),
    (38, "MEM",      "MIN",      "MEM – MIN"),
    (39, "MIR",      "MO",       "MIR – MO"),
    (40, "MU",       "NA",       "MU – NA"),
    (41, "NE",       "NI",       "NE – NI"),
    (42, "NO",       "OM",       "NO – OM"),
    (43, "ON",       "PAP",      "ON – PAP"),
    (44, "PAR",      "PES",      "PAR – PES"),
    (45, "PET",      "PL",       "PET – PL"),
    (46, "PO",       "PS",       "PO – PS"),
    (47, "PU",       "RA",       "PU – RA"),
    (48, "RE",       "RI",       "RE – RI"),
    (49, "RO",       "RUR",      "RO – RUR"),
    (50, "RUS",      "SAP",      "RUS – SAP"),
    (51, "SAR",      "SE",       "SAR – SE"),
    (52, "SH",       "SI",       "SH – SI"),
    (53, "SK",       "SP",       "SK – SP"),
    (54, "ST",       "ST",       "ST"),
    (55, "SU",       "TA",       "SU – TA"),
    (56, "TE",       "THE I",    "TE – THE I"),
    (57, "THE J",    "TI",       "THE J – TI"),
    (58, "TO",       "TU",       "TO – TU"),
    (59, "TW",       "VA",       "TW – VA"),
    (60, "VE",       "WA",       "VE – WA"),
    (61, "WE",       "WI",       "WE – WI"),
    (62, "WO",       "YO",       "WO – YO"),
    (63, "YU",       "Z",        "YU – Z"),
]

# Pre-built list of start prefixes for bisect lookup
_LETTER_STARTS = [v[1] for v in _LETTER_VOLUMES]
_LETTER_NUMS = [v[0] for v in _LETTER_VOLUMES]

# All 68 volumes as dicts (digit/special volumes get labels assigned dynamically)
VOLUMES = []
for num, start, end, label in _LETTER_VOLUMES:
    VOLUMES.append({"num": num, "label": label, "start": start, "end": end})

# Digit and special volumes (64-68) — labels finalized after dynamic split
VOLUMES.append({"num": 64, "label": "1… (First Half)",  "start": None, "end": None})
VOLUMES.append({"num": 65, "label": "1… (Second Half)", "start": None, "end": None})
VOLUMES.append({"num": 66, "label": "2… (First Half)",  "start": None, "end": None})
VOLUMES.append({"num": 67, "label": "2… (Second Half)", "start": None, "end": None})
VOLUMES.append({"num": 68, "label": "Other",            "start": None, "end": None})


def get_volume(num: int) -> dict:
    """Return volume dict by 1-based number."""
    return VOLUMES[num - 1]


def sort_key(title: str) -> str:
    """Extract sort key for volume assignment.

    Strips leading non-alphanumeric characters so titles like "'Ant'"
    sort by their first letter rather than into special-character volumes.
    """
    for i, ch in enumerate(title):
        if ch.isalnum():
            return title[i:].upper()
    return title.upper()


def _assign_letter_volume(key: str) -> int:
    """Assign a letter-starting sort key to volumes 1-63 using bisect."""
    idx = bisect_right(_LETTER_STARTS, key) - 1
    if idx < 0:
        idx = 0
    return _LETTER_NUMS[idx]


def assign_volumes(titles: list[str]) -> dict[str, int]:
    """Assign each title to a volume number (1-68).

    Digit-starting titles ("1..." and "2...") are split at the median
    into first/second half volumes. Must see all titles at once to
    compute the split point.
    """
    assignments: dict[str, int] = {}
    digit1_titles: list[str] = []
    digit2_titles: list[str] = []

    for title in titles:
        key = sort_key(title)
        if not key:
            assignments[title] = 68
            continue

        first = key[0]
        if first.isalpha():
            assignments[title] = _assign_letter_volume(key)
        elif first == "1":
            digit1_titles.append(title)
        elif first == "2":
            digit2_titles.append(title)
        else:
            assignments[title] = 68

    # Split digit-1 titles into halves (volumes 64-65)
    digit1_titles.sort(key=sort_key)
    mid = len(digit1_titles) // 2
    for i, title in enumerate(digit1_titles):
        assignments[title] = 64 if i < mid else 65

    # Split digit-2 titles into halves (volumes 66-67)
    digit2_titles.sort(key=sort_key)
    mid = len(digit2_titles) // 2
    for i, title in enumerate(digit2_titles):
        assignments[title] = 66 if i < mid else 67

    return assignments
