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

Filtered searches use a form POST to the same search URL, not query parameters. The
site can be queried with a `requests.Session`:

1. `GET /house-sitting-pet-sitting-jobs/search` to establish the session and fetch the base form.
2. `POST /house-sitting-pet-sitting-jobs/search` with form fields such as `state`, `region`, and `subregion`.
3. Parse the returned HTML like any other search page.

Observed Auckland Central payload:

```text
view=list
order=newentries
newentries=0
searchradius=50
state=north-island
region=33
subregion=178
```

The database still stores readable filter slugs, for example
`{"state":"north-island","region":"auckland","subregion":"auckland-central"}`.
The KiwiHouseSitters adapter owns translating those slugs into the site's numeric
form IDs.

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
request = initial_search_request_for_scope
url = request.url
first_page = True

while url:
    if first_page and request.form_data:
        html = post_form(url, request.form_data)
    else:
        html = fetch(url)

    soup = BeautifulSoup(html, "html.parser")
    listings.extend(parse_listings(soup))

    next_link = soup.select_one("div[id^='showmore'] a")
    url = absolute_url(next_link["href"]) if next_link else None
    first_page = False
```

Important: do not try to create `searchid` manually. Start from the first page every time and follow the site's own pagination links.

## Known Search Filters

The filter DOM has shown these form concepts:

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

Known region/subregion IDs:

The current human-reviewable map lives at:

```text
src/pet_sitting_palantir/kiwihousesitters/LOCATION_MAP.md
```

The one-off discovery workflow is documented in `discovery/README.md`. City/postcode
autocomplete uses `/postcodes/autocomplete`, but v1 does not catalog city IDs because
scopes are state/region/subregion based.

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
- pet counts by category
- `no_pets`
- `house_type`
- `starts_soon`
- `reply_rating_score`
- `content_hash`

The parser may inspect raw text such as date text, pet text, or reply-rating alt text internally, but those debug/raw fields are not part of the v1 persisted listing shape.

## Parser Notes

- `reply_rating` may appear in image alt text such as `Reply Rating 10`. Store the clean numeric value as `reply_rating_score` when possible.
- `starts_soon` is a site-provided listing signal. It is not calculated by this system.
- Store `starts_soon`, but exclude it from `content_hash`.
- Date and pet parsing can use original text internally for tests/debugging, but do not persist that raw text in v1.
