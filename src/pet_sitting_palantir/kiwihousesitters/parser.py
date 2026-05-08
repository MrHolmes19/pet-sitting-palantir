"""HTML parser for KiwiHouseSitters search result pages."""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.kiwihousesitters.constants import (
    ANIMAL_COUNT_FIELDS,
    APPROX_DATE_SUFFIX,
    BASE_URL,
    DATE_ICON_TEXT,
    DATE_RANGE_SEPARATOR,
    DURATION_ICON_TEXT,
    EXTERNAL_ID_PATTERN,
    HOUSE_TYPE_ICON_TEXT,
    LISTING_CARD_SELECTOR,
    LISTING_FOOTER_ITEM_SELECTOR,
    LISTING_INTRO_SELECTOR,
    LISTING_LINK_SELECTOR,
    LISTING_PETS_SELECTOR,
    LISTING_TAG_SELECTOR,
    LOCATION_LEADING_SEPARATOR,
    MONTH_YEAR_DATE_FORMAT,
    NIGHTS_PATTERN,
    PET_ALT_TO_FIELD,
    REGION_TO_ISLAND,
    REPLY_RATING_IMAGE_SELECTOR,
    REPLY_RATING_PATTERN,
    SEARCH_CAP_NOTICE_TEXT,
    STARTS_SOON_SELECTOR,
    TITLE_LINK_SELECTOR,
)
from pet_sitting_palantir.utils.hashing import stable_content_hash

AUCKLAND_SUBREGION_ALIASES = {
    "Central": "Auckland - Central",
    "North": "Auckland - North",
    "South": "Auckland - South",
    "West": "Auckland - West",
}

FILTER_COUNT_QUERY_FIELDS = (
    "subregion",
    "region",
    "sitlengths",
    "housetype",
    "state",
)
FILTER_COUNT_TOTAL_FIELDS = ("sitlengths", "housetype")
FILTER_COUNT_PATTERN = re.compile(r"^(?P<label>.+?)\s*\((?P<count>[\d,]+)\)\s*$")


@dataclass(frozen=True)
class SearchFilterCount:
    """One visible search-filter option with a result count."""

    field: str
    value: str
    label: str
    count: int


def parse_search_page(html: str) -> list[Listing]:
    """Parse all listing cards from a KiwiHouseSitters search page."""
    soup = BeautifulSoup(html, "html.parser")
    return [parse_listing_card(card) for card in soup.select(LISTING_CARD_SELECTOR)]


def parse_search_filter_counts(html: str) -> tuple[SearchFilterCount, ...]:
    """Parse result counts exposed beside search filter options."""
    soup = BeautifulSoup(html, "html.parser")
    counts: list[SearchFilterCount] = []

    for link in soup.select("a[href]"):
        label_text = _text_or_none(link.select_one(".label")) or _text_or_none(link)
        if label_text is None:
            continue

        match = FILTER_COUNT_PATTERN.match(label_text)
        if not match:
            continue

        query = parse_qs(urlparse(str(link.get("href", ""))).query)
        field = _filter_count_field(query)
        if field is None:
            continue

        value = query[field][0]
        if not value:
            continue

        counts.append(
            SearchFilterCount(
                field=field,
                value=value,
                label=match.group("label").strip(),
                count=int(match.group("count").replace(",", "")),
            )
        )

    return tuple(counts)


def parse_estimated_result_count(html: str) -> int | None:
    """Estimate result count from mutually exclusive visible filter buckets."""
    counts = parse_search_filter_counts(html)
    for field in FILTER_COUNT_TOTAL_FIELDS:
        field_counts = [option.count for option in counts if option.field == field]
        if field_counts:
            return sum(field_counts)
    return None


def search_page_has_cap_notice(html: str) -> bool:
    """Return whether the page says the search has more hidden results."""
    return SEARCH_CAP_NOTICE_TEXT in _normalize_text(
        BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    ).upper()


