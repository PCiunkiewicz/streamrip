import asyncio
import logging

from simple_term_menu import TerminalMenu

from streamrip import db
from streamrip.client import DeezerClient
from streamrip.config import Config
from streamrip.console import console
from streamrip.media import (
    Media,
    Pending,
    PendingAlbum,
    PendingArtist,
    PendingPlaylist,
    PendingSingle,
    remove_artwork_tempdirs,
)
from streamrip.metadata import SearchResults
from streamrip.progress import clear_progress
from streamrip.rip.prompter import DeezerCredentialPrompter

logger = logging.getLogger("streamrip")


class Main:
    """Provides all of the functionality called into by the CLI.

    * Logs in to Clients and prompts for credentials
    * Handles output logging
    * Handles downloading Media
    * Handles interactive search

    User input (urls) -> Main --> Download files & Output messages to terminal
    """

    def __init__(self, config: Config):
        # Data pipeline:
        # input URL -> (URL) -> (Pending) -> (Media) -> (Downloadable) -> audio file
        self.pending: list[Pending] = []
        self.media: list[Media] = []
        self.config = config
        self._client = DeezerClient(config)
        self.database: db.Database

        c = self.config.session.database
        if c.downloads_enabled:
            downloads_db = db.Downloads(c.downloads_path)
        else:
            downloads_db = db.Dummy()

        if c.failed_downloads_enabled:
            failed_downloads_db = db.Failed(c.failed_downloads_path)
        else:
            failed_downloads_db = db.Dummy()

        self.database = db.Database(downloads_db, failed_downloads_db)

    @property
    async def client(self) -> DeezerClient:
        if not self._client.logged_in:
            prompter = DeezerCredentialPrompter(self.config, self._client)
            if not prompter.has_creds():
                # Get credentials from user and log into client
                await prompter.prompt_and_login()
                prompter.save()
            else:
                with console.status("[cyan]Logging into Deezer", spinner="dots"):
                    # Log into client using credentials from config
                    await self._client.login()

        return self._client

    async def add_all_by_id(self, info: list[tuple[str, str]]):
        for media_type, id in info:
            self._add_by_id_client(await self.client, media_type, id)

    def _add_by_id_client(self, client: DeezerClient, media_type: str, id: str):
        if media_type == "track":
            item = PendingSingle(id, client, self.config, self.database)
        elif media_type == "album":
            item = PendingAlbum(id, client, self.config, self.database)
        elif media_type == "playlist":
            item = PendingPlaylist(id, client, self.config, self.database)
        elif media_type == "artist":
            item = PendingArtist(id, client, self.config, self.database)
        else:
            raise Exception(media_type)

        self.pending.append(item)

    async def resolve(self):
        """Resolve all currently pending items."""
        with console.status("Resolving URLs...", spinner="dots"):
            coros = [p.resolve() for p in self.pending]
            new_media: list[Media] = [m for m in await asyncio.gather(*coros) if m is not None]

        self.media.extend(new_media)
        self.pending.clear()

    async def rip(self):
        """Download all resolved items."""
        results = await asyncio.gather(*[item.rip() for item in self.media], return_exceptions=True)

        failed_items = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error processing media item: {result}")
                failed_items += 1

        if failed_items > 0:
            total_items = len(self.media)
            logger.info(f"Download completed with {failed_items} failed items out of {total_items} total items.")

    async def search_interactive(self, media_type: str, query: str) -> None:
        client = await self.client
        with console.status("[bold]Searching Deezer", spinner="dots"):
            pages = await client.search(media_type, query, self.config.session.cli.max_search_results)
            if len(pages) == 0:
                console.print(f"[red]No search results found for query {query}")
                return
            search_results = SearchResults.from_pages(media_type, pages)

        menu = TerminalMenu(
            search_results.summaries(),
            preview_command=search_results.preview,
            preview_size=0.5,
            title=(f"Results for {media_type}='{query}'\nSPACE - select, ENTER - download, ESC - exit, / - filter"),
            cycle_cursor=True,
            clear_screen=True,
            multi_select=True,
        )
        chosen_ind = menu.show()
        if chosen_ind is None:
            console.print("[yellow]No items chosen. Exiting.")
        else:
            choices = search_results.get_choices(chosen_ind)
            await self.add_all_by_id(
                [(item.media_type(), item.id) for item in choices],
            )

    def select_media_type(self) -> str | None:
        media_types = ["track", "album", "artist", "playlist", "playlist (bean)"]
        menu = TerminalMenu(
            [t.capitalize() for t in media_types],
            title=("Search type:"),
            cycle_cursor=True,
            clear_screen=True,
        )
        choice: int = menu.show()  # type: ignore
        if choice is None:
            console.print("[yellow]No items chosen. Exiting.")
        else:
            return media_types[choice]

    def prompt_search_query(self, media_type: str | None) -> str | None:
        if media_type == "playlist (bean)":
            return "all"
        if media_type:
            query = console.input(f"Search query ({media_type}):\n[red]>[/red] ")
            return query

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        # Ensure client session is closed
        if hasattr(self._client, "session"):
            await self._client.session.close()

        # close global progress bar manager
        clear_progress()
        remove_artwork_tempdirs()
