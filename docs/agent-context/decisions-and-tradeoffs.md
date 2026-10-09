# Decisions And Tradeoffs

This file records conceptual product and architecture decisions as they are made. Keep implementation details in the topic-specific docs.

## Production Runtime

Decision: run the production workflow from an always-on home machine, while
scope cadence remains database-configured.

The rationale, failed hosted approaches, quiet-hours policy, and pending
operational requirements are owned by
[scheduling.md](scheduling.md).

## Geographic Priority

Notification value is highest for Auckland Central. North Shore City, inside the Auckland Region scope, is the second most important area.

Decision: optimize alerting around Auckland Central first, then North Shore City. Broader scopes such as North Island and All New Zealand are mainly for history collection, market visibility, and future behavior analysis.

## Alert Configuration

Decision: keep human-edited defaults in `config/alert_filter_defaults.json`
and named alert overrides in `config/alert_filters.json`. Each custom filter
must supply its geography; it inherits local and delivery settings from the
complete defaults template. Alert filters describe matching geography
independently of scrape scopes, so a broader complete scrape can still trigger
a narrower matching filter. Delivery settings are filter-owned and
channel-neutral; Telegram is only the first sender implementation.

## Capture Before Analytics

The system will eventually support analytics, but analytics are only useful if the underlying capture is reliable.

Decision: build scraper quality, persistence, lifecycle handling, and alerts before dashboards or analysis jobs.

## Local Analytics Dashboard

Decision: build analytics as a local, command-driven dashboard rather than a
hosted app or separate frontend/backend application. Use DuckDB as a refreshable
local analytics snapshot, Streamlit for the local UI server, and Plotly for
interactive charts. Build against synthetic data first so the dashboard can be
designed before months or years of real data exist.

The detailed analytics plan, metrics, and dashboard shape are owned by
[analytics.md](analytics.md).

## Cost And Maintenance

This is a personal project, so operational simplicity matters more than completeness.

Decision: prefer cheap, boring infrastructure and small implementation phases. Avoid services or architecture that create maintenance work before the scraper has proven useful.

## Site Load

Fast alerts matter, but the scraper should avoid unnecessary request volume against KiwiHouseSitters.

Decision: preserve the fast Auckland scopes and the existing `all_nz` and
`north_island` identities. Every tick runs Auckland and its alert delivery
before optional deadline-bounded broad work. Broad failures and WAF protection
never suppress or reschedule Auckland. A challenge received by an Auckland
scope pauses only that exact scope for 15 minutes; this protects the shared IP
without turning a broad failure into an Auckland outage. Try the original
complete broad strategy first, but convert it into a restart-safe
region-by-region campaign if it hits a WAF challenge or exhausts its background
time budget. Remember recent WAF history so a new campaign can start directly
with the safer fallback. Add request and inter-leaf jitter, and persist both
campaign progress and circuit state so restarts cannot erase them.

## Broad Search Completeness

KiwiHouseSitters broad searches can be capped around 200 visible listings. A
broad capped result is useful as a signal that the search must be split, but it
is not complete enough for lifecycle inference or historical completeness.

Decision: keep All New Zealand and North Island as independently scheduled
logical scopes. A direct complete attempt may finish the campaign; otherwise
stage complete regional leaves, merge and deduplicate only when all leaves
succeed, then atomically persist under the original parent scope. Partial
campaigns cannot advance freshness or mark listings missing. Broad completion
advances only its own parent and never changes Auckland freshness. Regional
missing inference has exclusive ownership: `all_nz` covers South Island and
`north_island` covers non-Auckland North Island. This prevents overlapping
campaigns from advancing the shared missing counter twice. Every staged
observation keeps its leaf timestamp so delayed broad data cannot overwrite
fresher golden data.
Continue splitting capped region searches by subregion and then sit length.
Avoid house type as the primary split because the `House` bucket usually
remains too large.

## Listing Persistence Shape

The database should store normalized, useful listing fields rather than parser/debug text.

Decision: do not persist `raw_data`, `pets_raw`, or `reply_rating_text` in v1. Persist `reply_rating_score`, add `island` as a region-based aggregation, and add `total_animals` as an animal-count aggregation.

## KiwiHouseSitters Search Transport

KiwiHouseSitters filtered searches are submitted as POST form data to the base search URL. Browser-visible query parameters are not sufficient for scoped results.

Decision: keep database `site_filter` values as readable slugs and translate them inside the KiwiHouseSitters adapter to the site's form IDs. Use `requests.Session` with an initial GET followed by POST for filtered first pages. Do not introduce Playwright while server-rendered HTML plus POST form submission works.
