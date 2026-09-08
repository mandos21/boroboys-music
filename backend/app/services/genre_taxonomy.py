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

# Branches inside a family that are broad enough to colour on their own. Rock is
# the reason this exists: over half of a typical listener's tags resolve to it,
# and emo, shoegaze and garage rock sharing one colour says nothing useful. The
# tree already separates them, so these promote its own branches to groups.
_SUBGROUP_NODES = {
    "punk rock": "punk",
    "alternative rock": "alternative",
}

# The groups a genre can land in, in the order their colours are assigned.
# Adding one means adding a colour, and colours stop being separable in the low
# teens - so a new group has to earn its slot against an existing one.
GROUPS = (
    "rock",
    "alternative",
    "punk",
    "metal",
    "electronic",
    "hip hop",
    "pop",
    "jazz",
    "roots",
    "global",
    OTHER_GROUP,
)

# Families the tree defines, collapsed into groups. Kept broad on purpose: the
# groups exist so neighbouring genres share a colour, and a palette stops being
# separable long before twenty-one slots.
_GROUP_BY_FAMILY = {
    "rock": "rock",
    "metal": "metal",
    "blues": "roots",
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

# Spotify shorthand the tree spells out differently, or not at all. Values are
# tree terms rather than family names, so an alias inherits the same branch
# its target does. Each entry earns its place by appearing in real data.
_ALIASES = {
    "rap": "hip hop",
    "boom bap": "hip hop",
    "cloud rap": "hip hop",
    "gangster rap": "hip hop",
    "motown": "r&b",
    "punk": "punk rock",
    "indie": "indie rock",
    "neo-psychedelic": "neo-psychedelia",
    "jam band": "rock",
    "j-rock": "rock",
    "queercore": "punk rock",
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
    """Return the colour/count group for one genre string.

    A promoted branch wins over its family, so `midwest emo` is punk rather
    than rock while `garage rock` stays rock.
    """
    resolved = _resolve(genre)
    if resolved is None:
        return OTHER_GROUP
    family, subgroup = resolved
    return subgroup or _GROUP_BY_FAMILY.get(family, OTHER_GROUP)


def family_for(genre: str) -> str | None:
    """Return the beets family for one genre string, or None if unrecognised."""
    resolved = _resolve(genre)
    return resolved[0] if resolved else None


def _resolve(genre: str) -> tuple[str, str | None] | None:
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
def _taxonomy() -> tuple[
    dict[str, tuple[str, str | None]], tuple[tuple[str, re.Pattern[str]], ...]
]:
    """Map every term to its family and, where it has one, its promoted branch."""
    families: dict[str, tuple[str, str | None]] = {}

    def walk(node: Any, family: str, subgroup: str | None) -> None:
        if isinstance(node, str):
            name = node.casefold()
            families[name] = (family, _SUBGROUP_NODES.get(name, subgroup))
        elif isinstance(node, list):
            for child in node:
                walk(child, family, subgroup)
        elif isinstance(node, dict):
            for label, child in node.items():
                name = str(label).casefold()
                inherited = _SUBGROUP_NODES.get(name, subgroup)
                families[name] = (family, inherited)
                walk(child, family, inherited)

    for entry in yaml.safe_load(_TREE_PATH.read_text(encoding="utf-8")):
        ((label, children),) = entry.items()
        family = str(label)
        families[family.casefold()] = (family, None)
        walk(children, family, None)
    for alias, target in _ALIASES.items():
        families[alias] = families.get(target.casefold(), (target, None))

    # Word boundaries stop `ska` matching inside `skate punk`; ordering is by
    # length so a tie at the same position prefers the more specific term.
    patterns = tuple(
        (term, re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])"))
        for term in sorted(families, key=len, reverse=True)
    )
    return families, patterns
