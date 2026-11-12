"""
Melbourne Suburb Finder - test map
----------------------------------
Builds an interactive map of rent areas, switchable between median rent
and crime rate, and saves it to maps/suburb_map.html (open in a browser).

    pip install folium
    python make_map.py
"""

from pathlib import Path

import branca.colormap as cm
import folium
import geopandas as gpd

areas = gpd.read_file("data/clean/rent_areas.geojson")
Path("maps").mkdir(exist_ok=True)

LAYERS = {
    # column: (label, colours low -> high, number format)
    "rent_all_properties": ("Median weekly rent ($)", ["#f7fbff", "#6baed6", "#08306b"], "${:,.0f}"),
    "crime_per_1000": ("Crime per 1,000 residents", ["#fff5eb", "#fd8d3c", "#7f2704"], "{:,.0f}"),
}

m = folium.Map(location=[-37.81, 144.96], zoom_start=10, tiles="OpenStreetMap")

for i, (col, (label, colours, fmt)) in enumerate(LAYERS.items()):
    # quantile steps, so a few extreme areas (e.g. city centres) don't wash out the rest
    bins = areas[col].quantile([0, .2, .4, .6, .8, 1]).round().tolist()
    cmap = cm.LinearColormap(colours, vmin=bins[0], vmax=bins[-1]).to_step(index=bins)
    cmap.caption = label

    layer = folium.FeatureGroup(name=label, overlay=False, show=(i == 0))
    folium.GeoJson(
        areas,
        style_function=lambda f, c=col, cmap=cmap: {
            "fillColor": cmap(f["properties"][c]) if f["properties"][c] is not None else "#ccc",
            "color": "white", "weight": 0.8, "fillOpacity": 0.75,
        },
        highlight_function=lambda f: {"weight": 2.5, "color": "#333"},
        tooltip=folium.GeoJsonTooltip(
            fields=["rent_area", "rent_all_properties", "rent_change_5y_pct",
                    "crime_per_1000", "crime_change_1y_pct", "population_2021"],
            aliases=["Area", "Median rent ($/wk)", "Rent change, 5 yrs (%)",
                     "Crime per 1,000", "Crime change, 1 yr (%)", "Population (2021)"],
            localize=True, sticky=True,
        ),
    ).add_to(layer)
    layer.add_to(m)
    cmap.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
m.save("maps/suburb_map.html")
print("Saved maps/suburb_map.html - open it in your browser")
