import asyncio
import logging
from functools import wraps

import click
from click_help_colors import HelpColorsGroup
from rich.logging import RichHandler
from rich.traceback import install

from streamrip import db
from streamrip.config import DEFAULT_CONFIG_PATH, Config, OutdatedConfigError
from streamrip.console import console
from streamrip.rip.main import Main


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.group(
    cls=HelpColorsGroup,
    help_headers_color="yellow",
    help_options_color="green",
)
@click.option(
    "-f",
    "--folder",
    help="The folder to download items into.",
    type=click.Path(file_okay=False, dir_okay=True),
)
@click.option(
    "-ndb",
    "--no-db",
    help="Download items even if logged in the database",
    default=False,
    is_flag=True,
)
@click.option(
    "--no-ssl",
    help="Disable SSL certificate verification",
    is_flag=True,
    default=False,
)
@click.option(
    "-v",
    "--verbose",
    help="Enable verbose output (debug mode)",
    is_flag=True,
)
@click.pass_context
def rip(
    ctx,
    folder,
    no_db,
    no_ssl,
    verbose,
):
    """Streamrip: the all in one music downloader."""
    global logger
    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )
    logger = logging.getLogger("streamrip")
    if verbose:
        install(
            console=console,
            suppress=[click],
            show_locals=True,
            locals_hide_sunder=False,
        )
        logger.setLevel(logging.DEBUG)
        logger.debug("Showing all debug logs")
    else:
        install(console=console, suppress=[click, asyncio], max_frames=1)
        logger.setLevel(logging.INFO)

    # pass to subcommands
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = DEFAULT_CONFIG_PATH

    try:
        c = Config(DEFAULT_CONFIG_PATH)
    except OutdatedConfigError as e:
        console.print(e)
        console.print("Auto-updating config file...")
        Config.update_file(DEFAULT_CONFIG_PATH)
        c = Config(DEFAULT_CONFIG_PATH)
    except Exception as e:
        console.print(
            f"Error loading config from [bold cyan]{DEFAULT_CONFIG_PATH}[/bold cyan]: {e}\n"
            "Try running [bold]rip config reset[/bold]",
        )
        ctx.obj["config"] = None
        return

    # set session config values to command line args
    if no_db:
        c.session.database.downloads_enabled = False
    if folder is not None:
        c.session.downloads.folder = folder
    if no_ssl:
        c.session.downloads.verify_ssl = False

    ctx.obj["config"] = c


@rip.command("config")
@click.pass_context
def config(ctx):
    """Open the config file in a text editor."""
    config_path = ctx.obj["config_path"]

    console.print(f"Opening file at [bold cyan]{config_path}")
    click.launch(config_path)


@rip.group()
def database():
    """View and modify the downloads and failed downloads databases."""


@database.command("browse")
@click.argument("table")
@click.pass_context
def database_browse(ctx, table):
    """Browse the contents of a table.

    Available tables:

        * Downloads

        * Failed
    """
    from rich.table import Table

    cfg: Config = ctx.obj["config"]

    if table.lower() == "downloads":
        downloads = db.Downloads(cfg.session.database.downloads_path)
        t = Table(title="Downloads database")
        t.add_column("Row")
        t.add_column("ID")
        for i, row in enumerate(downloads.all()):
            t.add_row(f"{i:02}", *row)
        console.print(t)

    elif table.lower() == "failed":
        failed = db.Failed(cfg.session.database.failed_downloads_path)
        t = Table(title="Failed downloads database")
        t.add_column("Source")
        t.add_column("Media Type")
        t.add_column("ID")
        for i, row in enumerate(failed.all()):
            t.add_row(f"{i:02}", *row)
        console.print(t)

    else:
        console.print(
            f"[red]Invalid database[/red] [bold]{table}[/bold]. [red]Choose[/red] [bold]downloads "
            "[red]or[/red] failed[/bold].",
        )


@rip.command()
@click.argument("media-type", required=True)
@click.argument("query", required=True)
@click.pass_context
@coro
async def search(ctx, media_type, query):
    """Search for content using Deezer.

    Example:
        rip search album 'rumours'
    """
    with ctx.obj["config"] as cfg:
        async with Main(cfg) as main:
            await main.search_interactive(media_type, query)
            await main.resolve()
            await main.rip()


if __name__ == "__main__":
    rip()
