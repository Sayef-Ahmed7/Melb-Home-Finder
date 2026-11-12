"""
Melbourne Suburb Finder - Step 3: map boundaries
------------------------------------------------
Input:  data/boundaries/SAL_2021_AUST_GDA2020_SHP.zip   (ABS, ~100 MB, all of Australia)
        data/clean/suburb_lookup.csv                    (from clean_data.py - run that first)
Output: data/boundaries/vic_suburbs.geojson   Victorian suburbs only, simplified (small, committed)
        data/clean/rent_areas.geojson         suburbs merged into rent areas, with area_summary columns

    pip install geopandas
    python clean_data.py
    python prepare_boundaries.py
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

DATA = Path("data")
RAW_ZIP = DATA / "boundaries" / "SAL_2021_AUST_GDA2020_SHP.zip"
VIC_SUBURBS = DATA / "boundaries" / "vic_suburbs.geojson"
CLEAN = DATA / "clean"

SIMPLIFY_METRES = 30   # outline detail; bigger = smaller file, blockier shapes


def build_vic_suburbs() -> gpd.GeoDataFrame:
    """Cut the Australia-wide file down to simplified Victorian suburbs."""
    print(f"Reading {RAW_ZIP.name} (all of Australia) ...")
    aus = gpd.read_file(f"zip://{RAW_ZIP}")
    vic = aus[aus["STE_CODE21"] == "2"].copy()

    # same name cleaning as clean_data.py: "Richmond (Vic.)" -> "Richmond"
    vic["suburb"] = vic["SAL_NAME21"].str.replace(r"\s*\(.*\)$", "", regex=True).str.strip()
    vic = vic[vic["SAL_NAME21"] != "Newtown (Golden Plains - Vic.)"]
    vic = vic[vic.geometry.notna()]

    # simplify in metres (GDA2020 / MGA zone 55), then back to lat/lon for web maps
    vic = vic.to_crs(7855)
    vic["geometry"] = vic.geometry.simplify(SIMPLIFY_METRES, preserve_topology=True)
    vic = vic.to_crs(4326)

    vic = vic[["SAL_CODE21", "suburb", "AREASQKM21", "geometry"]]
    vic.to_file(VIC_SUBURBS, driver="GeoJSON", COORDINATE_PRECISION=5)
    return vic


def build_rent_areas(vic: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Merge suburb shapes into rent areas and attach the summary table."""
    lookup = pd.read_csv(CLEAN / "suburb_lookup.csv")
    summary = pd.read_csv(CLEAN / "area_summary.csv")

    shapes = vic.merge(lookup, on="suburb", how="inner")
    missing = set(lookup["suburb"]) - set(shapes["suburb"])
    if missing:
        print("  ! no boundary for:", sorted(missing))

    areas = shapes.dissolve(by="rent_area", as_index=False)[["rent_area", "geometry"]]
    areas = areas.merge(summary, on="rent_area", how="left")
    areas.to_file(CLEAN / "rent_areas.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    return areas


def main():
    if VIC_SUBURBS.exists():
        print(f"Using existing {VIC_SUBURBS}")
        vic = gpd.read_file(VIC_SUBURBS)
    else:
        vic = build_vic_suburbs()
    print(f"vic_suburbs:  {len(vic):,} suburbs  ({VIC_SUBURBS.stat().st_size / 1e6:.1f} MB)")

    areas = build_rent_areas(vic)
    print(f"rent_areas:   {len(areas)} rent areas with shapes -> {CLEAN / 'rent_areas.geojson'}")


if __name__ == "__main__":
    main()
