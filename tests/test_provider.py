import pytest
from conftest import FakeHttp

from rom_hub_sdk import PluginContext

from webmulator.search import Search, _matches
from webmulator.stream import Stream, StreamRefused

SEARCH_BOMBERMAN = (
    "https://www.webmulator.com/search.php?search_term_string=bomberman"
)
SEARCH_CONTRA = "https://www.webmulator.com/search.php?search_term_string=contra"
NES_INDEX = "https://www.webmulator.com/games/nintendo"


def ctx(pages, **config):
    return PluginContext(config=config, http=FakeHttp(pages))


# --- what search returns ----------------------------------------------------


def test_search_maps_platforms_and_drops_the_unmappable(search_html):
    http = FakeHttp([(200, search_html)])
    results = Search(PluginContext(config={}, http=http)).search("bomberman", None, 20)

    # 6 cards in, 5 out: the Neo Geo hit is real and is dropped, because
    # ROMarr models neogeoaes and neogeomvs separately and nothing on the
    # page chooses. It may not be emitted under a guessed slug.
    assert [(r.source_id, r.platform) for r in results] == [
        ("sega-saturn/saturn-bomberman-e", "saturn"),
        ("sega-saturn/saturn-bomberman-j", "saturn"),
        ("sega-saturn/saturn-bomberman-u", "saturn"),
        ("nintendo-64/bomberman-64-the-second-attack", "n64"),
        ("nintendo-64/bomberman-64", "n64"),
    ]
    assert "neo-geo/neo-bomberman" not in [r.source_id for r in results]


def test_search_costs_one_request_by_default(search_html):
    http = FakeHttp([(200, search_html)])
    Search(PluginContext(config={}, http=http)).search("bomberman", None, 20)
    assert http.urls == [SEARCH_BOMBERMAN]


def test_search_carries_the_metadata_the_page_printed(search_html):
    http = FakeHttp([(200, search_html)])
    first = Search(PluginContext(config={}, http=http)).search("bomberman", None, 5)[0]
    assert first.title == "Saturn Bomberman (E)"
    assert first.url == (
        "https://www.webmulator.com/games/sega-saturn/saturn-bomberman-e"
    )
    assert first.extra["region"] == "E"
    assert first.extra["webmulator_platform"] == "sega-saturn"
    assert first.extra["console"] == "Sega Saturn"
    assert first.extra["rating"] == "3.7"
    assert first.extra["downloads"] == "6722"
    assert first.extra["playable"] == "true"
    assert first.extra["downloadable"] == "false"
    # Webmulator prints a size only on the game page itself, never on a
    # card. None is the honest answer; a zero would read as an empty file.
    assert first.size_bytes is None


# --- the padding ------------------------------------------------------------


def test_the_sites_padding_is_dropped(padded_html):
    # A live "contra" search returns one Contra game and then pads the page
    # with unrelated popular titles. Handing FIFA 2005 back as a result for
    # "contra" would put it in somebody's library under that name.
    http = FakeHttp([(200, padded_html)])
    results = Search(PluginContext(config={}, http=http)).search("contra", None, 20)
    assert [r.source_id for r in results] == ["nintendo/contra"]


def test_the_padding_is_five_of_the_six_cards_on_that_page(padded_html):
    from webmulator.listing import parse_cards
    assert len(parse_cards(padded_html)) == 6


@pytest.mark.parametrize("query,title,expected", [
    ("contra", "Contra", True),
    ("contra", "Marvel Vs.Capcom 2 New Age of Heroes", False),
    ("contra", "FIFA 2005", False),
    # Punctuation and spacing in either half are not the question.
    ("megaman", "Mega Man 2", True),
    ("mega man", "Megaman X", True),
    ("street fighter", "Street Fighter II: The World Warrior", True),
    # Order is not the question either.
    ("link zelda", "The Legend of Zelda - Link's Awakening", True),
    ("bomberman", "Mario Maze (Bomberman Hack)", True),
    # Nothing to compare: matching everything beats silently emptying the
    # result set.
    ("???", "Anything At All", True),
    ("", "Anything At All", True),
])
def test_a_title_matches_when_it_carries_the_querys_words(query, title, expected):
    assert _matches(query, title) is expected


