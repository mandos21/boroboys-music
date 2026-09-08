"""Grouping free-form Spotify genres onto the vendored beets hierarchy."""

from __future__ import annotations

import pytest

from app.services.genre_taxonomy import OTHER_GROUP, family_for, group_for


@pytest.mark.parametrize(
    ("genre", "group"),
    [
        # Exact terms the tree carries.
        ("shoegaze", "rock"),
        ("bebop", "jazz"),
        ("dancehall", "global"),
        # The head noun is the last word, so the rightmost term wins. Matching
        # the longest term instead would call these ambient and alternative.
        ("ambient jazz", "jazz"),
        ("alt country", "roots"),
        ("ambient folk", "roots"),
        # Spotify shorthand the tree spells out differently, or not at all.
        ("rap", "hip hop"),
        ("edm", "electronic"),
        ("neo-psychedelic", "rock"),
        # The tree overrides what the words suggest: dream pop is a rock genre.
        ("dream pop", "rock"),
        # Word boundaries stop a short term matching inside a longer one.
        ("skate punk", "rock"),
    ],
)
def test_genres_group_by_taxonomy_not_by_spelling(genre: str, group: str) -> None:
    assert group_for(genre) == group


def test_an_unrecognised_genre_is_grouped_as_other_rather_than_guessed() -> None:
    assert family_for("escape room") is None
    assert group_for("escape room") == OTHER_GROUP
    assert group_for("") == OTHER_GROUP


def test_the_vendored_tree_still_carries_the_families_we_map() -> None:
    """A refreshed tree must not silently drop a family we colour by."""
    for genre, family in [
        ("shoegaze", "rock"),
        ("bebop", "jazz"),
        ("afrobeat", "african"),
        ("dancehall", "reggae"),
        ("bluegrass", "country"),
        ("house", "electronic"),
    ]:
        assert family_for(genre) == family, genre
