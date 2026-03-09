from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from streamrip.client import DeezerClient
from streamrip.config import Config
from streamrip.db import Database
from streamrip.media import (
    Pending,
    PendingAlbum,
    PendingArtist,
    PendingLabel,
    PendingPlaylist,
    PendingSingle,
)

logger = logging.getLogger("streamrip")
URL_REGEX = re.compile(
    r"https?://(?:www|open|play|listen)?\.?(deezer)\.com?(?:(?:/(album|artist|track|playlist|video|label))|(?:\/[-\w]+?))+\/([-\w]+)",
)


class URL(ABC):
    match: re.Match
    source: str

    def __init__(self, match: re.Match, source: str):
        self.match = match
        self.source = source

    @classmethod
    @abstractmethod
    def from_str(cls, url: str) -> URL | None:
        raise NotImplementedError

    @abstractmethod
    async def into_pending(
        self,
        client: DeezerClient,
        config: Config,
        db: Database,
    ) -> Pending:
        raise NotImplementedError


class DeezerURL(URL):
    @classmethod
    def from_str(cls, url: str) -> URL | None:
        generic_url = URL_REGEX.match(url)
        if generic_url is None:
            return None

        source, media_type, item_id = generic_url.groups()
        if source is None or media_type is None or item_id is None:
            return None

        return cls(generic_url, source)

    async def into_pending(
        self,
        client: DeezerClient,
        config: Config,
        db: Database,
    ) -> Pending:
        source, media_type, item_id = self.match.groups()
        assert client.source == source

        if media_type == "track":
            return PendingSingle(item_id, client, config, db)
        elif media_type == "album":
            return PendingAlbum(item_id, client, config, db)
        elif media_type == "playlist":
            return PendingPlaylist(item_id, client, config, db)
        elif media_type == "artist":
            return PendingArtist(item_id, client, config, db)
        elif media_type == "label":
            return PendingLabel(item_id, client, config, db)
        raise NotImplementedError


class DeezerDynamicURL(URL):
    standard_link_re = re.compile(
        r"https://www\.deezer\.com/[a-z]{2}/(album|artist|playlist|track)/(\d+)"
    )
    dynamic_link_re = re.compile(r"https://(?:deezer|dzr)\.page\.link/\w+")

    @classmethod
    def from_str(cls, url: str) -> URL | None:
        match = cls.dynamic_link_re.match(url)
        if match is None:
            return None

        return cls(match, "deezer")

    async def into_pending(
        self,
        client: DeezerClient,
        config: Config,
        db: Database,
    ) -> Pending:
        url = self.match.group(0)  # entire dynamic link
        media_type, item_id = await self._extract_info_from_dynamic_link(url, client)
        if media_type == "track":
            return PendingSingle(item_id, client, config, db)
        elif media_type == "album":
            return PendingAlbum(item_id, client, config, db)
        elif media_type == "playlist":
            return PendingPlaylist(item_id, client, config, db)
        elif media_type == "artist":
            return PendingArtist(item_id, client, config, db)
        elif media_type == "label":
            return PendingLabel(item_id, client, config, db)
        raise NotImplementedError

    @classmethod
    async def _extract_info_from_dynamic_link(
        cls, url: str, client: DeezerClient
    ) -> tuple[str, str]:
        """Extract the item's type and ID from a dynamic link.

        :param url:
        :type url: str
        :rtype: Tuple[str, str] (media type, item id)
        """
        async with client.session.get(url) as resp:
            match = cls.standard_link_re.search(await resp.text())

        if match:
            return match.group(1), match.group(2)

        raise Exception("Unable to extract Deezer dynamic link.")


def parse_url(url: str) -> URL | None:
    """Return a URL type given a url string.

    Args:
    ----
        url (str): Url to parse

    Returns: A URL type, or None if nothing matched.
    """
    url = url.strip()
    parsed_urls: list[URL | None] = [
        DeezerURL.from_str(url),
        DeezerDynamicURL.from_str(url),
        # TODO: the rest of the url types
    ]
    return next((u for u in parsed_urls if u is not None), None)
