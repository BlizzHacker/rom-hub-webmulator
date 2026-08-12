"""Search Webmulator, through the two surfaces the site publishes.

`GET /search.php?search_term_string=<q>` is what Webmulator's own search
box submits, so a query here costs the site exactly one page render -- the
same one a visitor's search costs. That is the first surface and it covers
the whole catalogue.

The second is the per-platform index, `/games/<platform>[/page/N]`. It is
read **only when the caller asked for a platform**, and only after the
site's own search has been asked first, because it answers a different
question: `search.php` searches everything and cannot be scoped, while the
index is scoped and cannot be searched. Together, a platform-scoped query
costs at most `max_pages` requests to each -- two, by default.

Why the site's own results are filtered
---------------------------------------

Webmulator's search returns its real matches and then **pads the page out
with unrelated popular titles**. A live `search.php?search_term_string=contra`
on 2026-08-12 returned twelve cards of which exactly one was a Contra game;
the other eleven were Marvel Vs. Capcom 2, House of the Dead 2, Sonic Rush,
Phoenix Wright, FIFA 2005 and so on. A nonsense query (`zzqqxwv`) returns
**zero** cards, which is what proves the eleven are padding rather than a
fuzzy match that happened to be generous -- a fuzzy matcher with that much
slack would have matched the nonsense too.

So `_matches` drops a card whose title does not contain the query's words.
That is not a re-ranking of the site's relevance order, which is left
exactly as served; it is dropping rows the site itself did not claim were
matches. Handing "FIFA 2005" back as a result for "contra" would put it in
somebody's library under that name.

The comparison is deliberately loose -- letters and digits only, so
"megaman" finds "Mega Man 2" and "street fighter" finds "Street Fighter II"
-- because the failure modes are not symmetric. Keeping one pad row costs a
caller one bad line; dropping one real hit costs them the game.

Results whose platform has no ROMarr slug are **dropped, not renamed**.
`platform_for` returning nothing is a decision, and honouring it here is
what keeps a Neo Geo romset out of some other machine's folder.
"""

from __future__ import annotations

import re
import time

from rom_hub_sdk import SearchProvider, SearchResult

from .listing import last_page, parse_cards, platform_url, search_url
from .platforms import platform_for, webmulator_platforms_for

#: Floor on the configured delay, in milliseconds. An operator can raise
#: the gap between requests but not remove it -- the value exists to be
#: polite to a site that has not asked us for anything (its `robots.txt` is
#: `User-agent: * / Disallow:`, with no `Crawl-delay`), and a configurable
#: zero would quietly turn that off.
MIN_DELAY_MS = 500

#: The default, matching `manifest.toml`. Milliseconds rather than seconds
#: because RPP v1 has no `float` config type -- a manifest declaring one is
#: rejected by `parse_manifest`, so a fractional-second knob has to be an
#: integer count of something smaller.
DEFAULT_DELAY_MS = 1500

_WORDS = re.compile(r"[a-z0-9]+")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def _matches(query: str, title: str) -> bool:
    """Does this title actually answer the query?

    Every alphanumeric run in the query must appear somewhere in the
    title once both are reduced to bare letters and digits. Order does not
    matter, so "link zelda" finds "The Legend of Zelda - Link's Awakening",
    and punctuation does not either, so "megaman" finds "Mega Man 2".

    A query with no alphanumerics at all (`"???"`) matches everything,
    because there is nothing to compare and inventing a verdict would
    silently empty the result set.
    """
    terms = _WORDS.findall((query or "").casefold())
    if not terms:
        return True
    flat = _NOT_ALNUM.sub("", (title or "").casefold())
    return all(term in flat for term in terms)


class _Walk:
    """One paginated read, and the politeness that goes with it.

    Carries the delay across *both* surfaces so a platform-scoped search
    that reads `search.php` and then a listing still spaces its requests;
    a per-surface delay would have let the second surface start
    immediately after the first finished.

    `refused` is sticky. A non-200 -- 403, 429, 503 -- stops this walk and
    also stops the walk that would have followed it, because a refusal is
    an answer about the site rather than about the URL, and asking a
    different path immediately afterwards is where routing around one
    starts.
    """

    __slots__ = ("http", "delay", "requests", "refused")

    def __init__(self, http, delay: float) -> None:
        self.http = http
        self.delay = delay
        self.requests = 0
        self.refused = False

    def pages(self, url_for, max_pages: int):
        """Yield `(entries, markup)` per page until there is no next one."""
        for page in range(1, max_pages + 1):
            if self.refused:
                return
            if self.requests:
                # Between requests, never before the first one: a lone
                # search should not sit still for a second and a half to
                # pay for a page it is not going to ask for.
                time.sleep(self.delay)
            self.requests += 1
            response = self.http.get(url_for(page))
            if response.status_code != 200:
                self.refused = True
                return
            entries = parse_cards(response.text)
            if not entries:
                return
            yield entries
            end = last_page(response.text)
            # No pagination block, or we are standing on the last page.
            # Asking past the end does not 404 here -- the server clamps
            # and re-serves the last page -- so this avoids a request that
            # would have returned rows already collected.
            if end is None or page >= end:
                return


