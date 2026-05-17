# Agent Startup Context

Read this file at the start of every task. Keep loaded context minimal: open only the linked files needed for the current task.

## Project In One Sentence

Build a low-cost personal scraper and alerting system for KiwiHouseSitters listings in New Zealand, prioritizing fast Auckland alerts now and reliable historical data for future analytics.

## General Rules

- Keep this file generic. Put topic-specific decisions in the relevant context file.
- Use progressive disclosure: open only the docs needed for the current task.
- Treat context and tool calls as a scarce budget. Prefer the smallest high-signal check that can answer the task correctly.
- Update docs when a product or architecture decision changes.
- Prefer simple, low-maintenance implementation choices.
- Use `uv` for Python dependency management and command execution.
- Avoid unexplained hardcoded values. Put reusable values in named constants close to the module that owns them.
- When changing database migrations or data contracts, always verify `docs/contracts`, `docs/agent-context/data-model.md`, and `supabase/migrations` stay in sync.
- Format JSON Schema files for human review: use expanded indentation, put examples only at the schema level, and reference nested structures with `$ref` instead of duplicating them inline.

## Speed And Scope Control

- Match effort to task size. For small wording fixes, simple renames, obvious rollbacks, or user corrections, make the minimal patch and run at most a targeted `rg` or focused test.
- Do not run full test suites for docs-only changes unless the docs are generated, schema-validated, or explicitly tied to tests.
- Do not broadly inspect unrelated files when the user asks for a narrow change and the affected files are already known.
- If a request says "fast", "minimal", "just", "only", or "quick", skip broad exploration and explain any skipped verification briefly.
- Prefer targeted verification first. Escalate to full `uv --cache-dir .uv-cache run pytest` only when code behavior, contracts, migrations, or shared parsing logic changed.
- If a task starts taking longer than expected because scope is expanding, stop and report the exact blocker or ask whether to continue deeper.

## Load Context By Task

- Architecture and stack: [architecture.md](docs/agent-context/architecture.md)
- Scraper behavior and KiwiHouseSitters findings: [scraping-kiwihousesitters.md](docs/agent-context/scraping-kiwihousesitters.md)
- Scheduler platform and deployment: [scheduling.md](docs/agent-context/scheduling.md)
- Scrape scope cadence and coverage: [scopes.md](docs/agent-context/scopes.md)
- Database schema: [data-model.md](docs/agent-context/data-model.md)
- Data contracts: [docs/contracts](docs/contracts)
- Listing lifecycle and safety rules: [lifecycle-and-safety.md](docs/agent-context/lifecycle-and-safety.md)
- Telegram alerts and filters: [alerts.md](docs/agent-context/alerts.md)
- Implementation phases: [implementation-roadmap.md](docs/agent-context/implementation-roadmap.md)
- Product decisions and tradeoffs: [decisions-and-tradeoffs.md](docs/agent-context/decisions-and-tradeoffs.md)

## Working Style For This Repo

- Prefer small, testable increments.
- Preserve scraping fixtures once they exist; parser changes should be fixture-tested.
- Favor simple operational reliability over premature analytics features.
- For local Postgres, prefer the repo scripts over long inline commands:
  - `scripts/init-local-postgres.sh`
  - `scripts/test-local-postgres.sh`
  - `scripts/persist-local.sh auckland_central 1`
  - `scripts/psql-local.sh`
- Runtime settings load from environment variables and a repo-root `.env` file. Keep production code environment-driven; local database URLs belong in `.env` or scripts, not hardcoded app logic.
- Production database credentials belong only in gitignored `.env.production`, Lambda environment variables, or GitHub Actions deployment secrets. Local scripts must not accidentally target production; production scripts need explicit warning/confirmation.
- Do not move files to the staged section unless the user explicitly asks for staging. Leave edits in the working changes section for user review by default.
- Do not unstage files unless the user explicitly asks for unstaging. The user may be managing the index manually to compare staged and unstaged diffs.

## Code Review

- Use `gh pr diff <number>` to get diffs. If no PR exists, use `git diff <base>...HEAD`.
- Skip `uv.lock` and any other lock files entirely; they are noise in reviews.
- Read changed source files directly with a file reader rather than parsing the full raw diff when the diff is large.
