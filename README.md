# Webmulator provider for ROM Hub / ROMarr

An RPP v1 provider that searches [Webmulator](https://www.webmulator.com)
and resolves a hit to the page where Webmulator runs its own emulator.

| Capability | Status |
|---|---|
| `search` | Implemented — the site's own `GET /search.php`, plus its per-platform indexes when a platform is asked for |
| `stream` | Implemented — the game page, which is where the site embeds its player |
| `importer` | **Deliberately absent.** See below |

Modelled on `romarr-plugin-retrostic`, which is the reference plugin for
this family.

## The one thing that will bite you: 12 vs 39

The navigation dropdown lists **12** platforms. The site actually serves
**39**, and `https://www.webmulator.com/games` renders all of them — one
card each, with the platform's own game count, and it is **not paginated**.

Building this plugin from the nav would have dropped 27 platforms and more
than half the catalogue: Neo Geo, all four Ataris, both WonderSwans, all
three Capcom Play Systems, Master System, Game Gear, 32X, ColecoVision,
Intellivision, Vectrex, PC-FX, Sharp X68000, TurboGrafx-16, 3DO, Virtual
Boy and the Magnavox Odyssey 2.

Two independent checks say 39 is the whole set, surveyed 2026-08-12:

* a spread of **50 `search.php` queries** turned up 27 distinct platform
  segments in game links and **not one** outside the table — as did every
  page read during the survey, 963 distinct game slugs in total;
* every plausible alternate spelling — `nes`, `snes`, `psx`, `dreamcast`,
  `gamecube`, `cps-1`, `vectrex`, `odyssey-2`, `pc-engine`, `famicom`,
  `atari-st`, `c64`, `zx-spectrum` — returns a clean **404**, so there is
  no second door into the same catalogue under a different name.

`tests/test_platforms.py` pins both the 39 and the 12, so a future
"simplification" down to the menu fails a test instead of silently losing
half the site.

## Platforms

**37 of the 39 map to a ROMarr platform.** Every slug in
`webmulator/platforms.py` was checked with `romarr.platforms.resolve()`,
and `tests/test_platforms.py` re-runs that check whenever ROMarr is
importable — so a slug cannot be invented, and a value that happens to be
an alias rather than a canonical slug fails too.

Two are not answered for:

| Platform | Games | Why |
|---|---|---|
| `neo-geo` | 206 | ROMarr carries `neogeoaes` **and** `neogeomvs`, and Webmulator's metadata says only "neo-geo" — not the title, not the console label, not the emulator it loads picks one. Two plausible slugs is what "refuse to answer" is for. ROMarr has its own test asserting `resolve("neo-geo") is None`; this plugin agrees with it. |
| `fairchild-channel-f` | 13 | ROMarr has no Fairchild Channel F platform. Nothing to map to. |

Results on those two are **dropped**, never emitted under a guessed
platform, and `--platform neo-geo` matches nothing rather than becoming a
way around the refusal.

`arcade` is a different case and is applied on purpose: `mame`,
`capcom-play-system-1`, `-2` and `-3` are all arcade hardware and ROMarr
models arcade as one platform, so the collapse loses nothing the library
models. Neo Geo is different precisely because ROMarr *does* draw a line
there and gives it two sides.

Two of the site's slugs are spelled oddly and the spellings are its own,
not typos here: `magnavox-odissey-2` (one "d", two "s") and `gce-vectrex`.
Correcting either one 404s, so both are pinned by a test.

## How much of the site is reachable

The counters on `/games` total **40,090 games** across the 39 platforms;
the 37 mapped ones account for 39,871 of them.

Walking the per-platform indexes reaches **materially fewer than that**,
and it is worth knowing before you plan around the number. Each index
paginates to a last page the site names in its own `>>` link, but the pages
render fewer cards than the counter implies. Measured by walking three
platforms to their last page:

| Platform | `/games` says | Index actually yields |
|---|---|---|
| `sega-master-system` | 200 | 100 |
| `atari-jaguar` | 168 | 56 |
| `sega-32x` | 84 | 41 |

Multiplying page 1's card count by each platform's last page puts the
site-wide figure near **18,000**, and that method reads a little high
against the three walked above — so treat it as an upper bound, not a
target. The rest is reachable only through `search.php`, which is exactly
why this plugin asks the search endpoint **first** and treats the index as
a top-up rather than the other way round.

Two more things about the indexes, both of which will produce wrong counts
if you assume otherwise:

* **Page size is not fixed.** It varies by platform — 12, 17, 34 and 18
  cards per page were all observed on page 1 of different platforms — so
  "a short page is the last page" is not a usable stop condition here. The
  walk stops on the site's own last-page link, or on a page that adds no
  new paths.
* **An out-of-range page number does not 404.** `/games/nintendo/page/101`
  re-serves page 100. Without the "no new paths" stop, a large `max_pages`
  would re-read the last page over and over.

Consecutive pages also overlap by one card, and the NES index prints
`super-mario-bros-3` three times on page 1 under three spellings of the
title. Both are deduplicated by path.

## Why there is no importer

Webmulator is a play-in-browser site. It publishes **no download control**
— no button, no form, no link. The only path to a ROM file is the query
string of the emulator iframe on each game page:

```html
<iframe class="playgame-iframe"
        src="https://downloads.webmulator.com/play.php?emulator=1&console_slug=nintendo
             &rom_url=%2Froms%2FSuper+Mario+Bros.+%28Japan%2C+USA%29.zip&…">
```

That `.zip` is presumably reachable. Lifting it would produce a working
download path by routing around the flow the site actually publishes, which
is the same call the Retrostic plugin made and it is declined here too.

So `importer` is **not declared in `manifest.toml`**, rather than declared
and raising at runtime. An operator sees a plugin that does not offer
downloads, not one that offers them and always refuses. `manifest.toml`
also does not declare `downloads.webmulator.com` in its network allowlist,
so the enforcement is structural: the host would refuse that host even if
somebody later wrote the code. `tests/test_provider.py` asserts that a
`stream` target never contains that host, `play.php` or `.zip`.

Every search result carries `downloadable: "false"` and `playable: "true"`
in `extra`, so callers do not have to discover this per item.

## Why the site's own results are filtered

Webmulator's search returns its real matches and then **pads the page out
with unrelated popular titles**. A live `search.php?search_term_string=contra`
on 2026-08-12 returned twelve cards of which exactly one was a Contra game;
the other eleven were Marvel Vs. Capcom 2, House of the Dead 2, Sonic Rush,
Phoenix Wright, FIFA 2005 and similar. A nonsense query (`zzqqxwv`) returns
**zero** cards — which is what proves the eleven are a pad rather than a
generous fuzzy match, because a matcher with that much slack would have
matched the nonsense too.

So a card whose title does not carry the query's words is dropped. This is
**not** a re-ranking: the site's own relevance order is left exactly as
served. It is declining to hand back rows the site itself did not claim
were matches, because "FIFA 2005" arriving as a result for `contra` ends up
in somebody's library under that name.

The comparison is deliberately loose — letters and digits only, order
ignored — so `megaman` finds "Mega Man 2" and `link zelda` finds "The
Legend of Zelda - Link's Awakening". The failure modes are not symmetric:
keeping one pad row costs a caller one bad line, dropping one real hit
costs them the game.

## What a query costs the site

| Query | Requests |
|---|---|
| `rom-hub search "bomberman"` | 1 |
| `rom-hub search "super mario" --platform nes` | 2 |
| either, with `max_pages = N` | at most `N` per surface |

The two surfaces answer different questions and neither can answer the
other's: `search.php` searches everything and cannot be scoped to a
platform, while `/games/<platform>` is scoped and cannot be searched. A
platform-scoped query therefore asks the cheap catalogue-wide one first and
only tops up from the index if the limit is not already met.

When a ROMarr slug covers several Webmulator platforms — `arcade` is four —
`max_pages` is a budget for the **whole** top-up, not per platform, so an
operator who capped it at 2 gets 2 index requests and not 8.

A non-200 — 403, 429, 503 — **stops the search**, including the surface
that would have been read next. It is not retried and the request is not
varied, because that is where routing around a refusal starts.

## Install

```sh
rom-hub plugin install https://git.moveweight.com/BlizzHacker/romarr-plugin-webmulator --ref v0.1.0
rom-hub search "bomberman" --platform saturn
rom-hub stream webmulator sega-saturn/saturn-bomberman-e
```

The `source_id` is the game path, `<platform>/<title-slug>` — it
reconstructs the URL exactly and is revalidated every time it comes back,
including at `stream`, because by then it has been round-tripped through
storage and another process. Validation is two questions, not one: is this
*shaped* like a game path, and is its first segment one of the 39 platforms
the site publishes. `/games/evil/x` passes the first and fails the second.

To list it in ROMarr's **Hub → Plugins** catalogue:

```sh
rom-hub catalog add moveweight-webmulator \
  https://git.moveweight.com/BlizzHacker/romarr-plugin-webmulator/raw/tag/v0.1.0/catalog/plugins.json
rom-hub catalog refresh
```

## Config

| Key | Default | Meaning |
|---|---|---|
| `collection` | `Webmulator` | RomM collection name for imported entries |
| `max_pages` | `1` | Pages read per surface |
| `request_delay_ms` | `1500` | Milliseconds between requests, floor `500` |

The delay is in **milliseconds**, and named `_ms`, because RPP v1's config
types are `str | int | bool | list[str] | secret` — there is no `float`,
and `parse_manifest` rejects a manifest that declares one rather than
degrading. An integer count of milliseconds says the same thing in a type
the host actually has. (Worth knowing if you are copying a sibling plugin's
manifest: some of them declare `request_delay = { type = "float" }`, which
does not load.)

`request_delay_ms` has a floor an operator cannot configure away, and it spans
both surfaces — the index request that follows a search request is spaced
from it rather than fired the instant it finishes. Webmulator's
`robots.txt` is `User-agent: * / Disallow:` with no `Crawl-delay`, so the
gap is our own restraint rather than a rule being followed, and a
configurable zero would quietly remove it.

## Test

```sh
ROM_HUB_SRC=/opt/rom-hub/src ROMARR_SRC=/opt/romarr pytest tests/ -q
```

138 passing. `ROMARR_SRC` is what makes the platform-slug checks run rather
than skip; without it the suite still passes but the load-bearing test is
skipped, which is the one thing here worth not skipping. (`conftest.py`
also looks in `/opt/romarr` and in a sibling working copy, so on either the
deployment or a laptop checkout it usually finds ROMarr on its own.)

The fixtures in `tests/fixtures/` are real responses, trimmed to their card
grid and pagination and otherwise exactly the markup the site served on
2026-08-12 — including the duplicate card the NES index really prints, the
Neo Geo hit that really appears in a `bomberman` search and must be
dropped, and the five padding rows a `contra` search really returns. (Line
endings are the one edit: the site serves CRLF and the fixtures are stored
LF, like the rest of the repo.)

## Terms

Webmulator hosts mixed game content and plays it in the browser. This
provider indexes metadata the site publishes and links to pages the site
presents to visitors; it grants no redistribution rights and downloads
nothing. Operators are responsible for using it in accordance with
applicable law and the source's terms.

## License

MIT — see `LICENSE`.