class Search(SearchProvider):
    def search(self, query: str, platform: str | None, limit: int) -> list[SearchResult]:
        limit = max(0, limit)
        text = (query or "").strip()
        if not text or not limit:
            return []

        config = self.ctx.config or {}
        try:
            max_pages = max(1, int(config.get("max_pages", 1)))
        except (TypeError, ValueError):
            max_pages = 1
        try:
            delay_ms = max(
                MIN_DELAY_MS, int(config.get("request_delay_ms", DEFAULT_DELAY_MS))
            )
        except (TypeError, ValueError):
            delay_ms = DEFAULT_DELAY_MS
        delay = delay_ms / 1000.0

        wanted = str(platform or "").strip().casefold()
        # Both spellings of a platform filter are accepted -- ROMarr's slug
        # and Webmulator's own -- because a caller has no reason to know
        # which one this plugin thinks in.
        scoped = webmulator_platforms_for(wanted)

        walk = _Walk(self.ctx.http, delay)
        results: list[SearchResult] = []
        seen: set[str] = set()

        # 1. The site's own search: one request, the whole catalogue.
        self._harvest(
            walk.pages(lambda page: search_url(text, page), max_pages),
            text, wanted, scoped, results, seen, limit,
        )

        # 2. The platform's own index, if a platform was asked for and the
        #    site's search did not fill the request. `search.php` cannot be
        #    scoped, so on a narrow platform this is often where the answer
        #    is -- and it is the surface that does not pad.
        #
        #    Bounded by the same `max_pages` *in total*, not per platform:
        #    `arcade` is four Webmulator platforms and a per-platform bound
        #    would quietly quadruple what an operator thought they capped.
        if scoped and len(results) < limit and not walk.refused:
            budget = max_pages
            for platform_seg in scoped:
                if budget <= 0 or len(results) >= limit or walk.refused:
                    break
                before = walk.requests
                self._harvest(
                    walk.pages(
                        lambda page, seg=platform_seg: platform_url(seg, page),
                        budget,
                    ),
                    text, wanted, scoped, results, seen, limit,
                )
                budget -= walk.requests - before

        return results[:limit]

    def _harvest(self, pages, text, wanted, scoped, results, seen, limit) -> None:
        for entries in pages:
            fresh = 0
            for entry in entries:
                if entry.path in seen:
                    continue
                seen.add(entry.path)
                fresh += 1
                mapped = platform_for(entry.platform_seg)
                if mapped is None:
                    continue
                if wanted and wanted not in (
                    mapped.casefold(), entry.platform_seg
                ):
                    continue
                if not _matches(text, entry.title):
                    continue
                results.append(SearchResult(
                    source_id=entry.path,
                    title=entry.title,
                    platform=mapped,
                    # Webmulator prints a file size, but only on the game
                    # page itself (`<meta itemprop="fileSize">`), never on
                    # a card. Reading it would cost one extra request per
                    # result to answer a question nobody asked. None means
                    # unknown; a zero would read as an empty file.
                    size_bytes=None,
                    url=entry.page_url,
                    extra={
                        "region": entry.region,
                        "webmulator_platform": entry.platform_seg,
                        "console": entry.console_label,
                        "rating": entry.rating,
                        "downloads": str(entry.downloads or ""),
                        # Every game has a player embedded on its own page;
                        # none has an import path. Saying so per result
                        # saves the caller from discovering it at
                        # `stream`/import time.
                        "playable": "true",
                        "downloadable": "false",
                    },
                ))
                if len(results) >= limit:
                    return
            # A page that repeated what the last one held is the end of the
            # index -- Webmulator clamps an out-of-range page number to the
            # last page rather than 404ing, so without this a max_pages of
            # 20 against a 3-page platform would re-read page 3 seventeen
            # times.
            if not fresh:
                return
