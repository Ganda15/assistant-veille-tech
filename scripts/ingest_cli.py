from __future__ import annotations

import logging

import typer

from app.ingest.news_api import NewsApiIngester
from app.ingest.scraper import Scraper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

app = typer.Typer(help="Ingestion CLI for the veille tech index.")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Lance news + scrape si aucune commande n'est passée."""
    if ctx.invoked_subcommand is None:
        news(topics=["python", "llm", "AI"])
        scrape()


@app.command()
def news(
    topics: list[str] = typer.Option(
        ["python", "llm", "AI"],
        "--topic", "-t",
        help="Topic à requêter (ex: -t python -t llm).",
    )
) -> None:
    """Collecte les articles NewsAPI et les indexe dans Chroma."""
    typer.echo(f"📰 Ingestion NewsAPI pour : {topics}")
    ingester = NewsApiIngester()
    articles = ingester.run(topics)
    typer.echo(f"✅ {len(articles)} articles indexés.")


@app.command()
def scrape() -> None:
    """Scrape les sources RSS et HTML et les indexe dans Chroma."""
    typer.echo("🔍 Scraping des sources tech...")
    scraper = Scraper()
    articles = scraper.run(urls=[])
    typer.echo(f"✅ {len(articles)} articles scrapés et indexés.")


if __name__ == "__main__":
    app()

    