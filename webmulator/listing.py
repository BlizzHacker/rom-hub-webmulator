"""Parse Webmulator's game cards, and build its URLs back up safely.

Webmulator renders both of its listing surfaces -- the per-platform index
at `/games/<platform>` and the results of `GET /search.php` -- as the same
kind of server-side card grid, so this is an HTML parse rather than an API
read. It uses `html.parser` from the standard library rather than a regex
over the markup, because the two surfaces nest that card *differently*:

    listing page                      search page
    ------------                      -----------
    <div class="single-rom">          <a href="/games/mame/x" title="X ROM">
      <div class="roms-img">            <div class="single-rom">
        <a href="/games/nes/x">           <div class="roms-img"> ... </div>
          <picture>...</picture>          <div class="roms-ftr">
        </a>                                <h2 class="roms-title">X</h2>
      </div>                                <div class="tagBtns">
      <div class="roms-ftr">                  <a href="/games/mame">MAME</a>
        <a href="/games/nes/x">               </div>
          <h2 class="roms-title">X</h2>      <a class="download-link">
        </a>                                  <span class="down-number">7</span>
        <div class="list-rom-rating"          </a>
             data-rating="4.4"></div>     </div>
        <span class="down-number">7</span> </div>
      </div>                            </a>
    </div>

On one the anchor is *inside* the card; on the other it *wraps* it. What is
constant across both -- and what this parser keys on -- is the order: a
game's `href` always appears before that game's `roms-title`, and the
rating, console label and download count always appear after it. So the
parser carries a pending path forward and closes a card on `</h2>`, which
holds for both layouts and does not care which element wraps which.

**Nothing built here is trusted because it came from the page.** Every path
must match `GAME_PATH` *and* name one of the 39 platforms `/games`
publishes before it becomes a URL, which is what keeps a crafted `href`
from turning into a request somewhere else. The allowlist in `netpolicy`
would refuse a foreign host anyway, but a parser that hands the allowlist
something to reject is relying on the last line of defence for ordinary
correctness.

`GAME_PATH` is tight on purpose and the tightness is measured: across
every page read during the 2026-08-12 survey -- 39 platform indexes, 50
search responses, sampled deep pages -- **963 distinct game slugs** used
only `[a-z0-9-]`, and so did all 39 platform segments. Requiring that shape
rejects nothing real.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode

from .platforms import PUBLISHED

BASE = "https://www.webmulator.com"

#: `<platform>/<slug>` -- the part of a game URL after `/games/`. Anchored,
#: lowercase-only, exactly two segments. Slugs legitimately start with a
#: digit (`1200-in-1-j`, `52-games`, `72-in-1`), so the leading character
#: class allows one.
GAME_PATH = re.compile(r"([a-z0-9][a-z0-9-]*)/([a-z0-9][a-z0-9-]*)")

#: An `href` into the games tree, with or without the trailing slash.
_HREF = re.compile(r"^/games/(.+?)/?$")

#: A region tag in the title: "Saturn Bomberman (E)", "Contra (USA)".
#: Only the first parenthesised group is taken -- the rest are dump flags.
_REGION = re.compile(r"\(([^)]{1,24})\)")

#: Pagination, on either surface. The per-platform index paginates as
#: `/games/<platform>/page/N`; `search.php` paginates as `?currentpage=N`.
#: Both appear only inside the pagination block, so one scan covers both.
_PAGE_NUMBER = re.compile(r"/page/(\d+)|currentpage=(\d+)")

#: `page` is not a game slug -- `/games/nintendo/page` would parse as one
#: and resolve to a listing wearing a game's clothes. It has never been
#: observed as an href; the guard is here so it cannot become one.
_NOT_A_SLUG = frozenset({"page"})


@dataclass(frozen=True)
class Entry:
    """One game card, already validated into parts that rebuild a URL."""

    path: str               # "nintendo/super-mario" -- this is the source_id
    platform_seg: str       # "nintendo" -- Webmulator's own platform slug
    slug: str               # "super-mario"
    title: str              # "Super Mario"
    console_label: str = ""  # "NES" as the search page printed it
    rating: str = ""        # "4.4", or "" where the site printed nothing
    downloads: int | None = None

    @property
    def page_url(self) -> str:
        """The game's page -- which is also where it is played.

        Webmulator embeds its emulator in an iframe on the game page
        itself rather than on a separate `/play` route, so there is one
        URL here and `stream` returns this one.
        """
        return f"{BASE}/games/{self.path}"

    @property
    def region(self) -> str:
        match = _REGION.search(self.title)
        return match.group(1).strip() if match else ""


def split_path(value: str) -> tuple[str, str, str] | None:
    """`"nintendo/super-mario"` -> `(path, "nintendo", "super-mario")`.

    The single gate every path passes through, whether it arrived from a
    parsed page or from a `SearchResult.source_id` handed back by the host
    on a later call. `fullmatch` rather than `search`, so a path with
    anything appended -- `../`, a query, a third segment -- is not a match
    at all rather than a match with a tail.

    The platform segment must be one Webmulator actually publishes. That
    is the difference between "this is shaped like a game path" and "this
    is a game path": `/games/evil/x` satisfies the first and not the
    second, and only the second may become a URL.
    """
    text = str(value or "").strip().strip("/").casefold()
    found = GAME_PATH.fullmatch(text)
    if found is None:
        return None
    platform_seg, slug = found.group(1), found.group(2)
    if platform_seg not in PUBLISHED or slug in _NOT_A_SLUG:
        return None
    return (text, platform_seg, slug)


def _as_int(text: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", text or "")
    return int(digits) if digits else None


class _Card:
    __slots__ = ("path", "title", "console_label", "rating", "downloads")

    def __init__(self, path: str, title: str) -> None:
        self.path = path
        self.title = title
        self.console_label = ""
        self.rating = ""
        self.downloads: int | None = None


class _CardParser(HTMLParser):
    """Collect game cards from either surface, in rendered order.

    Holds one piece of state that matters -- `_pending`, the last valid
    game path seen -- and closes a card when a `roms-title` heading ends.
    Everything after that heading and before the next game href belongs to
    the card just closed, which is how the rating, the console label and
    the download count are attached without depending on the nesting.

    `_pending` is cleared as soon as it is used, so a path becomes at most
    one card. A card carries its game's `href` two or three times -- once
    on the thumbnail anchor, once on the title anchor, once on the mobile
    variant -- and only the heading closes a card, so the repeats are
    harmless; a second heading under the same pending path would not be.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[_Card] = []
        self._pending: str | None = None
        self._title_buf: list[str] | None = None
        self._label_buf: list[str] | None = None
        self._number_buf: list[str] | None = None

    # -- helpers ------------------------------------------------------
    @property
    def _last(self) -> _Card | None:
        return self.cards[-1] if self.cards else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = attr.get("class", "").split()

        if tag == "a":
            found = _HREF.match(attr.get("href", "").strip())
            if not found:
                return
            parts = split_path(found.group(1))
            if parts is not None:
                self._pending = parts[0]
                return
            # A bare `/games/<platform>` inside a card is the search
            # page's console button -- the only place the site prints a
            # human-readable console name next to a result.
            if "emulator" in classes and self._last is not None:
                self._label_buf = []
            return

        if tag == "h2" and "roms-title" in classes:
            self._title_buf = []
        elif tag == "div" and "list-rom-rating" in classes:
            card = self._last
            # `data-rating=""` is printed for unrated games; keeping it
            # empty rather than coercing to 0 is the difference between
            # "nobody has rated this" and "everybody rated it zero".
            if card is not None and not card.rating:
                card.rating = attr.get("data-rating", "").strip()
        elif tag == "span" and "down-number" in classes:
            self._number_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._title_buf is not None:
            title = " ".join("".join(self._title_buf).split())
            if title and self._pending:
                self.cards.append(_Card(self._pending, title))
            self._pending = None
            self._title_buf = None
        elif tag == "a" and self._label_buf is not None:
            label = " ".join("".join(self._label_buf).split())
            card = self._last
            if card is not None and label and not card.console_label:
                card.console_label = label
            self._label_buf = None
        elif tag == "span" and self._number_buf is not None:
            card = self._last
            if card is not None and card.downloads is None:
                card.downloads = _as_int("".join(self._number_buf))
            self._number_buf = None

    def handle_data(self, data: str) -> None:
        for buf in (self._title_buf, self._label_buf, self._number_buf):
            if buf is not None:
                buf.append(data)


