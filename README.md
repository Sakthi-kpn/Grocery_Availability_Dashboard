# Grocery Availability Dashboard

Live page: https://sakthi-kpn.github.io/Grocery_Availability_Dashboard/

- Data: one file per day in `data/daily/` (Grocery_YYYY-MM-DD.csv.gz).
- Every day at 8:30 AM IST (backup 11:30 AM) GitHub reads the published "Grocery Extract"
  tab (link in `config/sheet_csv_url.txt`), saves any new day and republishes the page.
- Stores, class and cluster manager: `config/stores.csv`.
- Marketing scheme items (L2 "Marketing (scheme)") are excluded from availability.
- Run locally: `python build_data.py` then `python -m http.server 8000`.
