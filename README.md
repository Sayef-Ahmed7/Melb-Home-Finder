# Melbourne Suburb Finder

Find Victorian suburbs that fit your budget, ranked by rent and safety.

> 🚧 Work in progress

## Data sources
| Data | Source | Licence |
|---|---|---|
| Median weekly rent by suburb (2000–2026) | Homes Victoria Rental Report – Moving Annual Rents by Suburb | CC BY 4.0 |
| Criminal incidents by suburb (2017–2026) | Crime Statistics Agency Victoria – Criminal Incidents by LGA | CC BY 4.0 |

Raw files are in `data/`. Crime data © Crime Statistics Agency (CSA).

## Setup
```bash
pip install -r requirements.txt
python clean_data.py
```
This creates tidy CSVs in `data/clean/`:
- `area_summary.csv` – one row per rent area: rent, rent growth, crime, crime trend
- `rent_long.csv` – rent history by area, dwelling type and quarter
- `crime_suburb.csv` – incidents by suburb, year and offence type
- `suburb_lookup.csv` – which suburbs belong to each rent area

## Roadmap
- [x] Collect rent and crime data
- [x] Clean and merge
- [ ] Add population for crime rates per 1,000 residents
- [ ] Exploratory analysis and maps
- [ ] Rent forecast + suburb clustering
- [ ] Streamlit app
