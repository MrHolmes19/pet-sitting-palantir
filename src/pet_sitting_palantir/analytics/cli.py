"""Command-line entry point for analytics utilities."""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from json import dumps
from pathlib import Path

import duckdb

from pet_sitting_palantir.analytics.snapshot import (
    DEFAULT_PRODUCTION_ENV_FILE,
    DEFAULT_PRODUCTION_SNAPSHOT_PATH,
    database_url_from_env_file,
    refresh_production_snapshot,
)
from pet_sitting_palantir.analytics.synthetic import (
    DEFAULT_DEMO_DATABASE_PATH,
    DEFAULT_LISTING_COUNT,
    DEFAULT_SEED,
    write_demo_database,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run analytics commands."""
    args = _parse_args(argv)

    if args.command == "generate-demo":
        result = write_demo_database(
            output_path=args.output,
            listing_count=args.count,
            seed=args.seed,
        )
        print(dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
        return 0

    if args.command == "inspect-demo":
        inspect_demo_database(path=args.path, limit=args.limit)
        return 0

    if args.command == "refresh":
        if args.source != "production":
            raise ValueError(f"Unsupported analytics refresh source: {args.source}")
        database_url = database_url_from_env_file(args.env_file)
        result = refresh_production_snapshot(output_path=args.output, database_url=database_url)
        print(dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
        return 0

    raise ValueError(f"Unsupported analytics command: {args.command}")


def inspect_demo_database(*, path: Path = DEFAULT_DEMO_DATABASE_PATH, limit: int = 10) -> None:
    """Print quick sanity checks for a generated demo analytics database."""
    if not path.exists():
        raise FileNotFoundError(f"Demo analytics database does not exist: {path}")

    with duckdb.connect(str(path), read_only=True) as connection:
        print("Sample listings")
        connection.sql(f"""
            select
              external_id,
              region,
              subregion,
              city,
              start_date,
              end_date,
              duration_days,
              dogs_count,
              cats_count
            from listings
            limit {limit}
        """).show()

        print("Listings by region")
        connection.sql("""
            select region, count(*) as listings
            from listings
            group by region
            order by listings desc
        """).show()

        print("Listings by start month")
        connection.sql("""
            select month(start_date) as month, count(*) as listings
            from listings
            group by month
            order by month
        """).show()


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(description="Analytics utilities for pet-sitting data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_demo = subparsers.add_parser(
        "generate-demo",
        help="Generate a local DuckDB database with synthetic listing data.",
    )
    generate_demo.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DEMO_DATABASE_PATH,
        help=f"Destination DuckDB database path. Defaults to {DEFAULT_DEMO_DATABASE_PATH}.",
    )
    generate_demo.add_argument(
        "--count",
        type=_positive_int,
        default=DEFAULT_LISTING_COUNT,
        help=f"Number of synthetic listings to generate. Defaults to {DEFAULT_LISTING_COUNT}.",
    )
    generate_demo.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Deterministic random seed. Defaults to {DEFAULT_SEED}.",
    )

    inspect_demo = subparsers.add_parser(
        "inspect-demo",
        help="Print quick checks from the generated demo DuckDB database.",
    )
    inspect_demo.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_DEMO_DATABASE_PATH,
        help=f"Demo DuckDB database path. Defaults to {DEFAULT_DEMO_DATABASE_PATH}.",
    )
    inspect_demo.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help="Number of sample listings to print. Defaults to 10.",
    )

    refresh = subparsers.add_parser(
        "refresh",
        help="Refresh a local analytics snapshot from a source database.",
    )
    refresh.add_argument(
        "--source",
        choices=("production",),
        required=True,
        help="Source to refresh from.",
    )
    refresh.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_PRODUCTION_SNAPSHOT_PATH,
        help=(
            "Destination DuckDB database path. "
            f"Defaults to {DEFAULT_PRODUCTION_SNAPSHOT_PATH}."
        ),
    )
    refresh.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_PRODUCTION_ENV_FILE,
        help=(
            "Production env file containing DATABASE_URL. "
            f"Defaults to {DEFAULT_PRODUCTION_ENV_FILE}."
        ),
    )

    return parser.parse_args(argv)


def _positive_int(value: str) -> int:
    parsed_value = int(value)
    if parsed_value < 1:
        raise ValueError("value must be greater than zero")
    return parsed_value
