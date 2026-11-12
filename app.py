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
    # number of new leases behind each latest median, one column per home type
    latest = rent[rent["quarter"] == rent["quarter"].max()]
    counts = latest.pivot_table(index="rent_area", columns="dwelling_type", values="bond_count")
    counts.columns = ["n_" + c.lower().replace(" ", "_") for c in counts.columns]
    areas = areas.merge(counts, left_on="rent_area", right_index=True, how="left")
    crime = pd.read_csv(CLEAN / "crime_suburb.csv")
    lookup = pd.read_csv(CLEAN / "suburb_lookup.csv")
    return areas, rent, crime, lookup


areas, rent, crime, lookup = load_data()

CHEAPEST = "Cheapest available (any type)"
HOME_TYPES = {
    CHEAPEST: (None, None),
    "Typical home (all types combined)": ("rent_all_properties", "All properties"),
    "1 bedroom flat": ("rent_1_bedroom_flat", "1 bedroom flat"),
    "2 bedroom flat": ("rent_2_bedroom_flat", "2 bedroom flat"),
    "3 bedroom flat": ("rent_3_bedroom_flat", "3 bedroom flat"),
    "2 bedroom house": ("rent_2_bedroom_house", "2 bedroom house"),
    "3 bedroom house": ("rent_3_bedroom_house", "3 bedroom house"),
    "4 bedroom house": ("rent_4_bedroom_house", "4 bedroom house"),
}
MIN_LEASES = 30         # ignore home types with fewer new leases than this in "cheapest"
CENTRE_THRESHOLD = 200  # crime per 1,000 above this is usually a busy town/city centre
MELBOURNE_REGIONS = {
    "Inner Melbourne", "Inner Eastern Melbourne", "Southern Melbourne",
    "Outer Western Melbourne", "North Western Melbourne", "North Eastern Melbourne",
    "Outer Eastern Melbourne", "South Eastern Melbourne", "Mornington Peninsula",
}
# light grey basemap (no API key) so the coloured areas stand out
BASEMAP = ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
           "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}")
BASEMAP_ATTR = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, OpenStreetMap contributors"


# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Your search")
    budget = st.number_input("Weekly rent budget ($)", min_value=200, max_value=2000,
                             value=550, step=10)
    home_label = st.selectbox("Home type", list(HOME_TYPES))
    rent_col, rent_sheet = HOME_TYPES[home_label]

    include_regional = st.toggle("Include regional Victoria", value=False,
                                 help="Geelong, Ballarat, Bendigo and other regional centres")
    region_options = sorted(r for r in areas["region"].unique()
                            if include_regional or r in MELBOURNE_REGIONS)
    regions = st.multiselect("Regions (leave empty for all)", region_options)

    st.subheader("How important is…")
    st.caption("Set how much each factor counts towards the match score. "
               "*Not important* ignores it completely.")
    LEVELS = {"Not important": 0, "A little": 1, "Somewhat": 2, "Important": 3, "Very important": 4}
    w_afford = LEVELS[st.select_slider("💰 Low rent", list(LEVELS), value="Important")]
    w_safety = LEVELS[st.select_slider("🛡️ Low crime", list(LEVELS), value="Important")]
    w_stable = LEVELS[st.select_slider("📈 Stable rent", list(LEVELS), value="Somewhat",
                      help="Prefers areas where rent has risen less over the last 5 years")]
    top_n = st.slider("Results to show", 5, 30, 10)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
df = areas.copy()
TYPE_COLS = {sheet: col for col, sheet in HOME_TYPES.values() if sheet not in (None, "All properties")}
if home_label == CHEAPEST:
    # cheapest home type with a published median in each area
    type_rents = df[list(TYPE_COLS.values())].copy()
    for col in type_rents:   # drop medians based on too few leases to be reliable
        type_rents.loc[df[col.replace("rent_", "n_")] < MIN_LEASES, col] = None
    df["rent"] = type_rents.min(axis=1)
    df["rent_type"] = type_rents.fillna(1e9).idxmin(axis=1).map({c: s for s, c in TYPE_COLS.items()})
    df.loc[df["rent"].isna(), "rent_type"] = None
else:
    df["rent"] = df[rent_col]
    df["rent_type"] = rent_sheet

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

