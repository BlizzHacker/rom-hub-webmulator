"""Resolve a search hit to Webmulator's own game page.

Webmulator does not have a separate `/play` route. Its emulator is an
iframe embedded on the game page itself, so `/games/<platform>/<slug>` is
both the page a visitor lands on and the page the game runs in. That means
there is one URL to return and no per-entry playability flag to consult --
unlike the Vimm plugin, which has to check whether a "Play Online" control
was captured because only some Vimm entries have one.

What is *not* returned is the target of that iframe. The player is
`https://downloads.webmulator.com/play.php?...&rom_url=%2Froms%2F<name>.zip`,
which carries a direct path to the ROM archive, and handing that back would
turn a "play this" answer into a download link the site did not offer as
one. The page is what Webmulator publishes; the page is what this returns.
`manifest.toml` does not declare `downloads.webmulator.com` at all, so the
allowlist refuses it independently of this file.

Resolving makes **no network request**. Everything needed is in the
`source_id`, and re-deriving a URL that is already determined would cost
the site a page render per resolve to learn nothing.
"""

from rom_hub_sdk import SearchResult, StreamProvider, StreamTarget

from .listing import Entry, split_path
from .platforms import platform_for


class StreamRefused(Exception):
    """The id is not a Webmulator game path this plugin will build a URL from."""


class Stream(StreamProvider):
    def resolve(self, result: SearchResult) -> StreamTarget:
        source_id = getattr(result, "source_id", "") or ""
        parts = split_path(source_id)
        if parts is None:
            # Re-validated rather than trusted, even though it is our own
            # `source_id` coming back: by the time the host calls resolve()
            # the value has been round-tripped through storage and another
            # process, and the URL built from it is one somebody's browser
            # will open.
            raise StreamRefused(
                f"{source_id!r} is not a Webmulator game path of the form "
                "'<platform>/<title-slug>'"
            )
        path, platform_seg, slug = parts
        mapped = platform_for(platform_seg)
        if mapped is None:
            # `split_path` already established that this is one of the 39
            # platforms the site publishes; this is the second question,
            # which is whether it is one this plugin answers for. neo-geo
            # and fairchild-channel-f pass the first and fail this one.
            raise StreamRefused(
                f"Webmulator platform {platform_seg!r} has no ROMarr "
                f"platform, so {path!r} is not a game this plugin answers for"
            )

        entry = Entry(
            path=path,
            platform_seg=platform_seg,
            slug=slug,
            title=result.title or path,
        )
        return StreamTarget(
            kind="url",
            target=entry.page_url,
            mime_type="text/html",
            title=entry.title,
            extra={
                "webmulator_platform": platform_seg,
                "webmulator_slug": slug,
                "platform": mapped,
                "page_url": entry.page_url,
            },
        )
