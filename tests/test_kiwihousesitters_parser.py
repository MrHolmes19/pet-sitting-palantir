from datetime import date
from pathlib import Path

from pet_sitting_palantir.kiwihousesitters.parser import (
    parse_estimated_result_count,
    parse_search_filter_counts,
    parse_search_page,
    search_page_has_cap_notice,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


def test_parse_search_page_extracts_listing_fields() -> None:
    listings = parse_search_page(_fixture("search_listing_auckland_central.html"))

    assert len(listings) == 1
    listing = listings[0]
    assert listing.external_id == "614587"
    assert listing.island == "North Island"
    assert listing.city == "Stonefields Auckland"
    assert listing.region == "Auckland"
    assert listing.subregion == "Auckland - Central"
    assert listing.start_date == date(2026, 6, 12)
    assert listing.end_date == date(2026, 6, 28)
    assert listing.duration_days == 16
    assert listing.total_animals == 1
    assert listing.dogs_count == 1
    assert listing.cats_count == 0
    assert listing.house_type == "House"
    assert listing.starts_soon is True
    assert listing.reply_rating_score == 10
    assert listing.content_hash is not None
    assert "raw_data" not in listing.to_dict()
    assert "pets_raw" not in listing.to_dict()
    assert "reply_rating_text" not in listing.to_dict()


def test_parse_search_page_handles_leading_separator_location() -> None:
    listing = parse_search_page(_fixture("search_listing_leading_separator.html"))[0]

    assert listing.city == "New Plymouth"
    assert listing.region == "Taranaki"
    assert listing.subregion == "New Plymouth"


def test_parse_search_page_normalizes_short_auckland_subregion() -> None:
    listings = parse_search_page(
        """
        <div class="card primary with-header search-listing">
          <div class="card-body">
            <h3>
              <a href="/house-sitting-pet-sitting-job/614540/point-chevalier-auckland">
                Point Chevalier
                <span> - Auckland - Central</span>
              </a>
            </h3>
          </div>
        </div>
        """
    )

    assert listings[0].city == "Point Chevalier"
    assert listings[0].region == "Auckland"
    assert listings[0].subregion == "Auckland - Central"


def test_parse_search_page_extracts_multiple_real_page_style_cards() -> None:
    listings = parse_search_page(_fixture("search_page_multiple_listings.html"))

    assert [listing.external_id for listing in listings] == ["614587", "607595"]
    assert listings[0].island == "North Island"
    assert listings[0].total_animals == 1
    assert listings[1].city == "Masterton"
    assert listings[1].region == "Wairarapa"
    assert listings[1].total_animals == 4
    assert listings[1].starts_soon is False


def test_parse_search_filter_counts_extracts_sit_lengths_and_estimated_total() -> None:
    html = """
    <li id="sit-length-options" class="check-list" style="display:none;">
      <div data-featureid="60" class="feature-filter">
        <a
          href="/house-sitting-pet-sitting-jobs/search?display=list&amp;state=north-island&amp;sitlengths=60"
        >
          <span class="label">0 - 1 week (98)</span>
        </a>
      </div>
      <div data-featureid="61" class="feature-filter">
        <a
          href="/house-sitting-pet-sitting-jobs/search?display=list&amp;state=north-island&amp;sitlengths=61"
        >
          <span class="label">1 - 2 weeks (109)</span>
        </a>
      </div>
      <div data-featureid="62" class="feature-filter">
        <a
          href="/house-sitting-pet-sitting-jobs/search?display=list&amp;state=north-island&amp;sitlengths=62"
        >
          <span class="label">2 - 4 weeks (134)</span>
        </a>
      </div>
    </li>
    """

    counts = parse_search_filter_counts(html)

    assert [(count.field, count.value, count.count) for count in counts] == [
        ("sitlengths", "60", 98),
        ("sitlengths", "61", 109),
        ("sitlengths", "62", 134),
    ]
    assert parse_estimated_result_count(html) == 341


def test_search_page_has_cap_notice_detects_hidden_result_message() -> None:
    html = """
    <div class="search-list-results"></div>
    <h3>And there's more...</h3>
    <p>Rather than show you the whole list, add filters.</p>
    """

    assert search_page_has_cap_notice(html) is True
