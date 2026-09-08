"""Grouping free-form Spotify genres onto the vendored beets hierarchy."""

from __future__ import annotations

import pytest

from app.services.genre_taxonomy import OTHER_GROUP, family_for, group_for


@pytest.mark.parametrize(
    ("genre", "group"),
    [
        # Exact terms the tree carries.
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
        # Promoted branches: the tree separates these inside rock, and rock is
        # otherwise so dominant that emo, shoegaze and garage rock would all
        # share one colour.
        ("midwest emo", "punk"),
        ("shoegaze", "alternative"),
        ("garage rock", "rock"),
        # The tree overrides what the words suggest: dream pop sits under
        # alternative rock, not pop.
        ("dream pop", "alternative"),
        # Metal is its own family here, not a branch of rock.
        ("sludge metal", "metal"),
        ("metalcore", "metal"),
        # Word boundaries stop a short term matching inside a longer one.
        ("skate punk", "punk"),
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
        ("bebop", "jazz"),
        ("afrobeat", "african"),
        ("dancehall", "reggae"),
        ("bluegrass", "country"),
        ("house", "electronic"),
        # Metal was moved out of rock deliberately; heavy metal stays behind as
        # the origin. A refreshed upstream tree would undo both.
        ("sludge metal", "metal"),
        ("heavy metal", "rock"),
    ]:
        assert family_for(genre) == family, genre
