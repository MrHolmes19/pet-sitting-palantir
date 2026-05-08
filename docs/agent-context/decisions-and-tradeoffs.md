# Decisions And Tradeoffs

This file records conceptual product and architecture decisions as they are made. Keep implementation details in the topic-specific docs.

## Frequency

We want early notifications, but GitHub Actions is not reliable enough to be the
long-term scheduler for fast alerts. It accepts cron syntax such as
`*/5 * * * *`, but scheduled workflows are best-effort. Production observation
showed the scraper running much less often than every 5 minutes.

Decision: keep the GitHub Actions workflow disabled until scraper splitting and
lifecycle safety are fixed. If GitHub Actions is re-enabled, treat it as a cheap
opportunistic runner, not a dependable 5-minute alerting scheduler. For reliable
fast Auckland alerts, use an external scheduler or always-on worker.

## Geographic Priority

Notification value is highest for Auckland Central. North Shore City, inside the Auckland Region scope, is the second most important area.

Decision: optimize alerting around Auckland Central first, then North Shore City. Broader scopes such as North Island and All New Zealand are mainly for history collection, market visibility, and future behavior analysis.

## Capture Before Analytics

The system will eventually support analytics, but analytics are only useful if the underlying capture is reliable.

Decision: build scraper quality, persistence, lifecycle handling, and alerts before dashboards or analysis jobs.

## Cost And Maintenance

This is a personal project, so operational simplicity matters more than completeness.

Decision: prefer cheap, boring infrastructure and small implementation phases. Avoid services or architecture that create maintenance work before the scraper has proven useful.

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
