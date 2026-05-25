# Scraping KiwiHouseSitters

## Target Site

Primary site:

```text
https://www.kiwihousesitters.co.nz
```

Search URL:

```text
https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search?view=list
```

## Site Behavior Observed

The search page appears to be server-side rendered. The initial HTML response contains the listing cards and pagination controls. v1 should use:

- `requests`
- BeautifulSoup

Do not use Playwright for v1 unless plain HTML scraping stops working.

Filtered searches use a form POST to the same search URL, not query parameters. The
site can be queried with a `requests.Session`:

1. `GET /house-sitting-pet-sitting-jobs/search?view=list` to establish the
   server-side search context for a filtered request.
2. `POST /house-sitting-pet-sitting-jobs/search?view=list` with complete form
   fields such as `state`, `region`, and `subregion`. Repeat the GET/POST
   pair for each new filtered leaf; attempting to reuse a prior search
   bootstrap produced inconsistent capped-result behavior.
3. Paginate each filtered search immediately before issuing the next filtered
   POST. Requests to a `showmore` link must include
   `X-Requested-With: XMLHttpRequest` and the search-page referrer. Without the
   AJAX request context, a filtered Auckland Region page 1 was followed by
   unfiltered nationwide results on page 2.
4. Parse each returned HTML response like any other search page.

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
4. Follow its `href` as an AJAX request, including `X-Requested-With:
   XMLHttpRequest` and the search-page referrer. The URL includes generated
   parameters such as `searchid` and `page=2`.
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

Production scheduled scraping should use `--max-pages all` so each due scope follows pagination until the site stops exposing a next page. Local runs may pass a numeric `--max-pages` to limit site load while testing.

The client applies the minimum request delay defined in
`src/pet_sitting_palantir/settings.py`. The selected production value is `0.5`
seconds between requests; change it deliberately only after an end-to-end run.

## Search Result Cap And Splitting

KiwiHouseSitters appears to cap broad searches at about 200 exposed listings.
The site can show an "AND THERE'S MORE..." message instead of exposing all
results. A capped search is incomplete and must not be used for missing-listing
lifecycle inference.

Before scraping a broad scope fully, parse the first page house-type counts to
estimate whether the result set is over the cap. House types are mutually
exclusive and their sum can be treated as the visible listing total. Use `200`
as the cap threshold. If that count is greater than 200, split before collecting
listing pages.
If neither count data nor the explicit capped-results message is present,
paginate the requested scope directly; absence of count metadata is not evidence
that another split is required.

Do not sum sit-length counts to estimate result size: those categories do not
reliably partition the results. Use mutually exclusive house-type counts for
the first-page estimate, and retain sit length only as a final split dimension
when a subregion is actually capped.

When a non-terminal leaf genuinely reveals an explicit cap notice during
pagination, discard its partial results and retry through the next split level.

Preferred split order:

1. Location hierarchy.
2. Sit length, only if a subregion-level search still exceeds 200.

Location hierarchy:

- All New Zealand should not scrape as one unfiltered search. Expand it into
  North Island and South Island child searches.
- Island searches over 200 should expand into region child searches.
- Region searches over 200 should expand into subregion child searches.
- Subregion searches over 200 should expand into all five sit-length child
  searches.

Sit length is the fallback split dimension because it tends to distribute
listings better than house type. Its visible counts must not be summed as a
total. House type is useful to estimate the complete result count, but is not a
preferred split because most listings are usually `House`, so it often leaves
the largest bucket capped.

If one individual subregion-plus-sit-length child still exceeds the cap, the
current v1 adapter has no further complete partition available. Fail that scope
instead of persisting an incomplete result or applying missing-listing logic.
Once a sit-length filter is selected, do not apply the aggregate filter-count
estimate again: the returned page may still expose totals for all sit lengths.
Only an explicit cap notice makes that terminal leaf incomplete.

Known sit length IDs:

| ID | Meaning |
| ---: | --- |
| 60 | 0 - 1 week |
| 61 | 1 - 2 weeks |
| 62 | 2 - 4 weeks |
| 63 | 1 - 2 months |
| 64 | 2 months + |

If a child search still hits the explicit capped-results message after splitting,
treat that run as suspicious or otherwise incomplete, keep any safely parsed
listings, and skip missing marking for that child.

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
