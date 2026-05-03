from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult


def test_scrape_result_listings_are_immutable_sequence() -> None:
    result = ScrapeResult(
        search_url="https://example.test/search",
        pages_fetched=0,
        listings=(),
    )

    assert result.listings == ()
