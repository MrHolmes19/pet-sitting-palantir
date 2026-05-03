# Scraping KiwiHouseSitters

## Target Site

Primary site:

```text
https://www.kiwihousesitters.co.nz
```

Search URL:

```text
https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search
```

## Site Behavior Observed

The search page appears to be server-side rendered. The initial HTML response contains the listing cards and pagination controls. v1 should use:

- `requests`
- BeautifulSoup

Do not use Playwright for v1 unless plain HTML scraping stops working.

## Pagination

The first search page returns about 20 listings. More pages are discovered through a `showmore` link.

Observed pattern:

1. Fetch the initial search URL for the scope.
2. Parse listing cards.
3. Find the link inside `div[id^='showmore']`.
4. Follow its `href`, which includes generated parameters such as `searchid` and `page=2`.
5. Repeat until no `showmore` div exists.

Pseudo-flow:

```python
url = initial_search_url_for_scope

while url:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    listings.extend(parse_listings(soup))

    next_link = soup.select_one("div[id^='showmore'] a")
    url = absolute_url(next_link["href"]) if next_link else None
```

Important: do not try to create `searchid` manually. Start from the first page every time and follow the site's own pagination links.

## Known Search Filters

The filter DOM has shown these query concepts:

- `newentries`
- `features`
- `state`
- `region`
- `subregion`
- `sitlengths`
- `petcares`
- `housetype`
- `dwelling`
- `nearby`
- `locale`

Known state values:

- `north-island`
- `south-island`

Known `sitlengths` values:

| ID | Meaning |
| ---: | --- |
| 60 | 0 - 1 week |
| 61 | 1 - 2 weeks |
| 62 | 2 - 4 weeks |
| 63 | 1 - 2 months |
| 64 | 2 months + |

Known `petcares` values:

| ID | Meaning |
| ---: | --- |
| 65 | Dogs |
| 66 | Cats |
| 67 | Fish |
| 68 | Birds |
| 262 | Rabbits/Guinea Pigs |
| 431 | Chickens/Ducks/Geese |
| 70 | Farm Animals |
| 71 | Horses |
| 69 | Reptiles |
| 246 | None |

Known house type values include:

- Cottage
- Duplex
- Farm House
- Flat
- House
- Other
- Unit

Known feature concepts include:

- Own Transport Required
- No Garden Care
- Wifi
- Buses
- Supermarket
- City
- Suburban

Features appear as `features=<id>` in the DOM. Exact IDs should be fixture-backed before being relied on.

## Listing Definition

In this project, a listing is one individual KiwiHouseSitters pet sitting job.

Example:

```text
external_id = 614020
url = /house-sitting-pet-sitting-job/614020/te-anau-southland
```

A listing is not a scrape page, a scrape run, or an alert.

## Data To Extract From Search Results

Do not enter each listing detail page in v1. Extract from search cards:

- `external_id`
- `url`
- `title`
- `listing_tag`
- `intro`
- `city`
- `region`
- `subregion`
- `start_date`
- `end_date`
- `duration_days`
- `pets_raw`
- pet counts by category
- `no_pets`
- `house_type`
- `starts_soon`
- `reply_rating_score`
- `reply_rating_text`
- `content_hash`
- optional `raw_data`

## Parser Notes

- `reply_rating` may appear in image alt text such as `Reply Rating 10`. Store the clean numeric value as `reply_rating_score` when possible.
- Keep the original string as `reply_rating_text` if useful for debugging.
- `starts_soon` is a site-provided listing signal. It is not calculated by this system.
- Store `starts_soon`, but exclude it from `content_hash`.
- Date parsing should preserve original date text in `raw_data` if present.
- Pet parsing should preserve original pet text in `pets_raw` and `raw_data`.
