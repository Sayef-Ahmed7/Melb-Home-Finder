# Melbourne Suburb Finder

Find Victorian suburbs that fit your budget, ranked by rent and safety.

> 🚧 Work in progress

## Data sources
| Data | Source | Licence |
|---|---|---|
| Median weekly rent by suburb (2000–2026) | Homes Victoria Rental Report – Moving Annual Rents by Suburb | CC BY 4.0 |
| Criminal incidents by suburb (2017–2026) | Crime Statistics Agency Victoria – Criminal Incidents by LGA | CC BY 4.0 |
| Suburb boundaries (2021) | ABS ASGS Edition 3 – Suburbs and Localities, GDA2020 | CC BY 4.0 |
| Population by suburb (2021) | ABS Census 2021 General Community Profile, Suburbs and Localities (G01) | CC BY 4.0 |

Raw files are in `data/`. Crime data © Crime Statistics Agency (CSA).

## Notes
- Crime rates use 2021 Census population (latest suburb-level count), so recent growth areas may show slightly inflated rates.
- The rent report only lists ~280 suburbs, so unlisted suburbs show as gaps on the map.
- Some rent areas group several suburbs (e.g. Carlton-Parkville); their crime and population are summed across those suburbs.

## Setup
```bash
pip install -r requirements.txt
python clean_data.py          # tidy CSVs in data/clean/
python prepare_boundaries.py  # map shapes (needs the ABS zip only the first time)
python make_map.py            # interactive map -> maps/suburb_map.html
streamlit run app.py          # the web app
```
`data/boundaries/vic_suburbs.geojson` is included, so the ABS zip is only needed to rebuild it.

`clean_data.py` creates these in `data/clean/`:
- `area_summary.csv` – one row per rent area: rent, rent growth, crime rate per 1,000 residents, crime trend
- `rent_long.csv` – rent history by area, dwelling type and quarter
- `crime_suburb.csv` – incidents by suburb, year and offence type
- `suburb_lookup.csv` – which suburbs belong to each rent area

## Roadmap
- [x] Collect rent and crime data
- [x] Clean and merge
- [x] Add population for crime rates per 1,000 residents
- [x] Interactive map of rent and crime
- [ ] Exploratory analysis
- [ ] Rent forecast + suburb clustering
- [x] Streamlit app (budget, home type, region, priority sliders, map, area details)
- [ ] Deploy to Streamlit Community Cloud
