"""CLI entrypoint for Lobby Canada scraper."""

import argparse
import sys

from civican.scraper.utils import log_message

from .crawler import LobbyCanadaCrawler


def main():
    """Main CLI function for civican-scraper lobbycanada command."""
    parser = argparse.ArgumentParser(description="Lobby Canada Scraper CLI")
    parser.add_argument("--repo", required=True, help="Path to the lobbycanada data repository")
    parser.add_argument(
        "--type",
        choices=["all", "communications", "registrations"],
        default="all",
        help="Type of data to scrape (default: all)",
    )
    parser.add_argument("--year", type=int, help="Target specific historical calendar year (e.g. 2023)")
    parser.add_argument("--start-date", help="Start date filter (ISO format YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date filter (ISO format YYYY-MM-DD)")
    parser.add_argument("--bulk", action="store_true", help="Download full historical Open Data archives")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of items to scrape")
    parser.add_argument(
        "--format",
        choices=["json", "duckdb", "all"],
        default="duckdb",
        help="Output format: json, duckdb, or all (default: duckdb)",
    )
    parser.add_argument(
        "--db-path",
        help="Path to target DuckDB database file (default: <repo_path>/lobbycanada.duckdb)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run without modifying repository")

    args = parser.parse_args()

    crawler = LobbyCanadaCrawler()
    result = crawler.scrape_data(
        repo_path=args.repo,
        data_type=args.type,
        year=args.year,
        start_date=args.start_date,
        end_date=args.end_date,
        bulk=args.bulk,
        limit=args.limit,
        output_format=args.format,
        db_path=args.db_path,
        dry_run=args.dry_run,
    )

    if result.success:
        log_message(
            f"Successfully completed Lobby Canada ({args.type}, format={args.format}) scraping. "
            f"Registrations: {result.registrations_scraped}, Communications: {result.communications_scraped}"
        )
    else:
        log_message("Lobby Canada scraping finished with errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
