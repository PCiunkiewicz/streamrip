import asyncio
import logging
import os
from dataclasses import dataclass

from pathvalidate import sanitize_filepath

from streamrip import progress
from streamrip.client import DeezerClient
from streamrip.config import Config
from streamrip.db import Database
from streamrip.exceptions import NonStreamableError
from streamrip.media.artwork import download_artwork
from streamrip.media.media import Media, Pending
from streamrip.media.track import PendingTrack
from streamrip.metadata import AlbumMetadata
from streamrip.metadata.util import get_album_track_ids

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class Album(Media):
    meta: AlbumMetadata
    tracks: list[PendingTrack]
    config: Config
    # folder where the tracks will be downloaded
    folder: str
    db: Database

    async def preprocess(self):
        progress.add_title(self.meta.album)

    async def download(self):
        async def _resolve_and_download(pending: Pending):
            try:
                track = await pending.resolve()
                if track is None:
                    return
                await track.rip()
            except Exception as e:
                logger.error(f"Error downloading track: {e}")

        os.makedirs(self.folder, exist_ok=True)
        results = await asyncio.gather(*[_resolve_and_download(p) for p in self.tracks], return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Album track processing error: {result}")

    async def postprocess(self):
        progress.remove_title(self.meta.album)


@dataclass(slots=True)
class PendingAlbum(Pending):
    id: str
    client: DeezerClient
    config: Config
    db: Database

    async def resolve(self) -> Album | None:
        try:
            resp = await self.client.get_metadata(self.id, "album")
        except NonStreamableError as e:
            logger.error(
                f"Album {self.id} not available to stream on Deezer ({e})",
            )
            return None

        try:
            meta = AlbumMetadata.from_album_resp(resp)
        except Exception as e:
            logger.error(f"Error building album metadata for {id=}: {e}")
            return None

        if meta is None:
            logger.error(
                f"Album {self.id} not available to stream on Deezer",
            )
            return None

        tracklist = get_album_track_ids(resp)
        folder = self.config.session.downloads.folder
        album_folder = self._album_folder(folder, meta)
        embed_cover = await download_artwork(
            self.client.session,
            folder,
            meta.covers,
        )
        pending_tracks = [
            PendingTrack(
                id,
                album=meta,
                client=self.client,
                config=self.config,
                folder=album_folder,
                db=self.db,
                cover_path=embed_cover,
            )
            for id in tracklist
        ]
        logger.debug("Pending tracks: %s", pending_tracks)
        return Album(meta, pending_tracks, self.config, album_folder, self.db)

    def _album_folder(self, parent: str, meta: AlbumMetadata) -> str:
        config = self.config.session
        formatter = config.filepaths.folder_format
        folder = str(sanitize_filepath(meta.format_folder_path(formatter)))

        return os.path.join(parent, folder)
