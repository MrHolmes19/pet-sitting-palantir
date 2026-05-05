from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult


def test_scrape_result_listings_are_immutable_sequence() -> None:
    result = ScrapeResult(
        search_url="https://example.test/search",
        pages_fetched=0,
        listings=(),
    )

    assert result.listings == ()


def test_scrape_scope_uses_post_form_data_for_filtered_scope(monkeypatch) -> None:
    from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def fetch_search_pages(self, initial_url, *, max_pages, first_page_form_data=None):
            self.calls.append((initial_url, max_pages, first_page_form_data))
            return ()

    client = FakeClient()

    result = scrape_scope(
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        },
        max_pages=1,
        client=client,
    )

    assert result.pages_fetched == 0
    assert client.calls == [
        (
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            1,
            {
                "view": "list",
                "order": "newentries",
                "newentries": "0",
                "searchradius": "50",
                "latitude": "",
                "longitude": "",
                "stategroup": "",
                "state": "north-island",
                "region": "33",
                "subregion": "178",
                "housetype": "",
                "features": "",
                "sitlengths": "",
                "petcares": "",
                "locationname": "",
                "dates": "",
            },
        )
    ]
