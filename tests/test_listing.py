import pytest

from webmulator.listing import (
    Entry,
    last_page,
    parse_cards,
    platform_url,
    search_url,
    split_path,
)


# --- the per-platform index -------------------------------------------------


def test_parses_every_real_card_on_a_listing_page(listing_html):
    assert [e.path for e in parse_cards(listing_html)] == [
        "nintendo/super-mario",
        "nintendo/super-mario-bros-3",
        "nintendo/super-mario-bros-3-t-port",
        "nintendo/the-legend-of-zelda",
        "nintendo/new-strange-mario-bros-smb1-hack",
    ]


def test_the_sites_own_duplicate_collapses_to_one_game(listing_html):
    # The real page prints super-mario-bros-3 twice, as "Super Mario Bros. 3"
    # and again as "Super Mario Bros 3". Six cards render; five games exist.
    entries = parse_cards(listing_html)
    assert len(entries) == 5
    assert listing_html.count('class="roms-title"') == 6
    assert [e.title for e in entries][1] == "Super Mario Bros. 3"


def test_a_listing_card_carries_its_rating_and_download_count(listing_html):
    first = parse_cards(listing_html)[0]
    assert first.title == "Super Mario"
    assert first.rating == "4.4"
    assert first.downloads == 15259
    # The per-platform index does not print a console label -- the platform
    # is the URL. Empty, not invented.
    assert first.console_label == ""


def test_a_rating_attaches_to_the_card_whose_heading_opened_it(listing_html):
    # The two super-mario-bros-3 cards carry different ratings -- "5" on the
    # first and "" on its twin. Getting this wrong is invisible in the happy
    # case and shows up as every value shifted by one card, so it is pinned
    # against a page that really does have a mismatched pair.
    assert '"5"' in listing_html and 'data-rating=""' in listing_html
    by_path = {e.path: e for e in parse_cards(listing_html)}
    assert by_path["nintendo/super-mario-bros-3"].rating == "5"
    assert by_path["nintendo/super-mario"].rating == "4.4"


def test_an_unrated_game_keeps_an_empty_rating_rather_than_a_zero():
    # data-rating="" is what the site prints for a game nobody has rated.
    # Coercing it to 0 would claim everybody rated it badly.
    markup = (
        '<a href="/games/nintendo/contra"><h2 class="roms-title">Contra</h2></a>'
        '<div class="list-rom-rating" data-rating=""></div>'
    )
    assert parse_cards(markup)[0].rating == ""


# --- the search surface -----------------------------------------------------


def test_parses_every_real_card_on_a_search_page(search_html):
    assert [e.path for e in parse_cards(search_html)] == [
        "sega-saturn/saturn-bomberman-e",
        "neo-geo/neo-bomberman",
        "sega-saturn/saturn-bomberman-j",
        "sega-saturn/saturn-bomberman-u",
        "nintendo-64/bomberman-64-the-second-attack",
        "nintendo-64/bomberman-64",
    ]


def test_a_search_card_carries_the_console_label_the_site_printed(search_html):
    first = parse_cards(search_html)[0]
    assert first.title == "Saturn Bomberman (E)"
    assert first.console_label == "Sega Saturn"
    assert first.rating == "3.7"
    assert first.downloads == 6722


def test_the_console_button_is_not_mistaken_for_a_game(search_html):
    # Each search card contains <a href="/games/sega-saturn"> as its console
    # button. Two segments make a game; one does not.
    assert all("/" in e.path.strip("/") for e in parse_cards(search_html))
    assert "sega-saturn" not in [e.path for e in parse_cards(search_html)]


def test_both_layouts_parse_with_one_parser(listing_html, search_html):
    # The anchor wraps the card on one surface and sits inside it on the
    # other. If that ever needed two parsers, this is the test that says so.
    assert parse_cards(listing_html) and parse_cards(search_html)


# --- region -----------------------------------------------------------------


def test_region_comes_from_the_first_parenthesised_group():
    assert Entry("nintendo/x", "nintendo", "x", "Contra (USA)").region == "USA"
    # Dump flags follow the region; only the first group is the region.
    assert Entry("nintendo-ds/y", "nintendo-ds", "y",
                 "Puyo Pop Fever (J)(M2)").region == "J"
    assert Entry("nintendo/z", "nintendo", "z", "Contraption").region == ""


# --- path validation --------------------------------------------------------


