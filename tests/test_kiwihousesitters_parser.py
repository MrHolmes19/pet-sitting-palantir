from datetime import date

from pet_sitting_palantir.kiwihousesitters.parser import parse_search_page


def test_parse_search_page_extracts_listing_fields() -> None:
    html = """
    <div class="card primary with-header search-listing">
      <div class="card-header">
        <div class="listing-icons">
          <div class="urgent tooltip" title="Starts soon"></div>
          <div class="reply-rating">
            <img alt="Reply Rating 10" src="/rating/replyrating10.svg" />
          </div>
        </div>
      </div>
      <div class="card-body">
        <h3>
          <a href="/house-sitting-pet-sitting-job/614587/stonefields-auckland-auckland">
            Stonefields Auckland
            <span>Auckland - Auckland - Auckland - Central</span>
          </a>
        </h3>
        <div class="listing-tag">Goofy Dog in Stonefields</div>
        <p class="listing-intro">
          Looking for someone to look after one dog.
          <a href="/house-sitting-pet-sitting-job/614587/stonefields-auckland-auckland">
            View
          </a>
        </p>
        <div class="listing-footer">
          <ul class="icon-list">
            <li><span class="icon">date_range</span>12 Jun 2026 - 28 Jun 2026</li>
          </ul>
          <ul class="icon-list horizontal">
            <li><span class="icon">schedule</span>2 weeks 2 nights</li>
            <li><span class="icon">cottage</span>House</li>
          </ul>
          <ul class="listing-pets">
            <li><img alt="Dogs" src="/pets/dogs.svg" /><span>1</span></li>
            <li><img alt="Cats" src="/pets/cats.svg" /><span>0</span></li>
          </ul>
        </div>
      </div>
    </div>
    """

    listings = parse_search_page(html)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.external_id == "614587"
    assert listing.city == "Stonefields Auckland"
    assert listing.region == "Auckland"
    assert listing.subregion == "Auckland - Central"
    assert listing.start_date == date(2026, 6, 12)
    assert listing.end_date == date(2026, 6, 28)
    assert listing.duration_days == 16
    assert listing.dogs_count == 1
    assert listing.cats_count == 0
    assert listing.house_type == "House"
    assert listing.starts_soon is True
    assert listing.reply_rating_score == 10
    assert listing.content_hash is not None


def test_parse_search_page_handles_leading_separator_location() -> None:
    html = """
    <div class="card primary with-header search-listing">
      <div class="card-body">
        <h3>
          <a href="/house-sitting-pet-sitting-job/610458/new-plymouth-taranaki">
            New Plymouth
            <span> - Taranaki - New Plymouth</span>
          </a>
        </h3>
      </div>
    </div>
    """

    listing = parse_search_page(html)[0]

    assert listing.city == "New Plymouth"
    assert listing.region == "Taranaki"
    assert listing.subregion == "New Plymouth"
