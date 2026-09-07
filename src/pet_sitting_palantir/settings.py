"""Code-owned operational settings for the home-hosted runtime.

Secrets belong in environment files. Scope cadences belong in PostgreSQL.
"""

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

# Minimum pause between KiwiHouseSitters HTTP requests. The site began returning
# Cloudflare 429 responses after ten requests at the previous 0.5-second pace.
KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS = 1.5
# Maximum time to wait for one KiwiHouseSitters HTTP response before failing the scope.
KIWIHOUSESITTERS_TIMEOUT_SECONDS = 20
# Additional attempts for transient connection failures and upstream 5xx responses.
KIWIHOUSESITTERS_TRANSIENT_RETRY_ATTEMPTS = 2
# Initial delay for transient retries; each subsequent retry doubles this value.
KIWIHOUSESITTERS_TRANSIENT_RETRY_BACKOFF_SECONDS = 5
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
# Maximum wait before retrying an overdue scope whose latest direct attempt failed.
# Short-cadence scopes retain their configured cadence; broad scopes cool down longer.
SCRAPE_FAILURE_RETRY_MAX_MINUTES = 60
# Process lock path used to prevent two production home runners running together.
HOME_RUNNER_LOCK_FILE = Path("/tmp/pet-sitting-palantir-home-runner.lock")
# Local time when the home runner sends its daily operational health notification.
HOME_RUNNER_HEALTHCHECK_TIME = time(hour=10)
# Minutes after the daily health notification time during which sending is allowed.
HOME_RUNNER_HEALTHCHECK_WINDOW_MINUTES = 5
# Number of hours included in the daily health notification scan summary.
HOME_RUNNER_HEALTHCHECK_LOOKBACK_HOURS = 24

# Time zone used to evaluate quiet hours, independent of the computer's local setting.
NEW_ZEALAND_TIME_ZONE = ZoneInfo("Pacific/Auckland")
# Beginning of the daily no-scraping window in New Zealand local time.
QUIET_HOURS_START = time(hour=0)
# End of the daily no-scraping window in New Zealand local time.
QUIET_HOURS_END = time(hour=6)
