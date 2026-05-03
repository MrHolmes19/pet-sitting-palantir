# Decisions And Tradeoffs

This file records conceptual product and architecture decisions as they are made. Keep implementation details in the topic-specific docs.

## Frequency

We want early notifications, but GitHub Actions does not support schedules below 5 minutes. Going below 5 minutes would push the project toward paid services, an always-on worker, or a more complex hosting setup.

Decision: keep GitHub Actions at 5 minutes for v1 and use database-backed scopes to control actual scrape frequency.

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

Decision: use staggered scopes instead of scraping every geographic level every 5 minutes.