# --- the platform filter ----------------------------------------------------


@pytest.mark.parametrize("spelling", ["saturn", "sega-saturn"])
def test_platform_filter_accepts_either_spelling(search_html, spelling, monkeypatch):
    # ROMarr's slug and Webmulator's own must both work: a caller has no
    # reason to know which one this plugin thinks in.
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    http = FakeHttp([(200, search_html), (200, "<html></html>")])
    results = Search(PluginContext(config={}, http=http)).search(
        "bomberman", spelling, 20
    )
    assert {r.source_id for r in results} == {
        "sega-saturn/saturn-bomberman-e",
        "sega-saturn/saturn-bomberman-j",
        "sega-saturn/saturn-bomberman-u",
    }
    assert http.urls == [
        SEARCH_BOMBERMAN,
        "https://www.webmulator.com/games/sega-saturn",
    ]


def test_filtering_to_a_skipped_platform_returns_nothing(search_html):
    # Asking for `neo-geo` by name must not become a way around the refusal
    # to map it -- and it must not fall through to the platform index either.
    http = FakeHttp([(200, search_html)])
    assert Search(PluginContext(config={}, http=http)).search(
        "bomberman", "neo-geo", 20
    ) == []
    assert http.urls == [SEARCH_BOMBERMAN]


# --- the second surface -----------------------------------------------------


def test_a_platform_scoped_search_also_reads_that_platforms_index(
    padded_html, listing_html, monkeypatch
):
    # `search.php` cannot be scoped and pads what it does return; the index
    # is scoped and does not pad. A platform-scoped query asks the cheap one
    # first and then tops up from the index.
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    http = FakeHttp([(200, padded_html), (200, listing_html)])
    results = Search(PluginContext(config={}, http=http)).search(
        "super mario", "nes", 20
    )
    assert http.urls == [
        "https://www.webmulator.com/search.php?search_term_string=super+mario",
        NES_INDEX,
    ]
    assert [r.source_id for r in results] == [
        "nintendo/super-mario",
        "nintendo/super-mario-bros-3",
        "nintendo/super-mario-bros-3-t-port",
    ]


def test_an_unscoped_search_never_touches_the_index(padded_html):
    http = FakeHttp([(200, padded_html)])
    Search(PluginContext(config={}, http=http)).search("contra", None, 20)
    assert http.urls == [SEARCH_CONTRA]


def test_the_index_is_not_read_once_the_limit_is_already_met(search_html):
    http = FakeHttp([(200, search_html)])
    results = Search(PluginContext(config={}, http=http)).search(
        "bomberman", "saturn", 1
    )
    assert len(results) == 1
    assert http.urls == [SEARCH_BOMBERMAN]


def test_a_romarr_slug_covering_several_platforms_shares_one_budget(monkeypatch):
    # `arcade` is four Webmulator platforms. max_pages is a budget for the
    # whole top-up, not a budget per platform, so an operator who capped it
    # at 2 gets 2 index requests and not 8.
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    empty = "<html></html>"
    http = FakeHttp([(200, empty)] * 3)
    Search(
        PluginContext(config={"max_pages": 2, "request_delay_ms": 0}, http=http)
    ).search("street fighter", "arcade", 50)
    assert http.urls == [
        "https://www.webmulator.com/search.php"
        "?search_term_string=street+fighter",
        "https://www.webmulator.com/games/capcom-play-system-1",
        "https://www.webmulator.com/games/capcom-play-system-2",
    ]


# --- pagination and politeness ---------------------------------------------