def parse_listing_card(card: Tag) -> Listing:
    """Parse one listing card into a normalized listing."""
    link = _required_link(card)
    relative_url = link["href"]
    absolute_url = urljoin(BASE_URL, relative_url)
    external_id = _extract_external_id(relative_url)

    title_link = card.select_one(TITLE_LINK_SELECTOR)
    title, city, region, subregion = _parse_title_location(title_link)

    listing_tag = _text_or_none(card.select_one(LISTING_TAG_SELECTOR))
    intro = _parse_intro(card)
    footer_values = _parse_footer_values(card)
    pet_values = _parse_pets(card)
    reply_rating_score = _parse_reply_rating(card)
    starts_soon = card.select_one(STARTS_SOON_SELECTOR) is not None
    start_date, end_date = _parse_date_range(footer_values.get("dates_text"))
    duration_days = _parse_duration_days(footer_values.get("duration_text"))
    total_animals = _total_animals(pet_values)

    listing = Listing(
        external_id=external_id,
        content_hash="",
        island=REGION_TO_ISLAND.get(region) if region else None,
        region=region,
        subregion=subregion,
        city=city,
        duration_days=duration_days or _date_delta_days(start_date, end_date),
        start_date=start_date,
        end_date=end_date,
        house_type=footer_values.get("house_type"),
        total_animals=total_animals,
        dogs_count=pet_values["dogs_count"],
        cats_count=pet_values["cats_count"],
        fish_count=pet_values["fish_count"],
        birds_count=pet_values["birds_count"],
        rabbits_guinea_pigs_count=pet_values["rabbits_guinea_pigs_count"],
        chickens_ducks_geese_count=pet_values["chickens_ducks_geese_count"],
        farm_animals_count=pet_values["farm_animals_count"],
        horses_count=pet_values["horses_count"],
        reptiles_count=pet_values["reptiles_count"],
        other_pets_count=pet_values["other_pets_count"],
        no_pets=pet_values["no_pets"],
        starts_soon=starts_soon,
        reply_rating_score=reply_rating_score,
        listing_tag=listing_tag,
        title=title,
        intro=intro,
        url=absolute_url,
    )

    return replace(listing, content_hash=_content_hash_for_listing(listing))


def _required_link(card: Tag) -> Tag:
    link = card.select_one(LISTING_LINK_SELECTOR)
    if link is None or not link.get("href"):
        raise ValueError("Listing card does not contain a listing link")
    return link


def _extract_external_id(url: str) -> str:
    match = re.search(EXTERNAL_ID_PATTERN, url)
    if not match:
        raise ValueError(f"Could not extract external listing id from URL: {url}")
    return match.group(1)


def _parse_title_location(
    title_link: Tag | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if title_link is None:
        return None, None, None, None

    title_text = _normalize_text(title_link.get_text(" ", strip=True))
    span = title_link.find("span")
    direct_title_text = _normalize_text(
        " ".join(
            str(child).strip()
            for child in title_link.children
            if isinstance(child, str) and child.strip()
        )
    )
    location_tail = _normalize_text(span.get_text(" ", strip=True)) if span else None
    if location_tail:
        location_tail = location_tail.removeprefix(LOCATION_LEADING_SEPARATOR)
    city = direct_title_text or title_text or None

    if not location_tail:
        return title_text or None, city, None, None

    location_parts = [
        part.strip() for part in location_tail.split(DATE_RANGE_SEPARATOR) if part.strip()
    ]
    region = None
    subregion = None

    if len(location_parts) == 1:
        region = location_parts[0]
    elif len(location_parts) == 2:
        region = location_parts[0]
        subregion = location_parts[1]
    elif len(location_parts) == 3:
        region = location_parts[1]
        subregion = location_parts[2]
    elif len(location_parts) >= 4:
        region = location_parts[1]
        subregion = DATE_RANGE_SEPARATOR.join(location_parts[2:])

    return title_text or None, city, region, _normalize_subregion(region, subregion)


def _parse_intro(card: Tag) -> str | None:
    intro = card.select_one(LISTING_INTRO_SELECTOR)
    if intro is None:
        return None

    intro_copy = BeautifulSoup(str(intro), "html.parser")
    for link in intro_copy.select("a"):
        link.decompose()

    return _text_or_none(intro_copy)


def _normalize_subregion(region: str | None, subregion: str | None) -> str | None:
    if region == "Auckland" and subregion in AUCKLAND_SUBREGION_ALIASES:
        return AUCKLAND_SUBREGION_ALIASES[subregion]
    return subregion


def _parse_footer_values(card: Tag) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "dates_text": None,
        "duration_text": None,
        "house_type": None,
    }

    for item in card.select(LISTING_FOOTER_ITEM_SELECTOR):
        icon = item.select_one(".icon")
        if icon is None:
            continue

        icon_text = _normalize_text(icon.get_text(" ", strip=True))
        item_text = _item_text_without_icon(item)

        if icon_text == DATE_ICON_TEXT:
            values["dates_text"] = item_text
        elif icon_text == DURATION_ICON_TEXT:
            values["duration_text"] = item_text
        elif icon_text == HOUSE_TYPE_ICON_TEXT:
            values["house_type"] = item_text

    return values


