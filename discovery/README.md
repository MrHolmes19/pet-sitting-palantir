# Discovery Tools

This directory contains one-off operator scripts for inspecting KiwiHouseSitters
site behavior. These scripts are not part of the scheduled scraper path.

## Location Filters

Regenerate the state, region, and subregion ID map:

```bash
uv --cache-dir .uv-cache run python discovery/discover_kiwihousesitters_locations.py
```

The script follows the site's progressive filter UI:

1. GET the base search page and extract state options.
2. POST each state and extract region IDs.
3. POST each state/region pair and extract subregion IDs.
4. Write the markdown map to `src/pet_sitting_palantir/kiwihousesitters/LOCATION_MAP.md`.

City/postcode autocomplete is intentionally not cataloged. v1 scopes use state,
region, and subregion filters only.
