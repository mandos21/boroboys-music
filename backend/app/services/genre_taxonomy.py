"""Group free-form Spotify genre strings into a stable, shared taxonomy.

Spotify returns genres as uncontrolled prose - `bedroom pop`, `alt country`,
`neo-psychedelic` - with no hierarchy. The vendored beets tree in
`app/data/genres-tree.yaml` supplies one, mapping roughly 800 terms onto 21
families, which we collapse again into a handful of groups broad enough to
colour and count by.

Resolution tries an exact match, then the rightmost known term appearing as
whole words inside the string - genre names put the head noun last, so `ambient
jazz` is jazz rather than ambient. A small alias table covers the shorthand
Spotify uses that the tree does not carry (`rap`, `metal`, `indie`). Anything
still unresolved is `other` rather than a guess.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_TREE_PATH = Path(__file__).resolve().parent.parent / "data" / "genres-tree.yaml"

OTHER_GROUP = "other"

# Families the tree defines, collapsed into groups. Kept broad on purpose: the
# groups exist so neighbouring genres share a colour, and a palette stops being
# separable long before twenty-one slots.
_GROUP_BY_FAMILY = {
    "rock": "rock",
    "blues": "rock",
    "pop": "pop",
    "easy listening": "pop",
    "electronic": "electronic",
    "hip hop": "hip hop",
    "r&b": "hip hop",
    "jazz": "jazz",
    "classical": "jazz",
    "avant-garde": "jazz",
    "country": "roots",
    "folk": "roots",
    "singer-songwriter": "roots",
    "african": "global",
    "asian": "global",
    "caribbean and latin american": "global",
    "reggae": "global",
    "world music": "global",
    "soundtrack": OTHER_GROUP,
    "comedy": OTHER_GROUP,
    "kids music": OTHER_GROUP,
}

# Spotify shorthand the tree spells out differently, or not at all. Each entry
# earns its place by appearing in real submission data.
_ALIASES = {
    "rap": "hip hop",
    "boom bap": "hip hop",
    "cloud rap": "hip hop",
    "gangster rap": "hip hop",
    "motown": "r&b",
    "metal": "rock",
    "punk": "rock",
    "indie": "rock",
    "emo": "rock",
    "neo-psychedelic": "rock",
    "jam band": "rock",
    "j-rock": "rock",
    "queercore": "rock",
    "aor": "rock",
    "edm": "electronic",
    "synthpop": "electronic",
    "vaporwave": "electronic",
    "darkwave": "electronic",
    "cold wave": "electronic",
    "ebm": "electronic",
    "future bass": "electronic",
    "hyperpop": "pop",
    "big band": "jazz",
    "experimental": "avant-garde",
    "drone": "avant-garde",
    "plunderphonics": "avant-garde",
    "newgrass": "country",
    "children's music": "kids music",
    "anime": "soundtrack",
    "vocaloid": "soundtrack",
}


def group_for(genre: str) -> str:
    """Return the colour/count group for one genre string."""
    return _GROUP_BY_FAMILY.get(family_for(genre) or "", OTHER_GROUP)


def family_for(genre: str) -> str | None:
    """Return the beets family for one genre string, or None if unrecognised."""
    key = genre.strip().casefold()
    if not key:
        return None
    families, patterns = _taxonomy()
    direct = families.get(key)
    if direct is not None:
        return direct
    # Genre names put the head noun last - `ambient jazz` is jazz, `alt country`
    # is country - so the rightmost match wins, and the longest breaks a tie.
    best: tuple[int, int, str] | None = None
    for term, pattern in patterns:
        match = pattern.search(key)
        if match is None:
            continue
        candidate = (match.start(), len(term), term)
        if best is None or candidate > best:
            best = candidate
    return families[best[2]] if best else None


@lru_cache(maxsize=1)
def _taxonomy() -> tuple[dict[str, str], tuple[tuple[str, re.Pattern[str]], ...]]:
    families: dict[str, str] = {}

    def walk(node: Any, family: str) -> None:
        if isinstance(node, str):
            families[node.casefold()] = family
        elif isinstance(node, list):
            for child in node:
                walk(child, family)
        elif isinstance(node, dict):
            for label, child in node.items():
                families[str(label).casefold()] = family
                walk(child, family)

    for entry in yaml.safe_load(_TREE_PATH.read_text(encoding="utf-8")):
        ((label, children),) = entry.items()
        families[str(label).casefold()] = str(label)
        walk(children, str(label))
    families.update(_ALIASES)

    # Word boundaries stop `ska` matching inside `skate punk`; ordering is by
    # length so a tie at the same position prefers the more specific term.
    patterns = tuple(
        (term, re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])"))
        for term in sorted(families, key=len, reverse=True)
    )
    return families, patterns
