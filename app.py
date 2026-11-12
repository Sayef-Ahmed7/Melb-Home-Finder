"""
Melbourne Suburb Finder - Streamlit app
---------------------------------------
    pip install -r requirements.txt
    streamlit run app.py
"""

from pathlib import Path

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

CLEAN = Path("data/clean")

st.set_page_config(page_title="Melbourne Suburb Finder", page_icon="🏠", layout="wide")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Preparing data (first run only, ~30s) ...")
def load_data():
    # data/clean/ isn't in git, so build it on first run (e.g. on Streamlit Cloud)
    if not (CLEAN / "rent_areas.geojson").exists():
        import clean_data, prepare_boundaries
        clean_data.main()
        prepare_boundaries.main()
    areas = gpd.read_file(CLEAN / "rent_areas.geojson")
    rent = pd.read_csv(CLEAN / "rent_long.csv", parse_dates=["quarter"])
    crime = pd.read_csv(CLEAN / "crime_suburb.csv")
    lookup = pd.read_csv(CLEAN / "suburb_lookup.csv")
    return areas, rent, crime, lookup


areas, rent, crime, lookup = load_data()

HOME_TYPES = {
    "Any (all properties)": ("rent_all_properties", "All properties"),
    "1 bedroom flat": ("rent_1_bedroom_flat", "1 bedroom flat"),
    "2 bedroom flat": ("rent_2_bedroom_flat", "2 bedroom flat"),
    "3 bedroom flat": ("rent_3_bedroom_flat", "3 bedroom flat"),
    "2 bedroom house": ("rent_2_bedroom_house", "2 bedroom house"),
    "3 bedroom house": ("rent_3_bedroom_house", "3 bedroom house"),
    "4 bedroom house": ("rent_4_bedroom_house", "4 bedroom house"),
}
CENTRE_THRESHOLD = 200  # crime per 1,000 above this is usually a busy town/city centre


# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Your search")
    budget = st.number_input("Weekly rent budget ($)", min_value=200, max_value=2000,
                             value=550, step=10)
    home_label = st.selectbox("Home type", list(HOME_TYPES))
    rent_col, rent_sheet = HOME_TYPES[home_label]

    regions = st.multiselect("Regions (leave empty for all)", sorted(areas["region"].unique()))

    st.subheader("What matters most?")
    w_afford = st.slider("Affordability", 0, 10, 5)
    w_safety = st.slider("Safety", 0, 10, 5)
    w_stable = st.slider("Rent stability", 0, 10, 3,
                         help="Prefers areas where rent has risen less over 5 years")
    top_n = st.slider("Results to show", 5, 30, 10)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
df = areas.copy()
df["rent"] = df[rent_col]

# percentile scores across ALL areas (0-100, higher = better), robust to outliers
df["score_afford"] = (1 - df["rent"].rank(pct=True)) * 100
df["score_safety"] = (1 - df["crime_per_1000"].rank(pct=True)) * 100
df["score_stable"] = (1 - df["rent_change_5y_pct"].rank(pct=True)) * 100

total_w = w_afford + w_safety + w_stable
if total_w == 0:
    st.warning("Move at least one slider above 0.")
    st.stop()
df["match"] = ((w_afford * df["score_afford"] + w_safety * df["score_safety"]
                + w_stable * df["score_stable"]) / total_w).round(0)

mask = df["rent"].notna() & (df["rent"] <= budget)
if regions:
    mask &= df["region"].isin(regions)
matches = df[mask].sort_values("match", ascending=False)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🏠 Melbourne Suburb Finder")
st.caption("Find Victorian suburbs that fit your budget, ranked by affordability, safety "
           "and rent stability. Rent: Homes Victoria (Jun 2026) · Crime: Crime Statistics "
           "Agency (year to Jun 2026) · Population: ABS Census 2021")

c1, c2, c3 = st.columns(3)
c1.metric("Areas within budget", f"{len(matches)} of {df['rent'].notna().sum()}")
if len(matches):
    c2.metric("Cheapest match", f"${matches['rent'].min():.0f}/wk")
    c3.metric("Best match score", f"{matches.iloc[0]['match']:.0f} / 100")

if matches.empty:
    cheapest = df.loc[df["rent"].idxmin()] if df["rent"].notna().any() else None
    msg = f"No areas have a median {home_label.lower()} rent under ${budget}."
    if cheapest is not None:
        msg += f" The cheapest is {cheapest['rent_area']} at ${cheapest['rent']:.0f}/wk."
    st.info(msg)
    st.stop()


