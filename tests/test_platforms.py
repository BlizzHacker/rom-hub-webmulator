"""The table in platforms.py must not contain a slug somebody invented.

`test_every_slug_is_one_romarr_actually_has` is the load-bearing test in
this repo. A wrong slug does not fail anywhere: the import succeeds, the
file lands, and the library quietly holds a Master System ROM in the Game
Gear folder. So the mapping is checked against ROMarr's own table rather
than against a copy of it.
"""

import pytest

from webmulator.platforms import (
    PLATFORMS,
    PUBLISHED,
    UNMAPPED,
    platform_for,
    webmulator_platforms_for,
)

romarr_platforms = pytest.importorskip(
    "romarr.platforms",
    reason="ROMarr is not importable here; run with ROMARR_SRC set to check slugs",
)

#: What `https://www.webmulator.com/games` renders, one card per platform,
#: surveyed 2026-08-12. Pinned so that a platform appearing or disappearing
#: upstream shows up as a failing test rather than as silently missing
#: results. The page is not paginated: 39 cards is the whole list.
PUBLISHED_2026_08_12 = {
    "gameboy-advance", "nintendo-ds", "nintendo", "mame", "sega-genesis",
    "nintendo-64", "super-nintendo", "gameboy-color", "amiga", "gameboy",
    "atari-2600", "playstation-1", "sega-game-gear", "sega-saturn",
    "wonderswan", "atari-lynx", "neo-geo-pocket", "sega-cd", "turbografx16",
    "sega-master-system", "atari-5200", "atari-jaguar", "atari-7800",
    "neo-geo", "sharp-x68000", "sega-32x", "3do", "msx",
    "nintendo-virtual-boy", "capcom-play-system-1", "capcom-play-system-2",
    "intellivision", "magnavox-odissey-2", "pc-fx", "gce-vectrex",
    "colecovision", "fairchild-channel-f", "capcom-play-system-3",
    "wonderswan-color",
}

#: The twelve in the site's navigation dropdown. Kept because the gap
#: between this and the set above is the single most expensive thing to get
#: wrong about this site, and a test is a better place to say so than a
#: comment: building from the nav drops 27 platforms.
NAVIGATION_ONLY = {
    "amiga", "gameboy", "gameboy-advance", "gameboy-color", "mame", "msx",
    "nintendo", "nintendo-64", "nintendo-ds", "playstation-1", "sega-saturn",
    "super-nintendo",
}


@pytest.mark.parametrize("platform,slug", sorted(PLATFORMS.items()))
def test_every_slug_is_one_romarr_actually_has(platform, slug):
    resolved = romarr_platforms.resolve(slug)
    assert resolved is not None, f"{platform} -> {slug!r} is not a ROMarr platform"
    # resolve() also answers to names and aliases, so a value that happens to
    # be an alias would pass a bare "is not None". Require the canonical slug.
    assert resolved.slug == slug, (
        f"{platform} -> {slug!r} resolves to {resolved.slug!r}, not itself"
    )


def test_the_table_and_the_skips_together_cover_the_published_platforms():
    assert set(PLATFORMS) | set(UNMAPPED) == PUBLISHED_2026_08_12
    assert PUBLISHED == PUBLISHED_2026_08_12
    assert len(PUBLISHED) == 39


def test_the_navigation_is_not_the_platform_list():
    # The nav shows 12 of 39. This is pinned as a test rather than left as
    # prose because a future rewrite that "simplifies" the table down to
    # what the menu offers would lose more than half the site and nothing
    # else would notice.
    assert NAVIGATION_ONLY < PUBLISHED
    assert len(PUBLISHED - NAVIGATION_ONLY) == 27


def test_a_platform_is_either_mapped_or_skipped_never_both():
    assert not set(PLATFORMS) & set(UNMAPPED)


def test_every_skip_says_why():
    for platform, reason in UNMAPPED.items():
        assert len(reason) > 20, f"{platform} is skipped without a real reason"


def test_neo_geo_stays_unmapped():
    # ROMarr models neogeoaes and neogeomvs separately and Webmulator's
    # metadata does not choose between them. ROMarr has its own test
    # asserting resolve("neo-geo") is None; this one asserts that this
    # plugin does not paper over it with a guess of its own.
    assert platform_for("neo-geo") is None
    assert romarr_platforms.resolve("neo-geo") is None
    assert "neo-geo" not in PLATFORMS.values()
    assert platform_for("neo-geo") != "arcade"


def test_unknown_platform_returns_nothing_rather_than_a_guess():
    assert platform_for("fairchild-channel-f") is None
    assert platform_for("nintendo-switch") is None
    assert platform_for("") is None
    assert platform_for(None) is None


def test_lookup_folds_case_and_surrounding_space():
    assert platform_for("NINTENDO") == "nes"
    assert platform_for(" Sega-Genesis ") == "genesis-slash-megadrive"
    # Folding is only case and edge whitespace. Inner punctuation is not
    # normalised, so a platform slug still has to be the slug.
    assert platform_for("sega genesis") is None
    assert platform_for("sega_genesis") is None


def test_arcade_collapse_is_deliberate():
    # Four Webmulator platforms are arcade hardware and ROMarr models
    # arcade as one platform. Pinned so nobody "fixes" it into invented
    # slugs like "cps1".
    assert {
        platform_for(p) for p in (
            "mame", "capcom-play-system-1", "capcom-play-system-2",
            "capcom-play-system-3",
        )
    } == {"arcade"}


def test_the_odd_spellings_are_the_sites_own():
    # Webmulator spells it "odissey" and "gce-vectrex". Both are its slugs,
    # not typos in this table, and correcting either one 404s.
    assert platform_for("magnavox-odissey-2") == "odyssey-2-slash-videopac-g7000"
    assert platform_for("magnavox-odyssey-2") is None
    assert platform_for("gce-vectrex") == "vectrex"
    assert platform_for("vectrex") is None


def test_a_platform_filter_accepts_either_spelling():
    assert webmulator_platforms_for("nes") == ("nintendo",)
    assert webmulator_platforms_for("nintendo") == ("nintendo",)
    assert webmulator_platforms_for("NES") == ("nintendo",)


def test_a_romarr_slug_that_is_several_webmulator_platforms_returns_all():
    # Answering with only the first would quietly hide CPS2 from anyone who
    # searched `--platform arcade`.
    assert webmulator_platforms_for("arcade") == (
        "capcom-play-system-1", "capcom-play-system-2", "capcom-play-system-3",
        "mame",
    )


def test_asking_for_a_skipped_platform_by_name_matches_nothing():
    # Naming `neo-geo` directly must not become a way around the refusal to
    # map it.
    assert webmulator_platforms_for("neo-geo") == ()
    assert webmulator_platforms_for("fairchild-channel-f") == ()
    assert webmulator_platforms_for("") == ()
    assert webmulator_platforms_for(None) == ()
