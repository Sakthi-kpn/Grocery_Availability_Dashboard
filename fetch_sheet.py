#!/usr/bin/env python3
"""Download the published 'Grocery Extract' CSV (Google Sheets -> File -> Share -> Publish to web)
and save each day it holds as data/daily/Grocery_YYYY-MM-DD.csv.gz when we don't have it yet.
Writes new=true/false to $GITHUB_OUTPUT."""
import os, sys, io, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = os.path.join(HERE, 'config', 'sheet_csv_url.txt')
out_flag = os.environ.get('GITHUB_OUTPUT')

def flag(v):
    if out_flag:
        with open(out_flag, 'a') as f: f.write(f'new={v}\n')

if not os.path.exists(cfg) or not open(cfg).read().strip():
    print('No config/sheet_csv_url.txt - skipping sheet fetch'); flag('false'); sys.exit(0)
url = open(cfg).read().strip().split()[0]

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
raw = urllib.request.urlopen(req, timeout=60).read().decode('utf-8-sig')
df = pd.read_csv(io.StringIO(raw))
df.columns = [str(c).strip() for c in df.columns]
df.columns = [c if c.lower() not in ('outlet_id','dt','ksin') else c.lower() for c in df.columns]
need = ['outlet_id', 'dt', 'ksin', 'total_sku_hours', 'total_store_hrs']
if any(c not in df.columns for c in need) or df.empty:
    print('Published sheet does not look like the Grocery Extract:', df.columns.tolist()[:10]); flag('false'); sys.exit(0)

df = df[df['outlet_id'].astype(str).str.strip() != '']
df['dt'] = pd.to_datetime(df['dt'], errors='coerce', format='mixed').dt.strftime('%Y-%m-%d')
df = df.dropna(subset=['dt'])
os.makedirs(os.path.join(HERE, 'data', 'daily'), exist_ok=True)

# The sheet may hold one day or several (e.g. last 3 days). Save every day we don't have yet,
# or that now has more rows than before, so a missed refresh day is recovered later.
saved = []
for day, part in sorted(df.groupby('dt')):
    path = os.path.join(HERE, 'data', 'daily', f'Grocery_{day}.csv.gz')
    if os.path.exists(path) and len(pd.read_csv(path, low_memory=False)) >= len(part):
        print(f'{day} already saved ({len(part)} rows)'); continue
    part.to_csv(path, index=False, compression='gzip'); saved.append(day)
    print(f'Saved {path} ({len(part)} rows)')
flag('true' if saved else 'false')