# ---------------------------------------------------------------------------
# Map + ranked list
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2], gap="large")

with left:
    centre = matches.geometry.union_all().centroid
    m = folium.Map(location=[centre.y, centre.x], zoom_start=10, tiles="OpenStreetMap")
    cmap = cm.LinearColormap(["#fee8c8", "#fdbb84", "#31a354", "#006d2c"],
                             vmin=0, vmax=100, caption="Match score")

    shown = matches.head(top_n)["rent_area"].tolist()
    map_df = df[["rent_area", "rent", "crime_per_1000", "rent_change_5y_pct", "match",
                 "geometry"]].copy()
    map_df["in_budget"] = mask
    map_df["top"] = map_df["rent_area"].isin(shown)

    folium.GeoJson(
        map_df,
        style_function=lambda f: {
            "fillColor": cmap(f["properties"]["match"]) if f["properties"]["in_budget"] else "#d9d9d9",
            "color": "#222" if f["properties"]["top"] else "white",
            "weight": 2 if f["properties"]["top"] else 0.6,
            "fillOpacity": 0.8 if f["properties"]["in_budget"] else 0.35,
        },
        highlight_function=lambda f: {"weight": 3, "color": "#000"},
        tooltip=folium.GeoJsonTooltip(
            fields=["rent_area", "rent", "crime_per_1000", "rent_change_5y_pct", "match"],
            aliases=["Area", "Median rent ($/wk)", "Crime per 1,000",
                     "Rent change 5 yrs (%)", "Match score"],
            localize=True, sticky=True),
    ).add_to(m)
    cmap.add_to(m)
    st.caption("Grey = over budget · outlined = in your top results · hover for details")
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

with right:
    st.subheader(f"Top {min(top_n, len(matches))} matches")
    for i, r in enumerate(matches.head(top_n).itertuples(), 1):
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**{i}. {r.rent_area}**  \n<span style='color:gray'>{r.region} · "
                       f"${budget - r.rent:.0f} under budget</span>", unsafe_allow_html=True)
            b.metric("Match", f"{r.match:.0f}")
            x, y, z = st.columns(3)
            x.metric("Rent /wk", f"${r.rent:.0f}")
            y.metric("Crime /1k", f"{r.crime_per_1000:.0f}",
                     f"{r.crime_change_1y_pct:+.0f}% 1yr", delta_color="inverse")
            z.metric("Rent 5yr", f"{r.rent_change_5y_pct:+.0f}%")
            if r.crime_per_1000 > CENTRE_THRESHOLD:
                st.caption("⚠️ Busy town/city centre: visitors inflate the per-resident crime rate.")


# ---------------------------------------------------------------------------
# Area details
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Area details")
pick = st.selectbox("Choose an area", matches["rent_area"].tolist())
row = df[df["rent_area"] == pick].iloc[0]
suburbs = lookup.loc[lookup["rent_area"] == pick, "suburb"].tolist()
st.caption(f"Includes: {', '.join(suburbs)} · Population {row['population_2021']:,.0f} (2021)")

d1, d2 = st.columns(2)
with d1:
    st.markdown(f"**Median weekly rent: {rent_sheet.lower()}**")
    hist = rent[(rent["rent_area"] == pick) & (rent["dwelling_type"] == rent_sheet)]
    st.line_chart(hist.set_index("quarter")["median_rent"], height=280, y_label="$ per week")
with d2:
    st.markdown("**Crime incidents per year (to June)**")
    c = crime[crime["suburb"].isin(suburbs)].copy()
    c["type"] = c["offence_division"].str[0].map(
        {"A": "Against the person", "B": "Property"}).fillna("Other")
    yearly = c.pivot_table(index="year", columns="type", values="incidents", aggfunc="sum")
    st.bar_chart(yearly, height=280, y_label="Incidents")

with st.expander("How the match score works"):
    st.markdown(
        "1. **Filter**: keep areas whose median rent for your home type is within budget.\n"
        "2. **Score**: each area gets a 0–100 score for affordability (cheaper rent), safety "
        "(fewer incidents per 1,000 residents) and rent stability (smaller 5-year rise), "
        "based on its rank among all 146 areas.\n"
        "3. **Weight**: scores are combined using your sliders.\n\n"
        "**Limitations:** rent figures are area medians, not individual listings. Crime rates "
        "use 2021 population. Some areas group several suburbs, and suburbs not listed in "
        "the rent report aren't included."
    )
