"""Classes and functions that manage config state."""

import copy
import logging
import os
import shutil
from dataclasses import dataclass, fields
from pathlib import Path

import click
from tomlkit.api import dumps, parse
from tomlkit.toml_document import TOMLDocument

logger = logging.getLogger("streamrip")

HOME = Path.home()
APP_DIR = click.get_app_dir("streamrip")
os.makedirs(APP_DIR, exist_ok=True)

DEFAULT_CONFIG_PATH = os.path.join(APP_DIR, "config.toml")
DEFAULT_DOWNLOADS_FOLDER = os.path.join(HOME, "StreamripDownloads")
DEFAULT_DOWNLOADS_DB_PATH = os.path.join(APP_DIR, "downloads.db")
DEFAULT_FAILED_DOWNLOADS_DB_PATH = os.path.join(APP_DIR, "failed_downloads.db")

BLANK_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")


@dataclass(slots=True)
class DeezerConfig:
    # An authentication cookie that allows streamrip to use your Deezer account
    # See https://github.com/nathom/streamrip/wiki/Finding-Your-Deezer-ARL-Cookie
    # for instructions on how to find this
    arl: str
    # 0, 1, or 2
    quality: int
    # If the target quality is not available, fallback to best quality available
    lower_quality_if_not_available: bool


@dataclass(slots=True)
class DatabaseConfig:
    downloads_enabled: bool
    downloads_path: str
    failed_downloads_enabled: bool
    failed_downloads_path: str


@dataclass(slots=True)
class MetadataConfig:
    # Sets the value of the 'ALBUM' field in the metadata to the playlist's name.
    # This is useful if your music library software organizes tracks based on album name.
    set_playlist_to_album: bool
    # If part of a playlist, sets the `tracknumber` field in the metadata to the track's
    # position in the playlist instead of its position in its album
    renumber_playlist_tracks: bool


@dataclass(slots=True)
class FilepathsConfig:
    # Create folders for single tracks within the downloads directory using the folder_format
    # template
    add_singles_to_folder: bool
    # Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
    # "container", "id", and "albumcomposer"
    folder_format: str
    # Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
    # and "albumcomposer"
    track_format: str
    # Truncate the filename if it is greater than 120 characters
    # Setting this to false may cause downloads to fail on some systems
    truncate_to: int


@dataclass(slots=True)
class DownloadsConfig:
    # Folder where tracks are downloaded to
    folder: str
    # Download tracks all at once, instead of sequentially.
    concurrency: bool
    # The maximum number of tracks to download at once
    # If you have very fast internet, you will benefit from a higher value,
    # A value that is too high for your bandwidth may cause slowdowns
    max_connections: int
    # Verify SSL certificates for API connections
    # Set to false if you encounter SSL certificate verification errors (not recommended)
    verify_ssl: bool


@dataclass(slots=True)
class CliConfig:
    # Show resolve, download progress bars
    progress_bars: bool
    # The maximum number of search results to show in the interactive menu
    max_search_results: int


@dataclass(slots=True)
class ConfigData:
    toml: TOMLDocument
    downloads: DownloadsConfig
    deezer: DeezerConfig

    filepaths: FilepathsConfig
    metadata: MetadataConfig

    cli: CliConfig
    database: DatabaseConfig

    _modified: bool = False

    @classmethod
    def from_toml(cls, toml_str: str):
        # TODO: handle the mistake where Windows people forget to escape backslash
        toml = parse(toml_str)
        downloads = DownloadsConfig(**toml["downloads"])  # type: ignore
        deezer = DeezerConfig(**toml["deezer"])  # type: ignore
        filepaths = FilepathsConfig(**toml["filepaths"])  # type: ignore
        metadata = MetadataConfig(**toml["metadata"])  # type: ignore
        cli = CliConfig(**toml["cli"])  # type: ignore
        database = DatabaseConfig(**toml["database"])  # type: ignore

        return cls(
            toml=toml,
            downloads=downloads,
            deezer=deezer,
            filepaths=filepaths,
            metadata=metadata,
            cli=cli,
            database=database,
        )

    def set_modified(self):
        self._modified = True

    @property
    def modified(self):
        return self._modified

    def update_toml(self):
        update_toml_section_from_config(self.toml["downloads"], self.downloads)
        update_toml_section_from_config(self.toml["deezer"], self.deezer)
        update_toml_section_from_config(self.toml["filepaths"], self.filepaths)
        update_toml_section_from_config(self.toml["metadata"], self.metadata)
        update_toml_section_from_config(self.toml["cli"], self.cli)
        update_toml_section_from_config(self.toml["database"], self.database)


def update_toml_section_from_config(toml_section, config):
    for field in fields(config):
        toml_section[field.name] = getattr(config, field.name)


class Config:
    def __init__(self, path: str, /):
        self.path = path
        if not os.path.isfile(path):
            set_user_defaults(path)

        with open(path) as toml_file:
            self.file: ConfigData = ConfigData.from_toml(toml_file.read())

        self.session: ConfigData = copy.deepcopy(self.file)

    def save_file(self):
        if not self.file.modified:
            return

        with open(self.path, "w") as toml_file:
            self.file.update_toml()
            toml_file.write(dumps(self.file.toml))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.save_file()


def set_user_defaults(path: str, /):
    """Update the TOML file at the path with user-specific default values."""
    shutil.copy(BLANK_CONFIG_PATH, path)

    with open(path) as f:
        toml = parse(f.read())
    toml["downloads"]["folder"] = DEFAULT_DOWNLOADS_FOLDER  # type: ignore
    toml["database"]["downloads_path"] = DEFAULT_DOWNLOADS_DB_PATH  # type: ignore
    toml["database"]["failed_downloads_path"] = DEFAULT_FAILED_DOWNLOADS_DB_PATH  # type: ignore

    with open(path, "w") as f:
        f.write(dumps(toml))
