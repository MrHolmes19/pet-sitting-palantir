"""Command-line entry point for the scraper application."""

from argparse import ArgumentParser, ArgumentTypeError, Namespace
from json import dumps

from pet_sitting_palantir.kiwihousesitters.constants import (
    DEFAULT_MAX_PAGES,
    DEFAULT_SCOPE_NAME,
    DEFAULT_SITE_FILTERS,
)
from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope
from pet_sitting_palantir.workflows.run_due_scopes import run_due_scrape_scopes
from pet_sitting_palantir.workflows.scrape_and_store import scrape_and_store_scope

SUMMARY_LISTING_FIELDS = (
    "external_id",
    "island",
    "region",
    "subregion",
    "city",
    "duration_days",
    "start_date",
    "end_date",
    "total_animals",
    "dogs_count",
    "cats_count",
    "url",
)


def main() -> int:
    """Run the application."""
    args = _parse_args()
    if args.run_due:
        result = run_due_scrape_scopes(max_pages=args.max_pages)
        print(dumps(result.to_dict(), indent=2 if args.pretty else None, sort_keys=True))
        return 1 if result.scopes_failed else 0

    if args.persist:
        result = scrape_and_store_scope(scope_name=args.scope, max_pages=args.max_pages)
        print(dumps(result.to_dict(), indent=2 if args.pretty else None, sort_keys=True))
        return 0

    site_filter = DEFAULT_SITE_FILTERS[args.scope]
    result = scrape_scope(site_filter=site_filter, max_pages=args.max_pages)

    output = {
        "scope": args.scope,
        "search_url": result.search_url,
        "pages_fetched": result.pages_fetched,
        "listings_seen": len(result.listings),
        "listings": [
            _listing_summary(listing.to_dict()) if args.summary else listing.to_dict()
            for listing in result.listings
        ],
    }

    print(dumps(output, indent=2 if args.pretty else None, sort_keys=True, default=str))
    return 0


def _parse_args() -> Namespace:
    parser = ArgumentParser(description="Scrape KiwiHouseSitters search results.")
    parser.add_argument(
        "--scope",
        choices=sorted(DEFAULT_SITE_FILTERS.keys()),
        default=DEFAULT_SCOPE_NAME,
        help="Configured search scope to scrape.",
    )
    parser.add_argument(
        "--max-pages",
        type=_max_pages,
        default=DEFAULT_MAX_PAGES,
        help="Maximum number of paginated search result pages to fetch, or 'all'.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact JSON listing summary.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Store scraped listings in Postgres instead of printing listing JSON.",
    )
    parser.add_argument(
        "--run-due",
        action="store_true",
        help="Store every enabled database scrape scope whose interval is due.",
    )
    return parser.parse_args()


def _max_pages(value: str) -> int | None:
    if value == "all":
        return None
    parsed_value = int(value)
    if parsed_value < 1:
        raise ArgumentTypeError("--max-pages must be greater than zero")
    return parsed_value


def _listing_summary(listing: dict[str, object]) -> dict[str, object]:
    return {field: listing[field] for field in SUMMARY_LISTING_FIELDS}
