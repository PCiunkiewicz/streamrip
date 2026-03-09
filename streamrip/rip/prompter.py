import logging

from rich.prompt import Prompt

from streamrip.client import DeezerClient
from streamrip.config import Config
from streamrip.console import console
from streamrip.exceptions import AuthenticationError

logger = logging.getLogger("streamrip")


class DeezerCredentialPrompter:
    client: DeezerClient

    def __init__(self, config: Config, client: DeezerClient):
        self.config = config
        self.client = client

    def has_creds(self):
        return self.config.session.deezer.arl != ""

    async def prompt_and_login(self):
        if not self.has_creds():
            self._prompt_creds_and_set_session_config()
        while True:
            try:
                await self.client.login()
                break
            except AuthenticationError:
                console.print("[yellow]Invalid arl, try again.")
                self._prompt_creds_and_set_session_config()
        self.save()

    def _prompt_creds_and_set_session_config(self):
        console.print(
            "If you're not sure how to find the ARL cookie, see the instructions at ",
            "[blue underline]https://github.com/nathom/streamrip/wiki/Finding-your-Deezer-ARL-Cookie",
        )
        self.config.session.deezer.arl = Prompt.ask("Enter your [bold]ARL")

    def save(self):
        self.config.file.deezer.arl = self.config.session.deezer.arl
        self.config.file.set_modified()
        console.print(f"[green]Credentials saved to config file at [bold cyan]{self.config.path}")
