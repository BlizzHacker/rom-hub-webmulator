"""Webmulator platform slug -> RomM/ROMarr platform slug.

Exact-match lookup, no fallback and no prefix rules. A platform that is not
spelled out below resolves to nothing and its results are dropped, because
the alternative -- guessing -- files a ROM into another machine's directory
and nothing afterwards says anything went wrong.

**Every value here was checked against ROMarr's own table**, not written
from memory: each one was passed through `romarr.platforms.resolve()` and
had to come back as the platform whose `.slug` is that exact string.
`tests/test_platforms.py` re-runs that check whenever `romarr` is
importable, so a slug cannot be invented later either.

Where the 39 keys come from, and why that number matters
-------------------------------------------------------

`https://www.webmulator.com/games` renders one card per platform, each
carrying the platform's own game count, and it is **not paginated** -- 39
cards is the whole list. The counts in the comments below are those cards',
read 2026-08-12, and they total 40,090 games.

The **navigation dropdown shows 12**. Building from the nav rather than from
`/games` would silently drop 27 platforms and about half the catalogue,
including Neo Geo, all four Ataris, both WonderSwans, the three Capcom Play
Systems, Master System, Game Gear, 32X, ColecoVision, Intellivision,
Vectrex, PC-FX and the Magnavox Odyssey 2. Two independent checks say 39 is
right: a spread of 50 `search.php` queries turned up 27 distinct platform
segments and **not one** outside this table, and every plausible alternate
spelling (`nes`, `snes`, `psx`, `cps-1`, `vectrex`, `odyssey-2`,
`pc-engine`, `famicom`, ...) returns a clean 404 rather than a second door
into the same catalogue.

**Two platforms are deliberately unmapped.**

* `neo-geo` (206 games). This one is a *choice*, not a gap. ROMarr carries
  `neogeoaes` (the home cartridge machine), `neogeomvs` (the arcade board)
  and `arcade`, and Webmulator's platform slug says only "neo-geo". Nothing
  in the site's metadata -- not the title, not the console label, not the
  emulator it loads -- chooses between them. Two plausible slugs and no way
  to pick is exactly the case for refusing to answer. Mapping it to
  `arcade` would dodge the question rather than settle it, since that is a
  third answer and not obviously the right one either. ROMarr has a test
  asserting `resolve("neo-geo") is None`; this table agrees with it.

* `fairchild-channel-f` (13 games). ROMarr has no Fairchild Channel F
  platform. There is nothing to map it to, so it is counted and skipped.

The arcade collapse below is *not* that same case, and the difference is
worth being explicit about. `mame`, `capcom-play-system-1`,
`capcom-play-system-2` and `capcom-play-system-3` all map to `arcade`
because ROMarr models arcade hardware as one platform: Capcom Play System
*is* an arcade board, and the distinction between CPS1 and CPS2 is which
romset an arcade core loads, not which library folder holds it. Neo Geo is
different precisely because ROMarr does draw a line there and gives it two
sides.
"""

#: Webmulator platform slug -> ROMarr platform slug. Counts are Webmulator's
#: own, from the cards on `/games` (2026-08-12).
PLATFORMS: dict[str, str] = {
    "3do": "3do",                                       # 51
    "amiga": "amiga",                                   # 3,185
    "atari-2600": "atari2600",                          # 1,320
    "atari-5200": "atari5200",                          # 186
    "atari-7800": "atari7800",                          # 177
    "atari-jaguar": "jaguar",                           # 168
    "atari-lynx": "lynx",                               # 255
    "capcom-play-system-1": "arcade",                   # 100
    "capcom-play-system-2": "arcade",                   # 100
    "capcom-play-system-3": "arcade",                   # 6
    "colecovision": "colecovision",                     # 13
    "gameboy": "gb",                                    # 1,722
    "gameboy-advance": "gba",                           # 6,105
    "gameboy-color": "gbc",                             # 2,682
    "gce-vectrex": "vectrex",                           # 18
    "intellivision": "intellivision",                   # 18
    "magnavox-odissey-2": "odyssey-2-slash-videopac-g7000",  # 23
    "mame": "arcade",                                   # 2,468
    "msx": "msx",                                       # 66
    "neo-geo-pocket": "neo-geo-pocket",                 # 231
    "nintendo": "nes",                                  # 3,396
    "nintendo-64": "n64",                               # 2,625
    "nintendo-ds": "nds",                               # 6,258
    "nintendo-virtual-boy": "virtualboy",               # 51
    "pc-fx": "pc-fx",                                   # 20
    "playstation-1": "psx",                             # 678
    "sega-32x": "sega32",                               # 84
    "sega-cd": "segacd",                                # 206
    "sega-game-gear": "gamegear",                       # 652
    "sega-genesis": "genesis-slash-megadrive",          # 3,078
    "sega-master-system": "sms",                        # 200
    "sega-saturn": "saturn",                            # 206
    "sharp-x68000": "sharp-x68000",                     # 103
    "super-nintendo": "snes",                           # 2,846
    "turbografx16": "turbografx16--1",                  # 206
    "wonderswan": "wonderswan",                         # 366
    "wonderswan-color": "wonderswan-color",             # 2
}

#: Platforms Webmulator has that this plugin will not answer for, with the
#: game count each one costs and why. Kept as data rather than prose so
#: `tests/test_platforms.py` can assert the two sets do not overlap and that
#: together they account for all 39 platforms `/games` publishes.
UNMAPPED: dict[str, str] = {
    "neo-geo": (
        "ambiguous between ROMarr's neogeoaes and neogeomvs; nothing in "
        "Webmulator's metadata decides it (206 games)"
    ),
    "fairchild-channel-f": (
        "ROMarr has no Fairchild Channel F platform, so there is nothing "
        "to map it to (13 games)"
    ),
}

#: Every platform `/games` publishes -- the mapped and the skipped together.
#: A path whose first segment is not in here is not a Webmulator game path,
#: which is the second gate on a URL built from a parsed `href`.
PUBLISHED: frozenset[str] = frozenset(PLATFORMS) | frozenset(UNMAPPED)


def platform_for(platform_slug: str) -> str | None:
    """The ROMarr slug for a Webmulator platform, or nothing.

    Nothing is a real answer here and callers treat it as one: `search`
    drops the result rather than emitting it under a guessed platform, and
    `stream` refuses rather than building a URL for it.
    """
    return PLATFORMS.get(str(platform_slug or "").strip().casefold())


def webmulator_platforms_for(wanted: str) -> tuple[str, ...]:
    """Webmulator platforms a caller's `--platform` value refers to.

    Accepts either spelling -- ROMarr's slug (`arcade`) or Webmulator's own
    (`mame`) -- because a caller has no reason to know which one this
    plugin thinks in. Returns a tuple because the mapping is many-to-one:
    `arcade` is four Webmulator platforms, and answering with only the
    first would quietly hide CPS2.

    Sorted, so a platform-scoped search reads the same listings in the same
    order every time; "the same query cost a different number of requests"
    is otherwise indistinguishable from a bug.
    """
    key = str(wanted or "").strip().casefold()
    if not key:
        return ()
    if key in PLATFORMS:
        return (key,)
    # An unmapped platform matches nothing on purpose: asking for `neo-geo`
    # by name must not become a way around the refusal to map it.
    return tuple(sorted(p for p, slug in PLATFORMS.items() if slug == key))