def parse_cards(markup: str) -> list[Entry]:
    """Every game on one page, in the order it was rendered, deduplicated.

    Deduplication is not tidiness. Webmulator's own NES index prints
    `super-mario-bros-3` three times on page 1 under three spellings of
    the title, and consecutive listing pages overlap by one card, so a
    caller that trusted the page's card count would double-count real
    games. The first spelling of a path wins, which is the one the site
    put first.

    Markup that carries no cards comes back empty rather than raising: a
    search that legitimately found nothing renders the same page with an
    empty grid, and that is a result, not a failure.
    """
    parser = _CardParser()
    parser.feed(markup or "")
    parser.close()

    out: list[Entry] = []
    seen: set[str] = set()
    for card in parser.cards:
        if card.path in seen:
            continue
        parts = split_path(card.path)
        if parts is None:          # unreachable via the parser; cheap to keep
            continue
        seen.add(card.path)
        out.append(Entry(
            path=parts[0],
            platform_seg=parts[1],
            slug=parts[2],
            title=card.title,
            console_label=card.console_label,
            rating=card.rating,
            downloads=card.downloads,
        ))
    return out


def last_page(markup: str) -> int | None:
    """The highest page number the pagination block offers, or nothing.

    Webmulator's pagination always ends in a `>>` link to the last page,
    so this is the site telling us where its own index stops rather than a
    number this plugin guessed. A page with no pagination block is a
    single-page result and returns nothing.

    It is a *hint*, not the stop condition. Asking for a page past the end
    does not 404: the server clamps and re-serves the last page, so the
    walk in `search.py` stops on "this page added nothing new" and uses
    this only to avoid asking in the first place.
    """
    numbers = [int(a or b) for a, b in _PAGE_NUMBER.findall(markup or "")]
    return max(numbers) if numbers else None


def platform_url(platform_seg: str, page: int = 1) -> str:
    """`/games/<platform>`, and `/games/<platform>/page/N` after the first.

    Page 1 omits the `/page/1` suffix, exactly as the site's own first page
    does, so a single-page walk sends the request the site itself sends.
    """
    if page > 1:
        return f"{BASE}/games/{platform_seg}/page/{int(page)}"
    return f"{BASE}/games/{platform_seg}"


def search_url(query: str, page: int = 1) -> str:
    """The site's own search shape: `/search.php?search_term_string=…`.

    That is what Webmulator's own search box submits, and page 1 omits
    `currentpage` exactly as the form does. Later pages put `currentpage`
    first, which is the order the site's own pagination links use.
    """
    params = {"search_term_string": query}
    if page > 1:
        params = {"currentpage": int(page), "search_term_string": query}
    return f"{BASE}/search.php?{urlencode(params)}"