def test_urls_are_built_from_the_validated_path():
    entry = Entry("nintendo/super-mario", "nintendo", "super-mario", "Super Mario")
    assert entry.page_url == "https://www.webmulator.com/games/nintendo/super-mario"


@pytest.mark.parametrize("path", [
    "nintendo/super-mario",
    "nintendo/1200-in-1-j",                 # slugs really do start with a digit
    "atari-2600/x-man-1983-cosmovision-universal-gamex",
    "capcom-play-system-3/street-fighter-iii-3rd-strike",
    "magnavox-odissey-2/kc-munchkin",
    "neo-geo/neo-bomberman",                # a real path this plugin will not map
])
def test_accepts_real_survey_shapes(path):
    assert split_path(path) is not None


@pytest.mark.parametrize("path", [
    "",
    "nintendo",                             # no game slug
    "nintendo/super-mario/play",            # a tail is not a match
    "../../etc/passwd",
    "nintendo/super-mario?x=1",
    "nintendo/super-mario#frag",
    "https://evil.example/games/nintendo/x",
    "NINTENDO/Super-Mario/../../x",
])
def test_rejects_anything_that_is_not_exactly_a_game_path(path):
    assert split_path(path) is None


def test_a_platform_the_site_does_not_publish_is_not_a_game_path():
    # Shape alone is not enough. `/games/evil/x` is shaped like a game path
    # and is not one, and only the second question keeps a crafted href from
    # becoming a URL on a route that does not exist.
    assert split_path("evil/x") is None
    assert split_path("nes/super-mario") is None        # a real console, not a
    assert split_path("snes/super-mario") is None       # Webmulator platform
    assert split_path("nintendo/super-mario") is not None


def test_a_pagination_path_is_not_a_game():
    assert split_path("nintendo/page") is None


def test_path_matching_is_anchored_not_a_search():
    assert split_path("evil.example/nintendo/super-mario") is None
    assert split_path("nintendo/super-mario/../../admin") is None


def test_case_is_folded_so_one_game_has_one_id():
    assert split_path("NINTENDO/Super-Mario")[0] == "nintendo/super-mario"


def test_pages_without_cards_are_empty_not_an_error():
    assert parse_cards("") == []
    assert parse_cards("<html><body>no results</body></html>") == []
    assert parse_cards('<h2 class="roms-title">Orphan</h2>') == []


def test_a_heading_with_no_game_link_before_it_is_not_a_game():
    # Every platform index ends in prose headings like
    # "<h2>Nintendo Entertainment System Games</h2>". They carry no
    # roms-title class and no pending path, and must not become entries.
    markup = (
        '<a href="/games/nintendo/contra"><h2 class="roms-title">Contra</h2></a>'
        "<h2>Nintendo Entertainment System Games</h2>"
    )
    assert [e.path for e in parse_cards(markup)] == ["nintendo/contra"]


def test_a_foreign_href_never_becomes_an_entry():
    markup = (
        '<a href="https://evil.example/games/nintendo/x">'
        '<h2 class="roms-title">Evil</h2></a>'
    )
    assert parse_cards(markup) == []


# --- pagination -------------------------------------------------------------


def test_last_page_reads_the_platform_indexs_own_pagination(listing_html):
    # The real NES index stops at page 100 and says so in its `>>` link.
    assert last_page(listing_html) == 100


def test_last_page_reads_the_search_pages_pagination(search_html, padded_html):
    assert last_page(search_html) == 3
    assert last_page(padded_html) == 4


def test_no_pagination_block_means_a_single_page():
    assert last_page("<html></html>") is None
    assert last_page("") is None


def test_page_one_omits_the_page_suffix():
    # Page 1 must be the request the site's own links send.
    assert platform_url("nintendo") == "https://www.webmulator.com/games/nintendo"
    assert platform_url("nintendo", 1) == "https://www.webmulator.com/games/nintendo"


def test_later_listing_pages_use_the_sites_own_shape():
    assert platform_url("nintendo", 2) == (
        "https://www.webmulator.com/games/nintendo/page/2"
    )


def test_page_one_of_a_search_is_what_the_search_box_submits():
    assert search_url("contra") == (
        "https://www.webmulator.com/search.php?search_term_string=contra"
    )


def test_later_search_pages_use_the_sites_own_shape():
    assert search_url("contra", 2) == (
        "https://www.webmulator.com/search.php"
        "?currentpage=2&search_term_string=contra"
    )


def test_query_is_url_encoded():
    assert "search_term_string=mike+tyson%27s" in search_url("mike tyson's")
