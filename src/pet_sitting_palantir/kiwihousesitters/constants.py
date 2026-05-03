"""Constants for KiwiHouseSitters scraping."""

from types import MappingProxyType

BASE_URL = "https://www.kiwihousesitters.co.nz"
SEARCH_PATH = "/house-sitting-pet-sitting-jobs/search"
SEARCH_URL = f"{BASE_URL}{SEARCH_PATH}"

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_PAGES = 1
DEFAULT_SCOPE_NAME = "all_nz"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; pet-sitting-palantir/0.1; "
    "+https://github.com/leandro/pet-sitting-palantir)"
)

HTTP_OK_STATUS = 200

LISTING_CARD_SELECTOR = "div.search-listing"
LISTING_LINK_SELECTOR = 'a[href*="/house-sitting-pet-sitting-job/"]'
TITLE_LINK_SELECTOR = "h3 a"
LISTING_TAG_SELECTOR = ".listing-tag"
LISTING_INTRO_SELECTOR = ".listing-intro"
LISTING_FOOTER_ITEM_SELECTOR = ".listing-footer li"
LISTING_PETS_SELECTOR = ".listing-pets li"
NEXT_PAGE_SELECTOR = "div[id^='showmore'] a"
STARTS_SOON_SELECTOR = ".urgent[title='Starts soon'], .urgent.tooltip"
REPLY_RATING_IMAGE_SELECTOR = ".reply-rating img[alt]"

DATE_ICON_TEXT = "date_range"
DURATION_ICON_TEXT = "schedule"
HOUSE_TYPE_ICON_TEXT = "cottage"

EXTERNAL_ID_PATTERN = r"/house-sitting-pet-sitting-job/(\d+)/"
REPLY_RATING_PATTERN = r"Reply Rating\s+(\d+)"
DATE_RANGE_SEPARATOR = " - "
LOCATION_LEADING_SEPARATOR = "- "
APPROX_DATE_SUFFIX = " (approx)"
NIGHTS_PATTERN = r"(?:(\d+)\s+week[s]?)?\s*(?:(\d+)\s+night[s]?)?"
MONTH_YEAR_DATE_FORMAT = "%d %b %Y"

PET_ALT_TO_FIELD = MappingProxyType(
    {
        "Dogs": "dogs_count",
        "Cats": "cats_count",
        "Fish": "fish_count",
        "Birds": "birds_count",
        "Rabbits/Guinea Pigs": "rabbits_guinea_pigs_count",
        "Chickens/Ducks/Geese": "chickens_ducks_geese_count",
        "Farm Animals": "farm_animals_count",
        "Horses": "horses_count",
        "Reptiles": "reptiles_count",
    }
)

DEFAULT_SITE_FILTERS = MappingProxyType(
    {
        "all_nz": {},
        "north_island": {"state": "north-island"},
        "auckland_region": {"state": "north-island", "region": "auckland"},
        "auckland_central": {
            "state": "north-island",
            "region": "auckland",
            "subregion": ["auckland-central"],
        },
    }
)
