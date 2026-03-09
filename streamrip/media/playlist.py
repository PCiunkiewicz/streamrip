import asyncio
import logging
import os
from dataclasses import dataclass

from streamrip import progress
from streamrip.client import DeezerClient
from streamrip.config import Config
from streamrip.db import Database
from streamrip.exceptions import NonStreamableError
from streamrip.filepath_utils import clean_filepath
from streamrip.media.artwork import download_artwork
from streamrip.media.media import Media, Pending
from streamrip.media.track import Track
from streamrip.metadata import (
    AlbumMetadata,
    Covers,
    PlaylistMetadata,
    TrackMetadata,
)

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class PendingPlaylistTrack(Pending):
    id: str
    client: DeezerClient
    config: Config
    folder: str
    playlist_name: str
    position: int
    db: Database

    async def resolve(self) -> Track | None:
        if self.db.downloaded(self.id):
            logger.info(f"Track ({self.id}) already logged in database. Skipping.")
            return None
        try:
            resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError as e:
            logger.error(f"Could not stream track {self.id}: {e}")
            return None

        album = AlbumMetadata.from_track_resp(resp)
        if album is None:
            logger.error(
                f"Track ({self.id}) not available for stream on {self.client.source}",
            )
            self.db.set_failed(self.client.source, "track", self.id)
            return None
        meta = TrackMetadata.from_resp(album, resp)
        if meta is None:
            logger.error(
                f"Track ({self.id}) not available for stream on {self.client.source}",
            )
            self.db.set_failed(self.client.source, "track", self.id)
            return None

        c = self.config.session.metadata
        if c.renumber_playlist_tracks:
            meta.tracknumber = self.position
        if c.set_playlist_to_album:
            album.album = self.playlist_name

        quality = self.config.session.deezer.quality
        try:
            embedded_cover_path, downloadable = await asyncio.gather(
                self._download_cover(album.covers, self.folder),
                self.client.get_downloadable(self.id, quality),
            )
        except NonStreamableError as e:
            logger.error(f"Error fetching download info for track {self.id}: {e}")
            self.db.set_failed(self.client.source, "track", self.id)
            return None

        return Track(
            meta,
            downloadable,
            self.config,
            self.folder,
            embedded_cover_path,
            self.db,
        )

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path = await download_artwork(
            self.client.session,
            folder,
            covers,
            self.config.session.artwork,
        )
        return embed_path


@dataclass(slots=True)
class Playlist(Media):
    name: str
    config: Config
    client: DeezerClient
    tracks: list[PendingPlaylistTrack]

    async def preprocess(self):
        progress.add_title(self.name)

    async def postprocess(self):
        progress.remove_title(self.name)

    async def download(self):
        track_resolve_chunk_size = 20

        async def _resolve_download(item: PendingPlaylistTrack):
            try:
                track = await item.resolve()
                if track is None:
                    return
                await track.rip()
            except Exception as e:
                logger.error(f"Error downloading track: {e}")

        batches = self.batch(
            [_resolve_download(track) for track in self.tracks],
            track_resolve_chunk_size,
        )

        for batch in batches:
            results = await asyncio.gather(*batch, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Batch processing error: {result}")

    @staticmethod
    def batch(iterable, n=1):
        total = len(iterable)
        for ndx in range(0, total, n):
            yield iterable[ndx : min(ndx + n, total)]


@dataclass(slots=True)
class PendingPlaylist(Pending):
    id: str
    client: DeezerClient
    config: Config
    db: Database

    async def resolve(self) -> Playlist | None:
        try:
            resp = await self.client.get_metadata(self.id, "playlist")
        except NonStreamableError as e:
            logger.error(
                f"Playlist {self.id} not available to stream on {self.client.source} ({e})",
            )
            return None

        try:
            meta = PlaylistMetadata.from_resp(resp)
        except Exception as e:
            logger.error(f"Error creating playlist: {e}")
            return None
        name = meta.name
        parent = self.config.session.downloads.folder
        folder = os.path.join(parent, clean_filepath(name))
        tracks = [
            PendingPlaylistTrack(
                id,
                self.client,
                self.config,
                folder,
                name,
                position + 1,
                self.db,
            )
            for position, id in enumerate(meta.ids())
        ]
        return Playlist(name, self.config, self.client, tracks)
