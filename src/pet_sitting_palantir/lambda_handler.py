"""AWS Lambda entry point for scheduled due-scope scraping."""

from collections.abc import Mapping
from json import dumps
from logging import getLogger
from typing import Any

from pet_sitting_palantir.workflows.run_due_scopes import run_due_scrape_scopes

logger = getLogger(__name__)

ALL_PAGES: int | None = None


def lambda_handler(event: Mapping[str, Any] | None, context: Any) -> dict[str, Any]:
    """Run the production due-scope workflow from AWS EventBridge Scheduler."""
    result = run_due_scrape_scopes(max_pages=ALL_PAGES)
    payload = result.to_dict()
    logger.info("lambda_due_scope_run=%s", dumps(payload, sort_keys=True))

    if result.scopes_failed:
        logger.error("lambda_due_scope_run_failed=%s", dumps(payload, sort_keys=True))
        raise RuntimeError(
            f"Due-scope Lambda run failed for {result.scopes_failed} of {result.scopes_due} scopes"
        )

    return {
        "statusCode": 200,
        "body": payload,
    }