if not include_regional:
    df = df[df["region"].isin(MELBOURNE_REGIONS)]

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
    # zoom to the areas that fit the budget; panning is limited to Victoria
    minx, miny, maxx, maxy = matches.total_bounds
    m = folium.Map(tiles=BASEMAP, attr=BASEMAP_ATTR, min_zoom=7, max_zoom=15, zoom_snap=0.25,
                   max_bounds=True, min_lat=-39.3, max_lat=-33.9, min_lon=140.8, max_lon=150.1)
    m.fit_bounds([[miny, minx], [maxy, maxx]], padding=(15, 15))
    # smaller credits line, without the optional "Leaflet" link (tile credits must stay)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-control-attribution{font-size:9px!important;opacity:.8}</style>"))
    m.get_root().script.add_child(folium.Element(
        f"{m.get_name()}.attributionControl.setPrefix(false);"))
    cmap = cm.LinearColormap(["#fde0c5", "#facba6", "#74c476", "#006d2c"],
                             vmin=0, vmax=100, caption="Match score (higher = better fit)")

    shown = matches.head(top_n)["rent_area"].tolist()
    map_df = df[["rent_area", "rent", "rent_type", "crime_per_1000", "rent_change_5y_pct", "match",
                 "geometry"]].copy()
    map_df["in_budget"] = mask
    map_df["top"] = map_df["rent_area"].isin(shown)

    folium.GeoJson(
        map_df,
        style_function=lambda f: {
            "fillColor": cmap(f["properties"]["match"]) if f["properties"]["in_budget"] else "#9e9e9e",
            "color": "#111" if f["properties"]["top"] else "#555",
            "weight": 2.5 if f["properties"]["top"] else 0.7,
            "fillOpacity": 0.85 if f["properties"]["in_budget"] else 0.45,
        },
        highlight_function=lambda f: {"weight": 3, "color": "#000"},
        tooltip=folium.GeoJsonTooltip(
            fields=["rent_area", "rent", "rent_type", "crime_per_1000", "rent_change_5y_pct", "match"],
            aliases=["Area", "Median rent ($/wk)", "Home type", "Crime per 1,000",
                     "Rent change 5 yrs (%)", "Match score"],
            localize=True, sticky=True),
    ).add_to(m)
    st.markdown(
        "<div style='font-size:0.85rem;color:#555;margin-bottom:6px'>"
        "<b>Match score</b> &nbsp;0 <span style='display:inline-block;width:160px;height:10px;"
        "vertical-align:middle;border-radius:3px;background:linear-gradient(90deg,"
        "#fde0c5,#facba6,#74c476,#006d2c)'></span> 100 &nbsp;·&nbsp; "
        "<span style='display:inline-block;width:12px;height:10px;background:#9e9e9e;"
        "vertical-align:middle'></span> over budget &nbsp;·&nbsp; bold outline = top results"
        " &nbsp;·&nbsp; blank = no rent data</div>", unsafe_allow_html=True)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

with right:
    st.subheader(f"Top {min(top_n, len(matches))} matches")
    for i, r in enumerate(matches.head(top_n).itertuples(), 1):
        with st.container(border=True):
            n = getattr(r, "n_" + r.rent_type.lower().replace(" ", "_"))
            few = " ⚠️ few leases" if n < MIN_LEASES else ""
            crime_trend = r.crime_change_1y_pct
            arrow, colour = ("▼", "#2e7d32") if crime_trend < 0 else ("▲", "#c62828")
            st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start">
  <div><b>{i}. {r.rent_area}</b><br>
    <span style="color:gray;font-size:0.85rem">{r.region} · ${budget - r.rent:.0f} under budget</span></div>
  <div style="text-align:center;min-width:56px"><span style="font-size:0.75rem;color:gray">Match</span><br>
    <span style="font-size:1.6rem;font-weight:600">{r.match:.0f}</span></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:6px">
  <div><span style="font-size:0.75rem;color:gray">Rent /wk</span><br>
    <span style="font-size:1.25rem;font-weight:600">${r.rent:.0f}</span><br>
    <span style="font-size:0.75rem;color:gray">{r.rent_type} · {n:,.0f} leases{few}</span></div>
  <div><span style="font-size:0.75rem;color:gray">Crime /1k</span><br>
    <span style="font-size:1.25rem;font-weight:600">{r.crime_per_1000:.0f}</span><br>
    <span style="font-size:0.75rem;color:{colour}">{arrow} {abs(crime_trend):.0f}% in 1 yr</span></div>
  <div><span style="font-size:0.75rem;color:gray">Rent 5 yrs</span><br>
    <span style="font-size:1.25rem;font-weight:600">{r.rent_change_5y_pct:+.0f}%</span></div>
</div>""", unsafe_allow_html=True)
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
    pick_type = row["rent_type"]
    st.markdown(f"**Median weekly rent: {pick_type.lower()}**")
    hist = rent[(rent["rent_area"] == pick) & (rent["dwelling_type"] == pick_type)]
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
        "1. **Filter**: keep areas whose median rent for your home type is within budget. "
        "With *Cheapest available*, each area uses its cheapest home type, ignoring types "
        f"with fewer than {MIN_LEASES} new leases in the past year (too few to be reliable).\n"
        "2. **Score**: each area gets a 0–100 score for affordability (cheaper rent), safety "
        "(fewer incidents per 1,000 residents) and rent stability (smaller 5-year rise), "
        "based on its rank among all 146 areas.\n"
        "3. **Weight**: scores are combined using the importance you set for each factor.\n\n"
        "**Limitations:** rent figures are area medians, not individual listings. Crime rates "
        "use 2021 population. Some areas group several suburbs, and suburbs not listed in "
        "the rent report aren't included."
    )