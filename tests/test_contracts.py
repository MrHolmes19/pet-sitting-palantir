import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACTS_DIR = Path(__file__).parents[1] / "docs" / "contracts"
MIGRATIONS_DIR = Path(__file__).parents[1] / "supabase" / "migrations"

TABLE_CONTRACTS = {
    "scrape_scopes": CONTRACTS_DIR / "scrape_scopes.schema.json",
    "scrape_runs": CONTRACTS_DIR / "scrape_runs.schema.json",
    "listings": CONTRACTS_DIR / "listings.schema.json",
    "alert_filters": CONTRACTS_DIR / "alert_filters.schema.json",
    "sent_alerts": CONTRACTS_DIR / "sent_alerts.schema.json",
}

ALL_CONTRACTS = tuple(sorted(CONTRACTS_DIR.glob("*.schema.json")))


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text())


def _migration_sql() -> str:
    return "\n".join(path.read_text() for path in sorted(MIGRATIONS_DIR.glob("*.sql")))


def _registry() -> Registry:
    resources = []
    for path in ALL_CONTRACTS:
        schema = _load_schema(path)
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def _table_columns(table_name: str) -> set[str]:
    match = re.search(
        rf"create table (?:public\.)?{table_name} \((.*?)\n\);",
        _migration_sql(),
        flags=re.DOTALL,
    )
    assert match is not None, f"Table not found in migration: {table_name}"

    columns: set[str] = set()
    for line in match.group(1).splitlines():
        column_match = re.match(r"\s{2}([a-z_]+)\s+", line)
        if column_match and column_match.group(1) != "constraint":
            columns.add(column_match.group(1))

    alter_column_matches = re.findall(
        rf"alter table (?:public\.)?{table_name}\s+add column\s+([a-z_]+)\s+",
        _migration_sql(),
        flags=re.IGNORECASE,
    )
    columns.update(alter_column_matches)

    return columns


def test_contract_files_exist_for_all_persisted_tables() -> None:
    for path in TABLE_CONTRACTS.values():
        assert path.exists()


def test_contract_schemas_are_valid_json_schema() -> None:
    for path in ALL_CONTRACTS:
        Draft202012Validator.check_schema(_load_schema(path))


def test_contract_examples_validate_against_their_schema() -> None:
    registry = _registry()

    for path in ALL_CONTRACTS:
        schema = _load_schema(path)
        validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
            registry=registry,
        )

        for example in schema.get("examples", []):
            validator.validate(example)


def test_contract_properties_match_migration_columns() -> None:
    for table_name, path in TABLE_CONTRACTS.items():
        schema = _load_schema(path)

        assert set(schema["properties"]) == _table_columns(table_name)


def test_contracts_document_each_field() -> None:
    for path in ALL_CONTRACTS:
        schema = _load_schema(path)

        for field_name, field_schema in schema["properties"].items():
            assert field_schema.get("description"), f"{path.name} missing description: {field_name}"


def test_contracts_keep_examples_at_schema_level() -> None:
    for path in ALL_CONTRACTS:
        schema = _load_schema(path)

        assert schema.get("examples"), f"{path.name} missing schema-level examples"
        for field_name, field_schema in schema["properties"].items():
            assert "examples" not in field_schema, (
                f"{path.name} should not repeat examples at field level: {field_name}"
            )


def test_nested_filter_contracts_are_referenced_not_duplicated() -> None:
    scrape_scopes = _load_schema(TABLE_CONTRACTS["scrape_scopes"])
    alert_filters = _load_schema(TABLE_CONTRACTS["alert_filters"])

    assert scrape_scopes["properties"]["site_filter"]["$ref"] == "site_filter.schema.json"
    assert alert_filters["properties"]["site_filter"]["$ref"] == "site_filter.schema.json"
    assert alert_filters["properties"]["local_filter"]["$ref"] == "local_filter.schema.json"


def test_listings_contract_excludes_raw_parser_fields() -> None:
    listing_properties = _load_schema(TABLE_CONTRACTS["listings"])["properties"]

    assert "raw_data" not in listing_properties
    assert "pets_raw" not in listing_properties
    assert "reply_rating_text" not in listing_properties
