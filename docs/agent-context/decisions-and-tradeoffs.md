# Decisions And Tradeoffs

This file records conceptual product and architecture decisions as they are made. Keep implementation details in the topic-specific docs.

## Frequency

We want early notifications, but GitHub Actions is not reliable enough to be the
long-term scheduler for fast alerts. It accepts cron syntax such as
`*/5 * * * *`, but scheduled workflows are best-effort. Production observation
showed the scraper running much less often than every 5 minutes.

AWS EventBridge Scheduler plus AWS Lambda was implemented as the next option,
but requests from the Lambda runtime were blocked by KiwiHouseSitters because
they originated from an AWS cloud IP range.

Decision: run the production workflow from an always-on home machine over its
residential network connection. Keep GitHub Actions for CI only, not alert
timing. The home-runner command is still to be implemented; it should run one
generic due-scope invocation while scope cadence remains database-configured.

Decision: enforce overnight quiet hours in application code from `00:00`
inclusive to `06:00` exclusive in `Pacific/Auckland`. A local scheduler may
also avoid overnight invocations, but scraping must remain protected if it is
invoked during that window.

Reasons other options were left out:

- GitHub Actions scheduled workflows can be delayed or dropped and already failed
  the 5-minute alerting requirement in production.
- AWS EventBridge Scheduler with Lambda cannot currently reach the site because
  KiwiHouseSitters blocks the cloud IP range observed for those requests.
- Google Cloud Free Tier VM is low-migration, but the always-free VM is limited
  to selected US regions and requires server maintenance.
- Google Cloud Scheduler has a usable free scheduler allowance, but still needs
  a separate Python runtime target, so it is not simpler than AWS Lambda here.
- Supabase scheduled Edge Functions would require a runtime migration away from
  the current Python scraper.
- Oracle Always Free compute can reclaim idle instances, which is a poor match
  for a quiet periodic scraper.
- PythonAnywhere, Heroku free dynos, and cheap VPS options do not meet the
  free 5-minute cloud-runner requirement.

## Geographic Priority

Notification value is highest for Auckland Central. North Shore City, inside the Auckland Region scope, is the second most important area.

Decision: optimize alerting around Auckland Central first, then North Shore City. Broader scopes such as North Island and All New Zealand are mainly for history collection, market visibility, and future behavior analysis.

## Capture Before Analytics

The system will eventually support analytics, but analytics are only useful if the underlying capture is reliable.

Decision: build scraper quality, persistence, lifecycle handling, and alerts before dashboards or analysis jobs.

## Cost And Maintenance

This is a personal project, so operational simplicity matters more than completeness.

Decision: prefer cheap, boring infrastructure and small implementation phases. Avoid services or architecture that create maintenance work before the scraper has proven useful.

Decision: use already-owned home hardware for the current free runtime path.
The future activation command must provide non-overlapping executions, protected
production configuration, and concise logs without adding paid hosting.

## Site Load

Fast alerts matter, but the scraper should avoid unnecessary request volume against KiwiHouseSitters.

Decision: use staggered root scopes and dynamic child searches instead of
scraping every geographic level every 5 minutes. When overlapping scopes are due
together, run the broadest applicable scope and skip narrower covered scopes in
that invocation.

## Broad Search Completeness

KiwiHouseSitters broad searches can be capped around 200 visible listings. A
broad capped result is useful as a signal that the search must be split, but it
is not complete enough for lifecycle inference or historical completeness.

Decision: do not scrape All New Zealand as one unfiltered search. Either schedule
North Island and South Island separately or keep `all_nz` as a logical root that
expands into island child searches at runtime. Split over-cap searches by
location first, then by sit length only if a subregion still exceeds the cap.
Avoid house type as the primary split because the `House` bucket usually remains
too large.

## Listing Persistence Shape

The database should store normalized, useful listing fields rather than parser/debug text.

Decision: do not persist `raw_data`, `pets_raw`, or `reply_rating_text` in v1. Persist `reply_rating_score`, add `island` as a region-based aggregation, and add `total_animals` as an animal-count aggregation.

## KiwiHouseSitters Search Transport

KiwiHouseSitters filtered searches are submitted as POST form data to the base search URL. Browser-visible query parameters are not sufficient for scoped results.

Decision: keep database `site_filter` values as readable slugs and translate them inside the KiwiHouseSitters adapter to the site's form IDs. Use `requests.Session` with an initial GET followed by POST for filtered first pages. Do not introduce Playwright while server-rendered HTML plus POST form submission works.