def test_a_single_page_result_is_not_paginated(search_html, monkeypatch):
    # The bomberman search says its last page is 3, so with max_pages=1 only
    # one request may be made regardless.
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    http = FakeHttp([(200, search_html)])
    Search(PluginContext(config={}, http=http)).search("bomberman", None, 100)
    assert len(http.urls) == 1


def test_pagination_follows_the_sites_own_next_page(search_html, monkeypatch):
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    http = FakeHttp([(200, search_html), (200, search_html)])
    Search(
        PluginContext(config={"max_pages": 2, "request_delay_ms": 0}, http=http)
    ).search("bomberman", None, 100)
    assert http.urls == [
        SEARCH_BOMBERMAN,
        "https://www.webmulator.com/search.php"
        "?currentpage=2&search_term_string=bomberman",
    ]


def test_the_walk_stops_when_there_is_no_pagination_block(listing_html, monkeypatch):
    # A page with no pagination block is the only page there is -- 8 of
    # Webmulator's 39 platforms fit on one. Asking for page 2 of one of
    # those is a request that can only return what we already hold.
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    single = listing_html[:listing_html.find('<div class="col-12 text-center">')]
    http = FakeHttp([(200, single)])
    Search(
        PluginContext(config={"max_pages": 5, "request_delay_ms": 0}, http=http)
    ).search("mario", None, 100)
    assert len(http.urls) == 1


def test_a_repeated_page_ends_the_walk(search_html, monkeypatch):
    # Webmulator clamps an out-of-range page number to the last page instead
    # of 404ing, so a page that adds nothing new is the end. Without this a
    # max_pages of 5 would re-read the same page four more times.
    monkeypatch.setattr("webmulator.search.time.sleep", lambda _: None)
    http = FakeHttp([(200, search_html), (200, search_html)])
    Search(
        PluginContext(config={"max_pages": 5, "request_delay_ms": 0}, http=http)
    ).search("bomberman", None, 100)
    assert len(http.urls) == 2


def test_a_refusal_stops_the_search_rather_than_being_retried():
    # 403 is an answer. Retrying or varying the request is where routing
    # around a refusal would start, so there must be no second request.
    for status in (403, 429, 503, 500):
        http = FakeHttp([(status, "")])
        assert Search(PluginContext(config={}, http=http)).search(
            "bomberman", None, 10
        ) == []
        assert len(http.urls) == 1


def test_a_refusal_also_stops_the_second_surface():
    # A refusal is an answer about the site, not about the URL. Asking a
    # different path immediately afterwards is where routing around one
    # starts, so the index top-up must not run.
    http = FakeHttp([(429, "")])
    assert Search(PluginContext(config={}, http=http)).search(
        "bomberman", "nes", 10
    ) == []
    assert len(http.urls) == 1


def test_empty_query_makes_no_request():
    http = FakeHttp([])
    assert Search(PluginContext(config={}, http=http)).search("   ", None, 10) == []
    assert http.urls == []


def test_zero_limit_makes_no_request():
    http = FakeHttp([])
    assert Search(PluginContext(config={}, http=http)).search("contra", None, 0) == []
    assert http.urls == []


def test_paginated_requests_are_spaced(search_html, monkeypatch):
    slept = []
    monkeypatch.setattr("webmulator.search.time.sleep", lambda s: slept.append(s))
    http = FakeHttp([(200, search_html), (200, search_html)])
    Search(
        PluginContext(config={"max_pages": 2}, http=http)
    ).search("bomberman", None, 100)
    assert slept == [1.5]


def test_the_delay_spans_both_surfaces(padded_html, listing_html):
    slept = []
    import webmulator.search as module
    real = module.time.sleep
    module.time.sleep = lambda s: slept.append(s)
    try:
        http = FakeHttp([(200, padded_html), (200, listing_html)])
        Search(PluginContext(config={}, http=http)).search("super mario", "nes", 20)
    finally:
        module.time.sleep = real
    # The index request is spaced from the search request, not fired the
    # instant it finishes.
    assert slept == [1.5]


