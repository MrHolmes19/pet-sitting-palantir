"""Code-owned operational settings for the home-hosted runtime.

Secrets belong in environment files. Scope cadences belong in PostgreSQL.
"""

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS = 0.5
KIWIHOUSESITTERS_TIMEOUT_SECONDS = 20

HOME_RUNNER_TICK_INTERVAL_SECONDS = 5 * 60
HOME_RUNNER_LOCK_FILE = Path("/tmp/pet-sitting-palantir-home-runner.lock")

NEW_ZEALAND_TIME_ZONE = ZoneInfo("Pacific/Auckland")
QUIET_HOURS_START = time(hour=0)
QUIET_HOURS_END = time(hour=6)
