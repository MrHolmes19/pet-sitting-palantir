"""Code-owned operational settings for the home-hosted runtime.

Secrets belong in environment files. Scope cadences belong in PostgreSQL.
"""

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

# Minimum pause between KiwiHouseSitters HTTP requests; increasing it reduces site load.
KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS = 0.5
# Maximum time to wait for one KiwiHouseSitters HTTP response before failing the scope.
KIWIHOUSESITTERS_TIMEOUT_SECONDS = 20
# Maximum time to wait for a Telegram delivery request before retrying on a later tick.
TELEGRAM_TIMEOUT_SECONDS = 15

# Maximum time to wait while opening a PostgreSQL connection before retrying next tick.
POSTGRES_CONNECT_TIMEOUT_SECONDS = 10
# Seconds of idle database connection time before TCP keepalive checks begin.
POSTGRES_KEEPALIVES_IDLE_SECONDS = 10
# Seconds between database keepalive checks after an idle connection is probed.
POSTGRES_KEEPALIVES_INTERVAL_SECONDS = 5
# Failed database keepalive checks allowed before treating the connection as lost.
POSTGRES_KEEPALIVES_COUNT = 3

# How frequently the home runner checks the database for due scrape scopes.
HOME_RUNNER_TICK_INTERVAL_SECONDS = 5 * 60
# Process lock path used to prevent two production home runners running together.
HOME_RUNNER_LOCK_FILE = Path("/tmp/pet-sitting-palantir-home-runner.lock")

# Time zone used to evaluate quiet hours, independent of the computer's local setting.
NEW_ZEALAND_TIME_ZONE = ZoneInfo("Pacific/Auckland")
# Beginning of the daily no-scraping window in New Zealand local time.
QUIET_HOURS_START = time(hour=0)
# End of the daily no-scraping window in New Zealand local time.
QUIET_HOURS_END = time(hour=6)
