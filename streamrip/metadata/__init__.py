"""Manages the information that will be embeded in the audio file."""

from streamrip.metadata import util
from streamrip.metadata.album import AlbumInfo, AlbumMetadata
from streamrip.metadata.artist import ArtistMetadata
from streamrip.metadata.covers import Covers
from streamrip.metadata.playlist import PlaylistMetadata
from streamrip.metadata.search_results import (
    AlbumSummary,
    ArtistSummary,
    PlaylistSummary,
    SearchResults,
    Summary,
    TrackSummary,
)
from streamrip.metadata.tagger import tag_file
from streamrip.metadata.track import TrackInfo, TrackMetadata

__all__ = [
    "AlbumInfo",
    "AlbumMetadata",
    "AlbumSummary",
    "ArtistMetadata",
    "ArtistSummary",
    "Covers",
    "PlaylistMetadata",
    "PlaylistSummary",
    "SearchResults",
    "Summary",
    "TrackInfo",
    "TrackMetadata",
    "TrackSummary",
    "tag_file",
    "util",
]
