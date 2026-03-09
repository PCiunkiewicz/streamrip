from __future__ import annotations

import logging
from dataclasses import dataclass

from streamrip.metadata.album import AlbumMetadata

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class TrackInfo:
    id: str
    quality: int

    bit_depth: int | None = None
    explicit: bool = False
    sampling_rate: int | float | None = None
    work: str | None = None


@dataclass(slots=True)
class TrackMetadata:
    info: TrackInfo

    title: str
    album: AlbumMetadata
    artist: str
    tracknumber: int
    discnumber: int
    composer: str | None
    isrc: str | None = None
    lyrics: str | None = ""

    @classmethod
    def from_deezer(cls, album: AlbumMetadata, resp) -> TrackMetadata | None:
        track_id = str(resp["id"])
        isrc = str(resp["isrc"])
        bit_depth = 16
        sampling_rate = 44.1
        explicit = bool(resp["explicit_lyrics"])
        work = None
        title = str(resp["title"])
        artist = str(resp["artist"]["name"])
        tracknumber = int(resp["track_position"])
        discnumber = int(resp["disk_number"])
        composer = None
        info = TrackInfo(
            id=track_id,
            quality=album.info.quality,
            bit_depth=bit_depth,
            explicit=explicit,
            sampling_rate=sampling_rate,
            work=work,
        )
        return cls(
            info=info,
            title=title,
            album=album,
            artist=artist,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
            isrc=isrc,
        )

    @classmethod
    def from_resp(cls, album: AlbumMetadata, resp) -> TrackMetadata | None:
        return cls.from_deezer(album, resp)

    def format_track_path(self, format_string: str) -> str:
        # Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
        # and "explicit", "albumcomposer"
        none_text = "Unknown"
        info = {
            "title": self.title,
            "tracknumber": self.tracknumber,
            "artist": self.artist,
            "albumartist": self.album.albumartist,
            "albumcomposer": self.album.albumcomposer or none_text,
            "composer": self.composer or none_text,
            "explicit": " (Explicit) " if self.info.explicit else "",
        }
        return format_string.format(**info)
