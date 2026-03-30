import uvicorn
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pkmai.tasks import author_mirror_notes
from pkmai.tasks import auto_links
from pkmai.core.config import load_config


app = typer.Typer(
    help="PKM AI: Local AI orchestration for Personal Knowledge Management.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command(name="mirror")
def run_mirror(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force overwrite of existing mirror notes (ignores cache).",
    ),
):
    """
    Generate thesis/antithesis author mirrors for your notes.
    """
    console.print(
        Panel(
            "[bold cyan]MODULE:[/bold cyan] Author Mirror Generation",
            border_style="cyan",
        )
    )

    if force:
        console.print(
            "[bold yellow][WARN][/bold yellow] Force mode enabled: Existing mirrors may be overwritten."
        )

    try:
        author_mirror_notes.main()
        console.print(
            "[bold green][SUCCESS][/bold green] Author Mirror generation complete."
        )
    except Exception as e:
        console.print(f"[bold red][ERROR][/bold red] System failure: {e}")
        raise typer.Exit(code=1)


@app.command(name="links")
def run_links():
    """
    Generate semantic auto-links between your notes.
    """
    console.print(
        Panel(
            "[bold cyan]MODULE:[/bold cyan] Semantic Auto-Links Generation",
            border_style="cyan",
        )
    )

    try:
        auto_links.main()
        console.print(
            "[bold green][SUCCESS][/bold green] Auto-Links generation complete."
        )
    except Exception as e:
        console.print(f"[bold red][ERROR][/bold red] System failure: {e}")
        raise typer.Exit(code=1)


@app.command(name="info")
def show_info():
    """
    Display the current system configuration.
    """
    try:
        cfg = load_config()
    except Exception as e:
        console.print(f"[bold red][ERROR][/bold red] Failed to load config: {e}")
        raise typer.Exit(code=1)

    table = Table(title="SYSTEM CONFIGURATION", title_style="bold blue")
    table.add_column("Parameter", justify="right", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Vault Path", str(cfg.vault_path))
    table.add_row("LLM Model (Mirror)", str(cfg.author_model_path.name))
    table.add_row("Embedding Model (Links)", cfg.link_model_name)
    table.add_row("Similarity Threshold", str(cfg.link_similarity_threshold))

    console.print(table)


@app.command(name="serve")
def run_server(port: int = typer.Option(8000, help="Port to run the API server on.")):
    """
    Launch the FastAPI background server for Obsidian integration.
    """
    console.print(
        Panel(
            f"[bold cyan]MODULE:[/bold cyan] API Server started on port {port}",
            border_style="cyan",
        )
    )
    uvicorn.run("pkmai.api.server:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    app()