def test_the_delay_has_a_floor_an_operator_cannot_configure_away(
    search_html, monkeypatch
):
    slept = []
    monkeypatch.setattr("webmulator.search.time.sleep", lambda s: slept.append(s))
    http = FakeHttp([(200, search_html), (200, search_html)])
    Search(
        PluginContext(config={"max_pages": 2, "request_delay_ms": 0}, http=http)
    ).search("bomberman", None, 100)
    assert slept == [0.5]


def test_no_delay_before_a_single_page_search(search_html, monkeypatch):
    slept = []
    monkeypatch.setattr("webmulator.search.time.sleep", lambda s: slept.append(s))
    Search(
        PluginContext(config={}, http=FakeHttp([(200, search_html)]))
    ).search("bomberman", None, 10)
    assert slept == []


def test_limit_is_honoured(search_html):
    http = FakeHttp([(200, search_html)])
    assert len(
        Search(PluginContext(config={}, http=http)).search("bomberman", None, 2)
    ) == 2


def test_garbage_config_falls_back_instead_of_raising(search_html):
    http = FakeHttp([(200, search_html)])
    results = Search(
        PluginContext(config={"max_pages": "lots", "request_delay_ms": "soon"}, http=http)
    ).search("bomberman", None, 20)
    assert len(results) == 5


# --- stream -----------------------------------------------------------------


def result(source_id, title="Super Mario"):
    return type("SR", (), {"source_id": source_id, "title": title})()


def test_stream_returns_webmulators_own_game_page():
    target = Stream(PluginContext(config={}, http=None)).resolve(
        result("nintendo/super-mario")
    )
    assert target.kind == "url"
    assert target.target == "https://www.webmulator.com/games/nintendo/super-mario"
    assert target.mime_type == "text/html"
    assert target.extra["platform"] == "nes"
    assert target.extra["webmulator_platform"] == "nintendo"


def test_stream_never_returns_the_download_host():
    # The game page embeds play.php on downloads.webmulator.com, whose query
    # string carries a direct path to the .zip. Handing that back would turn
    # "play" into a download link the site did not offer as one -- and
    # manifest.toml does not declare that host either.
    target = Stream(PluginContext(config={}, http=None)).resolve(
        result("nintendo/super-mario")
    )
    assert "downloads.webmulator.com" not in target.target
    assert ".zip" not in target.target
    assert "play.php" not in target.target


@pytest.mark.parametrize("bad", [
    "", "nintendo", "../../etc/passwd", "https://evil.example/x",
    "nintendo/super-mario/../../admin", "evil.example/nintendo/super-mario",
    "evil/super-mario", "nintendo/page",
])
def test_stream_revalidates_the_id_it_is_handed(bad):
    with pytest.raises(StreamRefused):
        Stream(PluginContext(config={}, http=None)).resolve(result(bad))


def test_stream_refuses_a_platform_with_no_romarr_slug():
    for path, platform in (
        ("neo-geo/neo-bomberman", "neo-geo"),
        ("fairchild-channel-f/alien-invasion", "fairchild-channel-f"),
    ):
        with pytest.raises(StreamRefused, match=platform):
            Stream(PluginContext(config={}, http=None)).resolve(result(path))


def test_stream_makes_no_network_request():
    # ctx.http is None here: resolving must be pure URL construction.
    Stream(PluginContext(config={}, http=None)).resolve(
        result("sega-saturn/saturn-bomberman-e")
    )


def test_stream_round_trips_a_search_result(search_html):
    http = FakeHttp([(200, search_html)])
    first = Search(PluginContext(config={}, http=http)).search("bomberman", None, 1)[0]
    target = Stream(PluginContext(config={}, http=None)).resolve(first)
    assert target.target == first.url
