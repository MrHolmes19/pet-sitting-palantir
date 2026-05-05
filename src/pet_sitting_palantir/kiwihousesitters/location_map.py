"""KiwiHouseSitters state, region, and subregion filter IDs."""

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class SubregionFilter:
    """One KiwiHouseSitters subregion filter option."""

    label: str
    site_id: str


@dataclass(frozen=True)
class RegionFilter:
    """One KiwiHouseSitters region filter option."""

    label: str
    site_id: str
    state: str
    subregions: MappingProxyType[str, SubregionFilter]


STATE_LABELS = MappingProxyType(
    {
        "north-island": "North Island",
        "south-island": "South Island",
    }
)

REGION_FILTERS = MappingProxyType(
    {
        "auckland": RegionFilter(
            label="Auckland",
            site_id="33",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "auckland-central": SubregionFilter("Auckland - Central", "178"),
                    "auckland-north": SubregionFilter("Auckland - North", "186"),
                    "auckland-south": SubregionFilter("Auckland - South", "222"),
                    "manukau": SubregionFilter("Manukau", "204"),
                    "north-shore-city": SubregionFilter("North Shore City", "181"),
                    "rodney": SubregionFilter("Rodney", "180"),
                    "waiheke-island": SubregionFilter("Waiheke Island", "203"),
                    "waitakere": SubregionFilter("Waitakere", "179"),
                }
            ),
        ),
        "bay-of-plenty": RegionFilter(
            label="Bay of Plenty",
            site_id="34",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "opotiki": SubregionFilter("Opotiki", "247"),
                    "rotorua": SubregionFilter("Rotorua", "231"),
                    "tauranga": SubregionFilter("Tauranga", "243"),
                    "western-bay-of-plenty": SubregionFilter("Western Bay of Plenty", "245"),
                    "whakatane": SubregionFilter("Whakatane", "234"),
                }
            ),
        ),
        "gisborne": RegionFilter(
            label="Gisborne",
            site_id="36",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "gisborne": SubregionFilter("Gisborne", "352"),
                    "te-karaka": SubregionFilter("Te Karaka", "355"),
                }
            ),
        ),
        "hawkes-bay": RegionFilter(
            label="Hawke's Bay",
            site_id="37",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "central-hawkes-bay": SubregionFilter("Central Hawke's Bay", "383"),
                    "hastings": SubregionFilter("Hastings", "368"),
                    "napier": SubregionFilter("Napier", "369"),
                }
            ),
        ),
        "manawatu-whanganui": RegionFilter(
            label="Manawatū-Whanganui",
            site_id="38",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "horowhenua": SubregionFilter("Horowhenua", "438"),
                    "palmerston-north": SubregionFilter("Palmerston North", "416"),
                    "rangitikei": SubregionFilter("Rangitikei", "431"),
                    "ruapehu": SubregionFilter("Ruapehu", "421"),
                    "tararua": SubregionFilter("Tararua", "417"),
                    "whanganui": SubregionFilter("Whanganui", "412"),
                }
            ),
        ),
        "northland": RegionFilter(
            label="Northland",
            site_id="32",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "far-north": SubregionFilter("Far North", "138"),
                    "kaipara": SubregionFilter("Kaipara", "146"),
                    "whangarei": SubregionFilter("Whangarei", "128"),
                }
            ),
        ),
        "taranaki": RegionFilter(
            label="Taranaki",
            site_id="51",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "central-taranaki": SubregionFilter("Central Taranaki", "396"),
                    "new-plymouth": SubregionFilter("New Plymouth", "393"),
                    "south-taranaki": SubregionFilter("South Taranaki", "395"),
                }
            ),
        ),
        "waikato": RegionFilter(
            label="Waikato",
            site_id="35",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "hamilton": SubregionFilter("Hamilton", "264"),
                    "hauraki": SubregionFilter("Hauraki", "298"),
                    "matamata-piako": SubregionFilter("Matamata-Piako", "276"),
                    "north-waikato": SubregionFilter("North Waikato", "320"),
                    "south-waikato": SubregionFilter("South Waikato", "286"),
                    "taupo": SubregionFilter("Taupo", "277"),
                    "thames-coromandel": SubregionFilter("Thames-Coromandel", "297"),
                    "waipa": SubregionFilter("Waipa", "267"),
                }
            ),
        ),
        "wairarapa": RegionFilter(
            label="Wairarapa",
            site_id="510",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "masterton": SubregionFilter("Masterton", "407"),
                    "south-wairarapa": SubregionFilter("South Wairarapa", "477"),
                }
            ),
        ),
        "wellington": RegionFilter(
            label="Wellington",
            site_id="39",
            state="north-island",
            subregions=MappingProxyType(
                {
                    "kapiti-coast": SubregionFilter("Kapiti Coast", "466"),
                    "lower-hutt": SubregionFilter("Lower Hutt", "462"),
                    "porirua": SubregionFilter("Porirua", "465"),
                    "upper-hutt": SubregionFilter("Upper Hutt", "463"),
                    "wellington": SubregionFilter("Wellington", "409"),
                }
            ),
        ),
        "canterbury": RegionFilter(
            label="Canterbury",
            site_id="41",
            state="south-island",
            subregions=MappingProxyType(
                {
                    "ashburton": SubregionFilter("Ashburton", "570"),
                    "banks-peninsula": SubregionFilter("Banks Peninsula", "569"),
                    "christchurch": SubregionFilter("Christchurch", "544"),
                    "hurunui": SubregionFilter("Hurunui", "524"),
                    "mackenzie": SubregionFilter("Mackenzie", "611"),
                    "selwyn": SubregionFilter("Selwyn", "543"),
                    "timaru": SubregionFilter("Timaru", "612"),
                    "waimakariri": SubregionFilter("Waimakariri", "532"),
                }
            ),
        ),
        "nelson-marlborough": RegionFilter(
            label="Nelson / Marlborough",
            site_id="40",
            state="south-island",
            subregions=MappingProxyType(
                {
                    "marlborough": SubregionFilter("Marlborough", "506"),
                    "nelson": SubregionFilter("Nelson", "491"),
                    "tasman": SubregionFilter("Tasman", "489"),
                }
            ),
        ),
        "otago": RegionFilter(
            label="Otago",
            site_id="42",
            state="south-island",
            subregions=MappingProxyType(
                {
                    "central-otago": SubregionFilter("Central Otago", "656"),
                    "clutha": SubregionFilter("Clutha", "648"),
                    "dunedin": SubregionFilter("Dunedin", "637"),
                    "queenstown-lakes": SubregionFilter("Queenstown Lakes", "655"),
                    "waitaki": SubregionFilter("Waitaki", "675"),
                }
            ),
        ),
        "southland": RegionFilter(
            label="Southland",
            site_id="53",
            state="south-island",
            subregions=MappingProxyType(
                {
                    "invercargill": SubregionFilter("Invercargill", "721"),
                    "southland": SubregionFilter("Southland", "677"),
                }
            ),
        ),
        "west-coast": RegionFilter(
            label="West Coast",
            site_id="52",
            state="south-island",
            subregions=MappingProxyType(
                {
                    "buller": SubregionFilter("Buller", "1189"),
                    "grey": SubregionFilter("Grey", "1190"),
                    "westland": SubregionFilter("Westland", "1191"),
                }
            ),
        ),
    }
)
