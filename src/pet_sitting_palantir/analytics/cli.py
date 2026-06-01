"""Command-line entry point for analytics utilities."""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from json import dumps
from pathlib import Path

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

    raise ValueError(f"Unsupported analytics command: {args.command}")


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

    return parser.parse_args(argv)


def _positive_int(value: str) -> int:
    parsed_value = int(value)
    if parsed_value < 1:
        raise ValueError("value must be greater than zero")
    return parsed_value

