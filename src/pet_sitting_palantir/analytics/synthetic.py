"""Synthetic analytics data generation."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from random import Random
from typing import Any

import duckdb
import pandas as pd

from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS, STATE_LABELS

DEFAULT_DEMO_DATABASE_PATH = Path(".analytics/demo.duckdb")
DEFAULT_LISTING_COUNT = 3_000
DEFAULT_SEED = 20260601

DATE_RANGE_START = date(2024, 1, 1)
DATE_RANGE_END = date(2027, 12, 31)
DEMO_REFERENCE_DATE = date(2026, 6, 1)

MONTH_WEIGHTS = {
    1: 1.8,
    2: 1.2,
    3: 1.0,
    4: 0.85,
    5: 0.7,
    6: 0.65,
    7: 0.85,
    8: 0.95,
    9: 1.1,
    10: 1.25,
    11: 1.45,
    12: 2.0,
}

AUCKLAND_SUBREGION_WEIGHTS = {
    "auckland-central": 14.0,
    "north-shore-city": 8.0,
    "auckland-north": 5.0,
    "auckland-south": 4.0,
    "manukau": 3.0,
    "waitakere": 3.0,
    "rodney": 2.0,
    "waiheke-island": 1.2,
}

REGION_WEIGHTS = {
    "auckland": 7.0,
    "canterbury": 4.0,
    "wellington": 3.5,
    "waikato": 3.0,
    "bay-of-plenty": 2.5,
    "otago": 2.5,
    "northland": 2.0,
    "nelson-marlborough": 1.8,
    "hawkes-bay": 1.7,
}

CITY_BY_SUBREGION = {
    "auckland-central": (
        "Auckland CBD",
        "Grey Lynn",
        "Mount Eden",
        "Parnell",
        "Ponsonby",
        "Remuera",
        "Stonefields",
    ),
    "north-shore-city": ("Takapuna", "Devonport", "Milford", "Birkenhead", "Albany"),
    "auckland-north": ("Orewa", "Silverdale", "Warkworth", "Hibiscus Coast"),
    "auckland-south": ("Papakura", "Pukekohe", "Takanini", "Drury"),
    "manukau": ("Howick", "Manukau", "Mangere", "Botany Downs"),
    "waitakere": ("Henderson", "Titirangi", "New Lynn", "Glen Eden"),
    "christchurch": ("Christchurch", "Riccarton", "Sumner", "Cashmere"),
    "wellington": ("Wellington", "Karori", "Mount Victoria", "Island Bay"),
    "queenstown-lakes": ("Queenstown", "Wanaka", "Arrowtown"),
    "tauranga": ("Tauranga", "Mount Maunganui", "Papamoa"),
    "hamilton": ("Hamilton", "Cambridge", "Te Awamutu"),
    "nelson": ("Nelson", "Richmond", "Stoke"),
    "dunedin": ("Dunedin", "Mosgiel", "Port Chalmers"),
}

HOUSE_TYPES = ("House", "Townhouse", "Apartment", "Unit", "Lifestyle block")

LISTING_COLUMNS = (
    "id",
    "external_id",
    "content_hash",
    "island",
    "region",
    "subregion",
    "city",
    "duration_days",
    "start_date",
    "end_date",
    "house_type",
    "total_animals",
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
    "no_pets",
    "starts_soon",
    "reply_rating_score",
    "listing_tag",
    "title",
    "intro",
    "url",
    "first_seen_at",
    "last_seen_at",
    "first_seen_run_id",
    "last_seen_run_id",
    "first_seen_context",
    "status",
    "missing_count",
    "missing_since",
    "closed_at",
    "appearance_sequence",
    "created_at",
    "updated_at",
)

CREATE_LISTINGS_SQL = """
create table listings (
  id bigint,
  external_id text,
  content_hash text,
  island text,
  region text,
  subregion text,
  city text,
  duration_days integer,
  start_date date,
  end_date date,
  house_type text,
  total_animals integer,
  dogs_count integer,
  cats_count integer,
  fish_count integer,
  birds_count integer,
  rabbits_guinea_pigs_count integer,
  chickens_ducks_geese_count integer,
  farm_animals_count integer,
  horses_count integer,
  reptiles_count integer,
  other_pets_count integer,
  no_pets boolean,
  starts_soon boolean,
  reply_rating_score integer,
  listing_tag text,
  title text,
  intro text,
  url text,
  first_seen_at timestamp,
  last_seen_at timestamp,
  first_seen_run_id bigint,
  last_seen_run_id bigint,
  first_seen_context text,
  status text,
  missing_count integer,
  missing_since timestamp,
  closed_at timestamp,
  appearance_sequence integer,
  created_at timestamp,
  updated_at timestamp
)
"""


@dataclass(frozen=True)
class DemoGenerationResult:
    """Summary of a generated demo analytics database."""

    output_path: Path
    listing_count: int
    seed: int
    start_date_min: date
    start_date_max: date

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "output_path": str(self.output_path),
            "listing_count": self.listing_count,
            "seed": self.seed,
            "start_date_min": self.start_date_min,
            "start_date_max": self.start_date_max,
        }


@dataclass(frozen=True)
class SyntheticListing:
    """Synthetic listing row shaped like the analytics-facing listings table."""

    id: int
    external_id: str
    content_hash: str
    island: str
    region: str
    subregion: str
    city: str
    duration_days: int
    start_date: date
    end_date: date
    house_type: str
    total_animals: int
    dogs_count: int
    cats_count: int
    fish_count: int
    birds_count: int
    rabbits_guinea_pigs_count: int
    chickens_ducks_geese_count: int
    farm_animals_count: int
    horses_count: int
    reptiles_count: int
    other_pets_count: int
    no_pets: bool
    starts_soon: bool
    reply_rating_score: int | None
    listing_tag: str
    title: str
    intro: str
    url: str
    first_seen_at: datetime
    last_seen_at: datetime
    first_seen_run_id: int | None
    last_seen_run_id: int | None
    first_seen_context: str
    status: str
    missing_count: int
    missing_since: datetime | None
    closed_at: datetime | None
    appearance_sequence: int
    created_at: datetime
    updated_at: datetime


def write_demo_database(
    *,
    output_path: Path = DEFAULT_DEMO_DATABASE_PATH,
    listing_count: int = DEFAULT_LISTING_COUNT,
    seed: int = DEFAULT_SEED,
) -> DemoGenerationResult:
    """Write a deterministic synthetic analytics database."""
    if listing_count < 1:
        raise ValueError("listing_count must be greater than zero")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    listings = generate_synthetic_listings(listing_count=listing_count, seed=seed)
    frame = pd.DataFrame(
        [
            {column: asdict(listing)[column] for column in LISTING_COLUMNS}
            for listing in listings
        ]
    )

    with duckdb.connect(str(output_path)) as connection:
        connection.execute(CREATE_LISTINGS_SQL)
        connection.register("synthetic_listings", frame)
        connection.execute(f"""
            insert into listings ({", ".join(LISTING_COLUMNS)})
            select {", ".join(LISTING_COLUMNS)}
            from synthetic_listings
        """)
        connection.execute("""
            create table analytics_metadata (
              key text primary key,
              value text
            )
        """)
        connection.executemany(
            "insert into analytics_metadata values (?, ?)",
            [
                ("source", "synthetic"),
                ("seed", str(seed)),
                ("listing_count", str(listing_count)),
                ("generated_at", datetime.now(UTC).isoformat()),
                ("reference_date", DEMO_REFERENCE_DATE.isoformat()),
            ],
        )

    return DemoGenerationResult(
        output_path=output_path,
        listing_count=len(listings),
        seed=seed,
        start_date_min=min(listing.start_date for listing in listings),
        start_date_max=max(listing.start_date for listing in listings),
    )


def generate_synthetic_listings(
    *,
    listing_count: int = DEFAULT_LISTING_COUNT,
    seed: int = DEFAULT_SEED,
) -> list[SyntheticListing]:
    """Generate deterministic fake listings with useful seasonal patterns."""
    if listing_count < 1:
        raise ValueError("listing_count must be greater than zero")

    random = Random(seed)
    return [_generate_listing(index=index, random=random) for index in range(1, listing_count + 1)]


def _generate_listing(*, index: int, random: Random) -> SyntheticListing:
    location = _choose_location(random)
    start_date = _choose_start_date(random)
    duration_days = _choose_duration_days(random, start_date)
    end_date = start_date + timedelta(days=duration_days - 1)
    lead_time_days = _choose_lead_time_days(random, duration_days)
    first_seen_at = _with_random_time(random, start_date - timedelta(days=lead_time_days))
    last_seen_at = _choose_last_seen_at(random, first_seen_at, end_date)
    pet_counts = _choose_pet_counts(random)
    total_animals = sum(value for key, value in pet_counts.items() if key.endswith("_count"))
    external_id = f"demo-{index:06d}"
    listing_tag = _listing_tag(location["city"], pet_counts)
    title = f"{listing_tag} in {location['city']}"
    status, missing_count, missing_since, closed_at = _choose_status(random, end_date, last_seen_at)
    first_seen_context = _first_seen_context(first_seen_at)
    created_at = first_seen_at
    updated_at = max(first_seen_at, last_seen_at)

    content_hash = sha256(
        "|".join(
            [
                external_id,
                location["subregion"],
                location["city"],
                start_date.isoformat(),
                end_date.isoformat(),
                str(total_animals),
            ]
        ).encode()
    ).hexdigest()

    return SyntheticListing(
        id=index,
        external_id=external_id,
        content_hash=content_hash,
        island=location["island"],
        region=location["region"],
        subregion=location["subregion"],
        city=location["city"],
        duration_days=duration_days,
        start_date=start_date,
        end_date=end_date,
        house_type=_weighted_choice(
            random,
            (
                ("House", 7.0),
                ("Townhouse", 2.0),
                ("Apartment", 1.5),
                ("Unit", 1.2),
                ("Lifestyle block", 0.6),
            ),
        ),
        total_animals=total_animals,
        dogs_count=pet_counts["dogs_count"],
        cats_count=pet_counts["cats_count"],
        fish_count=pet_counts["fish_count"],
        birds_count=pet_counts["birds_count"],
        rabbits_guinea_pigs_count=pet_counts["rabbits_guinea_pigs_count"],
        chickens_ducks_geese_count=pet_counts["chickens_ducks_geese_count"],
        farm_animals_count=pet_counts["farm_animals_count"],
        horses_count=pet_counts["horses_count"],
        reptiles_count=pet_counts["reptiles_count"],
        other_pets_count=pet_counts["other_pets_count"],
        no_pets=pet_counts["no_pets"],
        starts_soon=lead_time_days <= 10,
        reply_rating_score=random.choice((None, 6, 7, 8, 9, 10)),
        listing_tag=listing_tag,
        title=title,
        intro=_intro_text(duration_days, location["city"]),
        url=(
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-job/"
            f"{600000 + index}/{location['city'].lower().replace(' ', '-')}"
        ),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        first_seen_run_id=None,
        last_seen_run_id=None,
        first_seen_context=first_seen_context,
        status=status,
        missing_count=missing_count,
        missing_since=missing_since,
        closed_at=closed_at,
        appearance_sequence=1,
        created_at=created_at,
        updated_at=updated_at,
    )


def _choose_location(random: Random) -> dict[str, str]:
    region_slug = _weighted_choice(
        random,
        tuple(
            (region_slug, REGION_WEIGHTS.get(region_slug, 1.0))
            for region_slug in REGION_FILTERS
        ),
    )
    region = REGION_FILTERS[region_slug]
    subregion_slug = _weighted_choice(
        random,
        tuple(
            (subregion_slug, _subregion_weight(region_slug, subregion_slug))
            for subregion_slug in region.subregions
        ),
    )
    subregion = region.subregions[subregion_slug]
    city = random.choice(CITY_BY_SUBREGION.get(subregion_slug, (subregion.label,)))

    return {
        "island": STATE_LABELS[region.state],
        "region": region.label,
        "subregion": subregion.label,
        "city": city,
    }


def _subregion_weight(region_slug: str, subregion_slug: str) -> float:
    if region_slug == "auckland":
        return AUCKLAND_SUBREGION_WEIGHTS[subregion_slug]
    if subregion_slug in {"christchurch", "wellington", "hamilton", "tauranga", "dunedin"}:
        return 3.0
    if subregion_slug in {"queenstown-lakes", "nelson", "marlborough", "whangarei"}:
        return 2.0
    return 1.0


def _choose_start_date(random: Random) -> date:
    max_weight = max(MONTH_WEIGHTS.values()) + 0.35
    day_count = (DATE_RANGE_END - DATE_RANGE_START).days + 1
    while True:
        candidate = DATE_RANGE_START + timedelta(days=random.randrange(day_count))
        if random.random() <= _date_weight(candidate) / max_weight:
            return candidate


def _date_weight(candidate: date) -> float:
    weight = MONTH_WEIGHTS[candidate.month]
    if candidate.month == 12 and candidate.day >= 20:
        weight += 0.35
    if candidate.month == 1 and candidate.day <= 10:
        weight += 0.25
    return weight


def _choose_duration_days(random: Random, start_date: date) -> int:
    if start_date.month in {12, 1}:
        buckets = (
            (range(1, 8), 1.2),
            (range(8, 15), 1.6),
            (range(15, 31), 2.2),
            (range(31, 61), 2.4),
            (range(61, 121), 1.3),
        )
    elif start_date.month in {6, 7}:
        buckets = (
            (range(1, 8), 2.6),
            (range(8, 15), 2.0),
            (range(15, 31), 1.5),
            (range(31, 61), 0.8),
            (range(61, 121), 0.3),
        )
    else:
        buckets = (
            (range(1, 8), 2.0),
            (range(8, 15), 2.0),
            (range(15, 31), 1.8),
            (range(31, 61), 1.2),
            (range(61, 121), 0.6),
        )

    selected_range = _weighted_choice(random, buckets)
    return random.choice(tuple(selected_range))


def _choose_lead_time_days(random: Random, duration_days: int) -> int:
    if random.random() < 0.08:
        return random.randint(0, 10)

    if duration_days <= 7:
        mean, spread = 20, 12
    elif duration_days <= 14:
        mean, spread = 30, 15
    elif duration_days <= 30:
        mean, spread = 45, 20
    elif duration_days <= 60:
        mean, spread = 75, 28
    else:
        mean, spread = 105, 35

    return min(240, max(0, round(random.gauss(mean, spread))))


def _choose_pet_counts(random: Random) -> dict[str, Any]:
    profile = _weighted_choice(
        random,
        (
            ("dogs", 3.6),
            ("cats", 2.8),
            ("dogs_and_cats", 1.9),
            ("mixed", 1.3),
            ("other", 0.7),
            ("no_pets", 0.4),
        ),
    )
    counts: dict[str, Any] = {
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

    if profile == "dogs":
        counts["dogs_count"] = random.randint(1, 2)
    elif profile == "cats":
        counts["cats_count"] = random.randint(1, 3)
    elif profile == "dogs_and_cats":
        counts["dogs_count"] = random.randint(1, 2)
        counts["cats_count"] = random.randint(1, 2)
    elif profile == "mixed":
        counts["dogs_count"] = random.randint(0, 2)
        counts["cats_count"] = random.randint(0, 2)
        extra_key = random.choice(
            (
                "fish_count",
                "birds_count",
                "rabbits_guinea_pigs_count",
                "chickens_ducks_geese_count",
            )
        )
        counts[extra_key] = random.randint(1, 4)
        if counts["dogs_count"] == 0 and counts["cats_count"] == 0:
            counts["cats_count"] = 1
    elif profile == "other":
        pet_key = random.choice(
            ("farm_animals_count", "horses_count", "reptiles_count", "other_pets_count")
        )
        counts[pet_key] = random.randint(1, 3)
    else:
        counts["no_pets"] = True

    return counts


def _listing_tag(city: str, pet_counts: dict[str, Any]) -> str:
    if pet_counts["no_pets"]:
        return f"Quiet home in {city}"
    if pet_counts["dogs_count"] and pet_counts["cats_count"]:
        return f"Dogs and cats in {city}"
    if pet_counts["dogs_count"]:
        return f"Dog sitting in {city}"
    if pet_counts["cats_count"]:
        return f"Cat sitting in {city}"
    return f"Pet sitting in {city}"


def _intro_text(duration_days: int, city: str) -> str:
    if duration_days >= 60:
        return f"Long sit in {city} with a comfortable home and established routine."
    if duration_days >= 31:
        return f"Extended sit in {city} for responsible house and pet care."
    return f"Short pet sitting opportunity in {city}."


def _choose_last_seen_at(random: Random, first_seen_at: datetime, end_date: date) -> datetime:
    latest_observation_date = min(end_date + timedelta(days=1), DEMO_REFERENCE_DATE)
    if latest_observation_date < first_seen_at.date():
        latest_observation_date = first_seen_at.date()
    span_days = max(0, (latest_observation_date - first_seen_at.date()).days)
    observed_date = first_seen_at.date() + timedelta(days=random.randint(0, span_days))
    return _with_random_time(random, observed_date)


def _choose_status(
    random: Random,
    end_date: date,
    last_seen_at: datetime,
) -> tuple[str, int, datetime | None, datetime | None]:
    if end_date < DEMO_REFERENCE_DATE:
        closed_at = datetime.combine(end_date + timedelta(days=1), time(hour=8))
        return "expired_by_date", 0, None, closed_at
    if random.random() < 0.04:
        missing_since = last_seen_at + timedelta(days=1)
        return "missing_once", 1, missing_since, None
    if random.random() < 0.03:
        missing_since = last_seen_at + timedelta(days=2)
        closed_at = missing_since + timedelta(days=1)
        return "missing_confirmed", 3, missing_since, closed_at
    return "active", 0, None, None


def _first_seen_context(first_seen_at: datetime) -> str:
    if first_seen_at.date() < DATE_RANGE_START + timedelta(days=45):
        return "baseline"
    return "observed"


def _with_random_time(random: Random, day: date) -> datetime:
    return datetime.combine(
        day,
        time(hour=random.randint(7, 21), minute=random.choice((0, 10, 20, 30, 40, 50))),
    )


def _weighted_choice[T](random: Random, weighted_items: tuple[tuple[T, float], ...]) -> T:
    total_weight = sum(weight for _, weight in weighted_items)
    threshold = random.random() * total_weight
    cumulative_weight = 0.0
    for item, weight in weighted_items:
        cumulative_weight += weight
        if threshold <= cumulative_weight:
            return item
    return weighted_items[-1][0]
