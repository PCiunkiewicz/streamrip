from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pathvalidate import sanitize_filename, sanitize_filepath

from streamrip.metadata.covers import Covers
from streamrip.metadata.util import safe_get

PHON_COPYRIGHT = "\u2117"
COPYRIGHT = "\u00a9"

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class AlbumInfo:
    id: str
    quality: int
    container: str
    label: str | None = None
    explicit: bool = False
    sampling_rate: int | float | None = None
    bit_depth: int | None = None
    booklets: list[dict] | None = None


@dataclass(slots=True)
class AlbumMetadata:
    info: AlbumInfo
    album: str
    albumartist: str
    year: str
    genre: list[str]
    covers: Covers
    tracktotal: int
    disctotal: int = 1
    albumcomposer: str | None = None
    copyright: str | None = None
    date: str | None = None
    description: str | None = None

    def get_genres(self) -> str:
        return ", ".join(self.genre)

    def get_copyright(self) -> str | None:
        if self.copyright is None:
            return None
        # Add special chars
        _copyright = re.sub(r"(?i)\(P\)", PHON_COPYRIGHT, self.copyright)
        _copyright = re.sub(r"(?i)\(C\)", COPYRIGHT, _copyright)
        return _copyright

    def format_folder_path(self, formatter: str) -> str:
        # Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
        # "id", and "albumcomposer",

        none_str = "Unknown"
        info: dict[str, str | int | float] = {
            "albumartist": str(sanitize_filename(self.albumartist)),
            "albumcomposer": str(sanitize_filename(self.albumcomposer or "")) or none_str,
            "bit_depth": self.info.bit_depth or none_str,
            "id": self.info.id,
            "sampling_rate": self.info.sampling_rate or none_str,
            "title": str(sanitize_filename(self.album)),
            "year": self.year,
            "container": self.info.container,
        }

        return str(sanitize_filepath(formatter.format(**info)))

    @classmethod
    def from_deezer(cls, resp: dict) -> AlbumMetadata | None:
        album = resp.get("title", "Unknown Album")
        tracktotal = int(resp.get("track_total", 0) or resp.get("nb_tracks", 0))
        disctotal = int(resp["tracks"][-1]["disk_number"])
        genres = [str(g["name"]) for g in resp["genres"]["data"]]

        date = str(resp["release_date"])
        year = date[:4]
        _copyright = None
        description = None
        albumartist = str(safe_get(resp, "artist", "name"))
        albumcomposer = None
        label = resp.get("label")
        booklets = None
        explicit = bool(resp.get("parental_warning", False) or resp.get("explicit_lyrics", False))

        # not embedded
        quality = 2
        bit_depth = 16
        sampling_rate = 44100
        container = "FLAC"

        cover_urls = Covers.from_deezer(resp)
        item_id = str(resp["id"])

        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container=container,
            label=label,
            explicit=explicit,
            sampling_rate=sampling_rate,
            bit_depth=bit_depth,
            booklets=booklets,
        )
        return AlbumMetadata(
            info,
            album,
            albumartist,
            year,
            genre=genres,
            covers=cover_urls,
            albumcomposer=albumcomposer,
            copyright=_copyright,
            date=date,
            description=description,
            disctotal=disctotal,
            tracktotal=tracktotal,
        )

    @classmethod
    def from_incomplete_deezer_track_resp(cls, resp: dict) -> AlbumMetadata | None:
        album_resp = resp["album"]
        album_id = album_resp["id"]
        album = album_resp["title"]
        covers = Covers.from_deezer(album_resp)
        date = album_resp["release_date"]
        year = date[:4]
        albumartist = ", ".join(a["name"] for a in resp["contributors"])
        explicit = resp.get("explicit_lyrics", False)

        info = AlbumInfo(
            id=album_id,
            quality=2,
            container="MP4",
            label=None,
            explicit=explicit,
            sampling_rate=None,
            bit_depth=None,
            booklets=None,
        )
        return AlbumMetadata(
            info,
            album,
            albumartist,
            year,
            genre=[],
            covers=covers,
            albumcomposer=None,
            copyright=None,
            date=date,
            description=None,
            disctotal=1,
            tracktotal=1,
        )

    @classmethod
    def from_track_resp(cls, resp: dict) -> AlbumMetadata | None:
        if "tracks" not in resp["album"]:
            return cls.from_incomplete_deezer_track_resp(resp)
        return cls.from_deezer(resp["album"])

    @classmethod
    def from_album_resp(cls, resp: dict) -> AlbumMetadata | None:
        return cls.from_deezer(resp)
