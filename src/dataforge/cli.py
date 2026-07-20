"""CLI for DataForge — generate data pipeline code from natural language."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .agent import DataForgeAgent, OutputType

console = Console()


@click.group()
@click.version_option()
def main():
    """DataForge — metadata-aware code generator powered by DataHub."""
    pass


@main.command()
@click.argument("request")
@click.option(
    "--type", "-t",
    "output_type",
    type=click.Choice(["dbt", "sql", "python"]),
    default="dbt",
    help="Output type: dbt model, SQL query, or Python ETL.",
)
@click.option("--datahub-url", envvar="DATAHUB_GMS_URL", help="DataHub GMS URL.")
@click.option("--datahub-token", envvar="DATAHUB_GMS_TOKEN", help="DataHub access token.")
@click.option("--model", default="claude-sonnet-4-20250514", help="Claude model to use.")
@click.option("--mock", is_flag=True, help="Use mock DataHub data for demos.")
@click.option("--output-dir", "-o", type=click.Path(), help="Write files to this directory.")
def generate(
    request: str,
    output_type: str,
    datahub_url: str | None,
    datahub_token: str | None,
    model: str,
    mock: bool,
    output_dir: str | None,
):
    """Generate production-ready data code from a natural language description."""
    use_mock = mock or not datahub_url

    if use_mock and not mock:
        console.print(
            "[yellow]No DATAHUB_GMS_URL set — using sample data. "
            "Pass --datahub-url or set DATAHUB_GMS_URL for real metadata.[/yellow]\n"
        )

    with console.status("[bold blue]Fetching metadata from DataHub..."):
        try:
            agent = DataForgeAgent(
                datahub_url=datahub_url,
                datahub_token=datahub_token,
                model=model,
                use_mock=use_mock,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

    otype = OutputType(output_type)

    with console.status("[bold blue]Generating code with full schema context..."):
        result = agent.generate(request, otype)

    console.print(f"\n[bold green]✓[/bold green] {result.description}")
    console.print(f"  {result.context_summary}\n")

    for filename, content in result.files.items():
        lang = "sql" if filename.endswith(".sql") else "yaml" if filename.endswith(".yml") else "python"
        console.print(Panel(
            Syntax(content, lang, theme="monokai", line_numbers=True),
            title=f"[bold]{filename}[/bold]",
            border_style="blue",
        ))

    if result.validation:
        valid = result.validation.get("valid", False)
        issues = result.validation.get("issues", [])
        suggestions = result.validation.get("suggestions", [])

        if valid:
            console.print("[bold green]✓ Validation passed[/bold green]")
        else:
            console.print("[bold red]✗ Validation found issues:[/bold red]")
            for issue in issues:
                console.print(f"  [red]• {issue}[/red]")

        if suggestions:
            console.print("\n[yellow]Suggestions:[/yellow]")
            for s in suggestions:
                console.print(f"  [yellow]• {s}[/yellow]")

    if output_dir:
        out = Path(output_dir)
        for filename, content in result.files.items():
            filepath = out / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
            console.print(f"[green]Wrote {filepath}[/green]")


@main.command()
@click.option("--datahub-url", envvar="DATAHUB_GMS_URL", help="DataHub GMS URL.")
@click.option("--datahub-token", envvar="DATAHUB_GMS_TOKEN", help="DataHub access token.")
@click.option("--mock", is_flag=True, help="Use mock DataHub data.")
def explore(datahub_url: str | None, datahub_token: str | None, mock: bool):
    """Explore available datasets in your DataHub instance."""
    use_mock = mock or not datahub_url

    if use_mock:
        from .context import MockDataHubClient
        client = MockDataHubClient()
    else:
        from .context import DataHubClient
        client = DataHubClient(datahub_url, datahub_token)

    with console.status("[bold blue]Searching DataHub..."):
        results = client.search("*", limit=20)

    console.print(f"\n[bold]Found {len(results)} datasets:[/bold]\n")
    for r in results:
        urn = r.get("entity", "")
        ds = client.get_dataset(urn)
        col_count = len(ds.columns)
        tags_str = f" [{', '.join(ds.tags)}]" if ds.tags else ""
        console.print(f"  [bold]{ds.platform}.{ds.name}[/bold]{tags_str}")
        console.print(f"    {ds.description or '(no description)'}")
        console.print(f"    {col_count} columns | owners: {', '.join(ds.owners) or 'none'}\n")


if __name__ == "__main__":
    main()
