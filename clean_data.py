"""
Melbourne Suburb Finder - Step 2: clean and merge
-------------------------------------------------
Inputs  (in data/):  rent.xlsx  (Homes Victoria moving annual rents by suburb)
                     crime.xlsx (CSA criminal incidents by LGA, Table 03 = suburb level)
Outputs (in data/clean/):
    rent_long.csv       one row per rent area x dwelling type x quarter
    crime_suburb.csv    one row per suburb x year x offence division
    suburb_lookup.csv   which crime suburbs belong to which rent area
    area_summary.csv    one row per rent area - the table the app will use

    pip install pandas openpyxl
    python clean_data.py
"""

import re
from pathlib import Path

import pandas as pd

DATA = Path("data")
OUT = DATA / "clean"
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. RENT  - wide, multi-header sheets  ->  tidy long table
# ---------------------------------------------------------------------------
def load_rent() -> pd.DataFrame:
    frames = []
    for sheet in pd.ExcelFile(DATA / "rent.xlsx").sheet_names:
        raw = pd.read_excel(DATA / "rent.xlsx", sheet_name=sheet, header=None)

        quarters = raw.iloc[1, 2:].ffill()          # "Mar 2000", "Mar 2000", ...
        measures = raw.iloc[2, 2:]                  # "Count", "Median", ...
        body = raw.iloc[3:].copy()
        body[0] = body[0].ffill()                   # region only on first row of group
        body = body[body[1].notna() & (body[1] != "Group Total")]

        long = body.melt(id_vars=[0, 1], value_vars=list(range(2, raw.shape[1])),
                         var_name="col", value_name="value")
        long["quarter"] = long["col"].map(quarters)
        long["measure"] = long["col"].map(measures).str.lower()
        long = long.pivot_table(index=[0, 1, "quarter"], columns="measure",
                                values="value", aggfunc="first").reset_index()
        long.columns = ["region", "rent_area", "quarter", "bond_count", "median_rent"]
        long["dwelling_type"] = sheet
        frames.append(long)

    rent = pd.concat(frames, ignore_index=True)
    # "-" marks too few bonds to publish -> missing
    for col in ["bond_count", "median_rent"]:
        rent[col] = pd.to_numeric(rent[col], errors="coerce")
    rent["quarter"] = pd.to_datetime(rent["quarter"], format="%b %Y") + pd.offsets.MonthEnd(0)
    rent["rent_area"] = rent["rent_area"].str.strip()
    return rent.sort_values(["dwelling_type", "rent_area", "quarter"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. CRIME - Table 03: incidents by suburb x offence subgroup x year
# ---------------------------------------------------------------------------
def load_crime() -> pd.DataFrame:
    raw = pd.read_excel(DATA / "crime.xlsx", sheet_name="Table 03")
    raw.columns = ["year", "year_ending", "lga", "postcode", "suburb",
                   "offence_division", "offence_subdivision", "offence_subgroup", "incidents"]
    raw["suburb"] = raw["suburb"].str.strip()
    # collapse subgroups to division level (A person, B property, C drugs, ...)
    crime = (raw.groupby(["year", "lga", "postcode", "suburb", "offence_division"],
                         as_index=False)["incidents"].sum())
    return crime


# ---------------------------------------------------------------------------
# 3. LOOKUP - rent areas are groups like "Carlton-Parkville"; crime is per suburb
# ---------------------------------------------------------------------------
# rent-name part -> crime suburb name(s), for the few that don't match directly
MANUAL = {
    "west st kilda": ["St Kilda West"],
    "east st kilda": ["St Kilda East"],
    "east hawthorn": ["Hawthorn East"],
    "east brunswick": ["Brunswick East"],
    "west brunswick": ["Brunswick West"],
    "cbd": ["Melbourne"],
    "st kilda rd": [],                       # also postcode 3004 "Melbourne", counted via CBD
    "newcombe": ["Newcomb"],
    "bendigo east": ["East Bendigo"],
    "wanagaratta": ["Wangaratta"],           # typo in the rent file
    "ballarat": ["Ballarat Central", "Ballarat East", "Ballarat North"],
}


def build_lookup(rent: pd.DataFrame, crime: pd.DataFrame) -> pd.DataFrame:
    crime_subs = crime[["lga", "suburb"]].drop_duplicates()
    by_lower = {s.lower(): s for s in crime_subs["suburb"]}
    rows = []

    for area in rent["rent_area"].unique():
        if area == "Yarra Ranges":
            # rent area covers the whole LGA except Lilydale (in Croydon-Lilydale)
            for s in crime_subs.loc[crime_subs["lga"] == "Yarra Ranges", "suburb"]:
                if s != "Lilydale":
                    rows.append((area, s))
            continue
        for part in area.split("-"):
            key = re.sub(r"^mt ", "mount ", part.strip().lower())
            matches = MANUAL.get(key, [by_lower[key]] if key in by_lower else None)
            if matches is None:
                print(f"  ! no crime suburb found for '{part}' in '{area}'")
                continue
            rows += [(area, m) for m in matches]

    return pd.DataFrame(rows, columns=["rent_area", "suburb"]).drop_duplicates()


# ---------------------------------------------------------------------------
# 4. SUMMARY - one row per rent area
# ---------------------------------------------------------------------------
def build_summary(rent, crime, lookup) -> pd.DataFrame:
    latest_q = rent["quarter"].max()
    q_1y = latest_q - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
    q_5y = latest_q - pd.DateOffset(years=5) + pd.offsets.MonthEnd(0)

    # rent: latest median per dwelling type, as columns
    wide = rent[rent["quarter"] == latest_q].pivot_table(
        index=["region", "rent_area"], columns="dwelling_type", values="median_rent")
    wide.columns = ["rent_" + c.lower().replace(" ", "_") for c in wide.columns]
    summary = wide.reset_index()

    allp = rent[rent["dwelling_type"] == "All properties"].set_index(["rent_area", "quarter"])["median_rent"]
    for label, q in [("1y", q_1y), ("5y", q_5y)]:
        past = allp.xs(q, level="quarter")
        now = allp.xs(latest_q, level="quarter")
        summary[f"rent_change_{label}_pct"] = summary["rent_area"].map((now / past - 1) * 100).round(1)

    # crime: aggregate suburbs into rent areas
    c = crime.merge(lookup, on="suburb", how="inner")
    yr = c["year"].max()
    tot = c.groupby(["rent_area", "year"])["incidents"].sum().unstack()
    summary["crime_incidents"] = summary["rent_area"].map(tot[yr])
    summary["crime_change_1y_pct"] = summary["rent_area"].map((tot[yr] / tot[yr - 1] - 1) * 100).round(1)
    summary["crime_change_5y_pct"] = summary["rent_area"].map((tot[yr] / tot[yr - 5] - 1) * 100).round(1)

    div = (c[c["year"] == yr].groupby(["rent_area", "offence_division"])["incidents"]
           .sum().unstack(fill_value=0))
    summary["crime_person_pct"] = summary["rent_area"].map(
        div.filter(like="A ").sum(axis=1) / div.sum(axis=1) * 100).round(1)
    summary["crime_property_pct"] = summary["rent_area"].map(
        div.filter(like="B ").sum(axis=1) / div.sum(axis=1) * 100).round(1)

    summary["n_suburbs_matched"] = summary["rent_area"].map(lookup.groupby("rent_area").size())
    summary.attrs["latest"] = (latest_q.strftime("%b %Y"), yr)
    return summary.sort_values(["region", "rent_area"])


# ---------------------------------------------------------------------------
def main():
    print("Loading rent ..."); rent = load_rent()
    print("Loading crime (big sheet, ~30s) ..."); crime = load_crime()
    print("Matching suburbs ..."); lookup = build_lookup(rent, crime)
    summary = build_summary(rent, crime, lookup)

    rent.to_csv(OUT / "rent_long.csv", index=False)
    crime.to_csv(OUT / "crime_suburb.csv", index=False)
    lookup.to_csv(OUT / "suburb_lookup.csv", index=False)
    summary.to_csv(OUT / "area_summary.csv", index=False)

    q, yr = summary.attrs["latest"]
    print(f"\nrent_long:     {len(rent):,} rows  ({rent['rent_area'].nunique()} areas, "
          f"{rent['quarter'].min():%b %Y} - {rent['quarter'].max():%b %Y})")
    print(f"crime_suburb:  {len(crime):,} rows  ({crime['suburb'].nunique()} suburbs, "
          f"{crime['year'].min()}-{crime['year'].max()})")
    print(f"suburb_lookup: {len(lookup)} suburbs mapped to {lookup['rent_area'].nunique()} rent areas")
    print(f"area_summary:  {len(summary)} areas  (rent {q}, crime year ending June {yr})")
    print(f"\nSaved to {OUT}/")


if __name__ == "__main__":
    main()
