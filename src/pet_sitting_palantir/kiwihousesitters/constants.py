"""Constants for KiwiHouseSitters scraping."""

from types import MappingProxyType

BASE_URL = "https://www.kiwihousesitters.co.nz"
SEARCH_PATH = "/house-sitting-pet-sitting-jobs/search"
SEARCH_URL = f"{BASE_URL}{SEARCH_PATH}?view=list"

DEFAULT_MAX_PAGES = 1
DEFAULT_SCOPE_NAME = "all_nz"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
DEFAULT_REQUEST_HEADERS = MappingProxyType(
    {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-NZ,en;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Referer": BASE_URL,
        "Upgrade-Insecure-Requests": "1",
    }
)
PAGINATION_REQUEST_HEADERS = MappingProxyType(
    {
        "X-Requested-With": "XMLHttpRequest",
    }
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
SEARCH_CAP_NOTICE_TEXT = "AND THERE'S MORE"
SEARCH_RESULT_CAP = 200

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

NORTH_ISLAND = "North Island"
SOUTH_ISLAND = "South Island"

REGION_TO_ISLAND = MappingProxyType(
    {
        "Auckland": NORTH_ISLAND,
        "Bay of Plenty": NORTH_ISLAND,
        "Gisborne": NORTH_ISLAND,
        "Hawke's Bay": NORTH_ISLAND,
        "Manawatū-Whanganui": NORTH_ISLAND,
        "Northland": NORTH_ISLAND,
        "Taranaki": NORTH_ISLAND,
        "Waikato": NORTH_ISLAND,
        "Wairarapa": NORTH_ISLAND,
        "Wellington": NORTH_ISLAND,
        "Canterbury": SOUTH_ISLAND,
        "Nelson / Marlborough": SOUTH_ISLAND,
        "Otago": SOUTH_ISLAND,
        "Southland": SOUTH_ISLAND,
        "West Coast": SOUTH_ISLAND,
    }
)

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

ANIMAL_COUNT_FIELDS = (
    "dogs_count",
    "cats_count",
    "fish_count",
    "birds_count",
    "rabbits_guinea_pigs_count",
    "chickens_ducks_geese_count",
    "farm_animals_count",
    "horses_count",
    "reptiles_count",
    "other_pets_count",
)

SIT_LENGTH_IDS = ("60", "61", "62", "63", "64")

DEFAULT_SITE_FILTERS = MappingProxyType(
    {
        "all_nz": {},
        "north_island": {"state": "north-island"},
        "auckland_region": {"state": "north-island", "region": "auckland"},
        "north_shore_city": {
            "state": "north-island",
            "region": "auckland",
            "subregion": "north-shore-city",
        },
        "auckland_central": {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        },
    }
)
