# Agent Startup Context

Read this file at the start of every task. Keep loaded context minimal: open only the linked files needed for the current task.

## Project In One Sentence

Build a low-cost personal scraper and alerting system for KiwiHouseSitters listings in New Zealand, prioritizing fast Auckland alerts now and reliable historical data for future analytics.

## General Rules

- Keep this file generic. Put topic-specific decisions in the relevant context file.
- Use progressive disclosure: open only the docs needed for the current task.
- Update docs when a product or architecture decision changes.
- Prefer simple, low-maintenance implementation choices.

## Load Context By Task

- Architecture and stack: [architecture.md](docs/agent-context/architecture.md)
- Scraper behavior and KiwiHouseSitters findings: [scraping-kiwihousesitters.md](docs/agent-context/scraping-kiwihousesitters.md)
- Scope scheduling: [scheduling-and-scopes.md](docs/agent-context/scheduling-and-scopes.md)
- Database schema: [data-model.md](docs/agent-context/data-model.md)
- Listing lifecycle and safety rules: [lifecycle-and-safety.md](docs/agent-context/lifecycle-and-safety.md)
- Telegram alerts and filters: [alerts.md](docs/agent-context/alerts.md)
- Implementation phases: [implementation-roadmap.md](docs/agent-context/implementation-roadmap.md)
- Product decisions and tradeoffs: [decisions-and-tradeoffs.md](docs/agent-context/decisions-and-tradeoffs.md)

## Working Style For This Repo

- Prefer small, testable increments.
- Preserve scraping fixtures once they exist; parser changes should be fixture-tested.
- Favor simple operational reliability over premature analytics features.
