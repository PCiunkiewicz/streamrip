import asyncio
import logging
import os
import shutil

import aiohttp

from streamrip.client import BasicDownloadable
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


async def download_artwork(session: aiohttp.ClientSession, folder: str, covers: Covers) -> str | None:
    """Download artwork and update passed Covers object with filepaths.

    Args:
    ----
        session (aiohttp.ClientSession):
        folder (str):
        covers (Covers):

    Returns:
    -------
        (path to embedded artwork, path to hires artwork)
    """
    if covers.empty():
        return None

    downloadables = []

    if covers.path is None:
        assert covers.url is not None
        embed_dir = os.path.join(folder, "__artwork")
        os.makedirs(embed_dir, exist_ok=True)
        _artwork_tempdirs.add(embed_dir)
        covers.path = os.path.join(embed_dir, f"cover{hash(covers.url)}.jpg")
        downloadables.append(
            BasicDownloadable(session, covers.url, "jpg").download(
                covers.path,
                lambda _: None,
            ),
        )

    if len(downloadables) == 0:
        return covers.path

    try:
        await asyncio.gather(*downloadables)
    except Exception as e:
        logger.error(f"Error downloading artwork: {e}")
        return None

    return covers.path