def _parse_pets(card: Tag) -> dict[str, int | bool]:
    values: dict[str, int | bool] = {
        "dogs_count": 0,
        "cats_count": 0,
        "fish_count": 0,
        "birds_count": 0,
        "rabbits_guinea_pigs_count": 0,
        "chickens_ducks_geese_count": 0,
        "farm_animals_count": 0,
        "horses_count": 0,
        "reptiles_count": 0,
        "other_pets_count": 0,
        "no_pets": False,
    }

    for item in card.select(LISTING_PETS_SELECTOR):
        image = item.select_one("img[alt]")
        count_text = _text_or_none(item.select_one("span"))

        if image is None or count_text is None:
            continue

        pet_name = image["alt"]
        count = _parse_int(count_text)
        field_name = PET_ALT_TO_FIELD.get(pet_name)

        if field_name:
            values[field_name] = count
        elif pet_name.lower() == "none":
            values["no_pets"] = True
        else:
            values["other_pets_count"] = int(values["other_pets_count"]) + count

    return values


def _parse_reply_rating(card: Tag) -> int | None:
    image = card.select_one(REPLY_RATING_IMAGE_SELECTOR)
    if image is None:
        return None

    alt_text = image.get("alt")
    if not alt_text:
        return None

    match = re.search(REPLY_RATING_PATTERN, alt_text)
    return int(match.group(1)) if match else None


def _parse_date_range(dates_text: str | None) -> tuple[date | None, date | None]:
    if not dates_text:
        return None, None

    cleaned = dates_text.replace(APPROX_DATE_SUFFIX, "").strip()
    if DATE_RANGE_SEPARATOR not in cleaned:
        return None, None

    start_text, end_text = cleaned.split(DATE_RANGE_SEPARATOR, maxsplit=1)
    return _parse_date(start_text), _parse_date(end_text)


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), MONTH_YEAR_DATE_FORMAT).date()
    except ValueError:
        return None


def _parse_duration_days(duration_text: str | None) -> int | None:
    if not duration_text:
        return None

    match = re.fullmatch(NIGHTS_PATTERN, duration_text.strip())
    if not match:
        return None

    weeks = int(match.group(1) or 0)
    nights = int(match.group(2) or 0)
    total = weeks * 7 + nights
    return total or None


def _date_delta_days(start_date: date | None, end_date: date | None) -> int | None:
    if not start_date or not end_date:
        return None

    return (end_date - start_date).days


def _total_animals(pet_values: dict[str, int | bool]) -> int:
    return sum(int(pet_values[field]) for field in ANIMAL_COUNT_FIELDS)


def _content_hash_for_listing(listing: Listing) -> str:
    content = {
        "external_id": listing.external_id,
        "title": listing.title,
        "island": listing.island,
        "city": listing.city,
        "region": listing.region,
        "subregion": listing.subregion,
        "start_date": listing.start_date,
        "end_date": listing.end_date,
        "duration_days": listing.duration_days,
        "total_animals": listing.total_animals,
        "dogs_count": listing.dogs_count,
        "cats_count": listing.cats_count,
        "fish_count": listing.fish_count,
        "birds_count": listing.birds_count,
        "rabbits_guinea_pigs_count": listing.rabbits_guinea_pigs_count,
        "chickens_ducks_geese_count": listing.chickens_ducks_geese_count,
        "farm_animals_count": listing.farm_animals_count,
        "horses_count": listing.horses_count,
        "reptiles_count": listing.reptiles_count,
        "other_pets_count": listing.other_pets_count,
        "no_pets": listing.no_pets,
        "house_type": listing.house_type,
        "reply_rating_score": listing.reply_rating_score,
        "listing_tag": listing.listing_tag,
        "intro": listing.intro,
    }
    return stable_content_hash(content)


def _item_text_without_icon(item: Tag) -> str | None:
    item_copy = BeautifulSoup(str(item), "html.parser")
    icon = item_copy.select_one(".icon")
    if icon:
        icon.decompose()
    return _text_or_none(item_copy)


def _text_or_none(tag: Tag | BeautifulSoup | None) -> str | None:
    if tag is None:
        return None

    text = _normalize_text(tag.get_text(" ", strip=True))
    return text or None


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _filter_count_field(query: dict[str, list[str]]) -> str | None:
    for field in FILTER_COUNT_QUERY_FIELDS:
        if query.get(field):
            return field
    return None
