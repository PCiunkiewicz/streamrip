import asyncio
import logging
import os
import shutil

import aiohttp

from streamrip.client import BasicDownloadable
from streamrip.config import ArtworkConfig
from streamrip.metadata import Covers

_artwork_tempdirs: set[str] = set()

logger = logging.getLogger("streamrip")


def remove_artwork_tempdirs():
    logger.debug("Removing dirs %s", _artwork_tempdirs)
    for path in _artwork_tempdirs:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass


async def download_artwork(
    session: aiohttp.ClientSession,
    folder: str,
    covers: Covers,
    config: ArtworkConfig,
) -> str | None:
    """Download artwork and update passed Covers object with filepaths.

    If paths for the selected sizes already exist in `covers`, nothing will
    be downloaded.

    If `for_playlist` is set, it will not download hires cover art regardless
    of the config setting.

    Embedded artworks are put in a temporary directory under `folder` called
    "__embed" that can be deleted once a playlist or album is done downloading.

    Hi-res (saved) artworks are kept in `folder` as "cover.jpg".

    Args:
    ----
        session (aiohttp.ClientSession):
        folder (str):
        covers (Covers):
        config (ArtworkConfig):

    Returns:
    -------
        (path to embedded artwork, path to hires artwork)
    """
    if not config.embed or covers.empty():
        # No need to download anything
        return None

    downloadables = []

    _, embed_url, embed_cover_path = covers.get_size(config.embed_size)
    if embed_cover_path is None and config.embed:
        assert embed_url is not None
        embed_dir = os.path.join(folder, "__artwork")
        os.makedirs(embed_dir, exist_ok=True)
        _artwork_tempdirs.add(embed_dir)
        embed_cover_path = os.path.join(embed_dir, f"cover{hash(embed_url)}.jpg")
        downloadables.append(
            BasicDownloadable(session, embed_url, "jpg").download(
                embed_cover_path,
                lambda _: None,
            ),
        )

    if len(downloadables) == 0:
        return embed_cover_path

    try:
        await asyncio.gather(*downloadables)
    except Exception as e:
        logger.error(f"Error downloading artwork: {e}")
        return None

    if config.embed:
        assert embed_cover_path is not None
        covers.set_path(config.embed_size, embed_cover_path)

    return embed_cover_path
