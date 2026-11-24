#!/usr/bin/env python3
"""Build data.json for the Grocery Availability Dashboard.

Usage:  python build_data.py [xlsx-file-or-folder] [out.json]
Default: every .xlsx/.csv in ./data (and subfolders) -> ./data.json
"Newest" = last git commit time (falls back to file modified time).
"""
import sys, os, glob, json, subprocess, datetime as dt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'data')
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'data.json')

def stamp(f):
    try:
        t = subprocess.run(['git', 'log', '-1', '--format=%ct', '--', f], capture_output=True, text=True, cwd=HERE).stdout.strip()
        if t: return (int(t), os.path.getmtime(f))
    except Exception: pass
    return (0, os.path.getmtime(f))

RAW_COLS = ['outlet_id', 'dt', 'ksin', 'kpn_title', 'l1_name', 'l2_name', 'l3_name', 'total_sku_hours', 'total_store_hrs'] + [f'h{i:02d}' for i in range(7, 21)]
NUM_COLS = RAW_COLS[7:]
RENAME = {'l1_category': 'l1_name', 'l2_category': 'l2_name', 'l3_category': 'l3_name'}

def fix_shifted(df):
    """Rows pasted from an export with an extra column (l2_name) land one column to the right.
    Detect them (text in total_sku_hours) and shift their numeric block back."""
    cols = list(df.columns)
    if 'total_sku_hours' not in cols: return df
    bad = pd.to_numeric(df['total_sku_hours'], errors='coerce').isna() & df['total_sku_hours'].notna()
    if bad.any():
        i = cols.index('total_sku_hours')
        tail = cols[i:]                      # total_sku_hours ... last column
        df.loc[bad, tail[:-1]] = df.loc[bad, tail[1:]].values
        print(f'  repaired {int(bad.sum())} shifted rows')
    return df

if os.path.isdir(src):
    files = [f for f in glob.glob(os.path.join(src, '**', '*.*'), recursive=True)
             if f.lower().endswith(('.xlsx', '.xls', '.csv', '.csv.gz')) and not os.path.basename(f).startswith('~$')]
else:
    files = [src]
if not files: sys.exit('No .xlsx file found in ' + str(src))
files.sort(key=stamp)                        # oldest -> newest; newer rows win on duplicates

raws, a, s = [], None, None
for order, f in enumerate(files):
    print('Reading', os.path.basename(f))
    sheets = {'csv': pd.read_csv(f, low_memory=False, encoding='utf-8-sig')} if f.lower().endswith(('.csv', '.csv.gz')) else pd.read_excel(f, sheet_name=None)
    for name, df in sheets.items():
        df.columns = [str(c).strip() for c in df.columns]
        low = {c.lower(): c for c in df.columns}
        if {'outlet_id', 'dt', 'ksin'} <= set(low):
            df = df.rename(columns={v: k for k, v in low.items()}).rename(columns=RENAME)
            for c in ('l2_name', 'l3_name'):
                if c not in df.columns: df[c] = 'Other'
            miss = [c for c in RAW_COLS if c not in df.columns]
            if miss: print(f'  skip sheet {name}: missing {miss}'); continue
            df = df[RAW_COLS].copy(); df['_o'] = order; raws.append(df)
if not raws: sys.exit('No availability rows found (need outlet_id, dt, ksin columns)')
r = pd.concat(raws, ignore_index=True)
for c in NUM_COLS: r[c] = pd.to_numeric(r[c], errors='coerce').fillna(0)
r['dt'] = pd.to_datetime(r['dt'], format='mixed', dayfirst=False).dt.normalize()
for c in ('l1_name', 'l2_name', 'l3_name'): r[c] = r[c].fillna('Other').astype(str).str.strip()
# marketing scheme items (NSO launch offers, subscriptions) are not shelf stock
EXCL = r['l2_name'].eq('Marketing (scheme)')
EXCLUDED = sorted(r.loc[EXCL, 'kpn_title'].unique().tolist())
r = r[~EXCL]
# each date comes from the newest file that contains it; then drop exact duplicates
r = r[r['_o'] == r.groupby('dt')['_o'].transform('max')]
r = r.drop_duplicates(['outlet_id', 'dt', 'ksin'], keep='last').drop(columns='_o')
src = files[-1]
print('Rows', len(r), '| dates', r.dt.min().date(), '->', r.dt.max().date())
# stores: config/stores.csv (outlet_id,store,class,cluster)
s = pd.read_csv(os.path.join(HERE, 'config', 'stores.csv'), dtype=str)
s = s.rename(columns={'store': 'store', 'class': 'cls', 'cluster': 'COM'})
for c in ('store', 'cls', 'COM'): s[c] = s[c].astype(str).str.strip()

Y = r.dt.max()
r = r[(r.dt.dt.year == Y.year) & (r.dt.dt.month == Y.month)]      # MTD = month of latest date

unknown = sorted(set(r.outlet_id) - set(s.outlet_id))
if unknown: print('Stores not in config/stores.csv (shown with their id):', unknown)
s = pd.concat([s, pd.DataFrame({'outlet_id': unknown, 'store': unknown, 'cls': '-', 'COM': 'Unmapped'})], ignore_index=True)
m = r.merge(s[['outlet_id', 'store', 'cls', 'COM']], on='outlet_id', how='left')
m['dlv'] = m['l2_name']            # second breakup = L2 group
D_unmapped = []
H = [f'h{i:02d}' for i in range(7, 21)]
m['oos0'] = m.total_sku_hours == 0; m['full'] = m.total_sku_hours == m.total_store_hrs
yd = m[m.dt == Y]

def av(d): return round(d.total_sku_hours.sum() / d.total_store_hrs.sum() * 100, 1)
def kpi(d):
    return dict(avail=av(d), rows=len(d), oos0=int(d.oos0.sum()), oos0p=round(d.oos0.mean() * 100, 1),
                full=round(d.full.mean() * 100, 1), lost=int(d.total_store_hrs.sum() - d.total_sku_hours.sum()))
def brk(col):
    o = [dict(k=k, y=kpi(g[g.dt == Y]), m=kpi(g)) for k, g in m.groupby(col)]
    return sorted(o, key=lambda z: z['m']['avail'])
hr = lambda d: [round(float(d[h].mean()), 1) for h in H]

D = {}
D['generated_at'] = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
D['source'] = os.path.basename(src) if len(files) == 1 else f'{len(files)} files in data/ (latest: {os.path.basename(src)})'
D['date'] = Y.strftime('%d %b %Y'); D['dshort'] = Y.strftime('%d %b'); D['mon'] = Y.strftime('%b')
D['ov'] = dict(y=kpi(yd), m=kpi(m))
D['stores_n'] = int(m.outlet_id.nunique()); D['sku_n'] = int(m.ksin.nunique())
D['cat'] = brk('l1_name'); D['dlv'] = brk('l2_name'); D['cls'] = brk('cls'); D['com'] = brk('COM')
l3 = []
for k, g in m.groupby('l3_name'):
    gy = g[g.dt == Y]
    if len(gy) < 20: continue
    l3.append(dict(k=k, l1=g.l1_name.iloc[0], l2=g.l2_name.iloc[0], skus=int(g.ksin.nunique()), y=kpi(gy), m=kpi(g)))
D['l3'] = l3
# category tree: every L1, L1>L2 and L1>L2>L3 node with yesterday + MTD KPIs
tree = []
for keys, lvl in ((['l1_name'], 1), (['l1_name', 'l2_name'], 2), (['l1_name', 'l2_name', 'l3_name'], 3)):
    for k, g in m.groupby(keys):
        k = k if isinstance(k, tuple) else (k,)
        gy = g[g.dt == Y]
        if not len(gy): continue
        tree.append(dict(lv=lvl, p=list(k), skus=int(g.ksin.nunique()), y=kpi(gy), m=kpi(g)))
D['tree'] = tree
D['com_listed'] = s[s.COM != 'Unmapped'].COM.value_counts().to_dict()
D['hour_y'] = hr(yd); D['hour_m'] = hr(m)
D['hour_cat_y'] = {c: hr(g) for c, g in yd.groupby('l1_name')}
D['hour_cat_m'] = {c: hr(g) for c, g in m.groupby('l1_name')}
D['hour_dlv_y'] = {}
D['trend'] = [dict(d=k.strftime('%d'), v=av(g), **{c: av(gg) for c, gg in g.groupby('l1_name')}) for k, g in m.groupby('dt')]

# recent 7 days vs earlier days of the month
days = sorted(m.dt.unique())
if len(days) >= 8:
    cut = pd.Timestamp(days[-7]); e = m[m.dt < cut]; rc = m[m.dt >= cut]
    D['earlier'] = dict(avail=av(e), label=f"{e.dt.min().strftime('%d')}–{e.dt.max().strftime('%d')} {D['mon']}")
    D['recent'] = dict(avail=av(rc), label=f"{rc.dt.min().strftime('%d')}–{rc.dt.max().strftime('%d')} {D['mon']}")
else:
    D['earlier'] = D['recent'] = None

# SKUs
sk = []
for k, g in m.groupby('ksin'):
    gy = g[g.dt == Y]
    sk.append(dict(n=g.kpn_title.iloc[0], c=g.l1_name.iloc[0], dl=g.l3_name.iloc[0], l2=g.l2_name.iloc[0], ya=av(gy) if len(gy) else None, ma=av(g),
                   yo=int(gy.oos0.sum()), ys=len(gy), mo=int(g.oos0.sum()), mr=len(g)))
D['skus'] = sk
D['dead'] = [z['n'] for z in sk if z['ma'] == 0]
nd = m[~m.kpn_title.isin(D['dead'])]
D['exdead_y'] = av(nd[nd.dt == Y]) if len(nd[nd.dt == Y]) else None; D['exdead_m'] = av(nd)
D['notinraw'] = []
D['excluded'] = EXCLUDED
D['unmapped'] = D_unmapped
D['missing_stores'] = s[~s.outlet_id.isin(r.outlet_id) & (s.COM != 'Unmapped')].store.tolist()

# stores
ny = {c['k']: c['y']['avail'] for c in D['cat']}
st = []
for o, g in m.groupby('outlet_id'):
    gy = g[g.dt == Y]
    ch = g.groupby('kpn_title').oos0.sum(); thr = max(2, len(days) // 2); ch = ch[ch >= thr].sort_values(ascending=False)
    st.append(dict(id=o, name=g.store.iloc[0], cls=g.cls.iloc[0], com=g.COM.iloc[0], y=kpi(gy), m=kpi(g),
        daily=[av(gg) for _, gg in g.groupby('dt')], hour_y=hr(gy),
        caty={c: av(gg) for c, gg in gy.groupby('l1_name')}, catm={c: av(gg) for c, gg in g.groupby('l1_name')},
        dlvy={c: av(gg) for c, gg in gy.groupby('dlv')}, dlvm={c: av(gg) for c, gg in g.groupby('dlv')},
        chronic=[[k, int(v)] for k, v in ch.items()], last7=av(g[g.dt > Y - pd.Timedelta(days=7)])))
for i, z in enumerate(sorted(st, key=lambda z: -z['y']['avail'])): z['ry'] = i + 1
for i, z in enumerate(sorted(st, key=lambda z: -z['m']['avail'])): z['rm'] = i + 1
avg0 = D['ov']['y']['oos0'] / len(st)
avgch = sum(len(z['chronic']) for z in st) / len(st)
for z in st:
    d = round(z['y']['avail'] - z['m']['avail'], 1); z['delta'] = d
    z['tag'] = 'Recovering' if d >= 4 else ('Slipping' if d <= -3 else 'Steady')
    ins = []
    gaps = {c: round(z['caty'][c] - ny[c], 1) for c in z['caty']}
    wc = min(gaps, key=gaps.get); bc = max(gaps, key=gaps.get)
    if gaps[wc] <= -5: ins.append((abs(gaps[wc]), f"<b>{wc}</b> drags at {z['caty'][wc]}% — {abs(gaps[wc])} pts below network"))
    if gaps[bc] >= 8: ins.append((gaps[bc] * .6, f"<b>{bc}</b> a strength at {z['caty'][bc]}% (+{gaps[bc]} vs network)"))
    h0, h1 = z['hour_y'][1], z['hour_y'][-1]
    if h0 - h1 >= 10: ins.append((h0 - h1, f"Shelf fades <b>{h0}% → {h1}%</b> from 8 AM to 8 PM — refill gap after noon"))
    nl2 = {c['k']: c['y']['avail'] for c in D['dlv']}
    g2 = {c: round(z['dlvy'][c] - nl2.get(c, z['dlvy'][c]), 1) for c in z['dlvy']}
    if g2:
        w2 = min(g2, key=g2.get)
        if g2[w2] <= -8 and w2 not in gaps: ins.append((abs(g2[w2]) * .7, f"<b>{w2}</b> at {z['dlvy'][w2]}% — {abs(g2[w2])} pts below network"))
    o_ = z['y']['oos0']
    if o_ >= avg0 * 1.4: ins.append((o_, f"<b>{o_} SKUs blank all day</b> (network avg {avg0:.0f})"))
    ch = z['chronic']
    if len(ch) >= max(9, avgch * 1.3): ins.append((len(ch) * 1.2, f"<b>{len(ch)} chronic dead SKUs</b> (zero on {max(2, len(days)//2)}+ days, network avg {avgch:.0f}): {', '.join(c[0] for c in ch[:3])}"))
    if z['last7'] < z['m']['avail'] - 3: ins.append((z['m']['avail'] - z['last7'] + 3, f"Last 7 days {z['last7']}% — trending below MTD"))
    if d >= 6: ins.append((d + 5, f"Yesterday <b>+{d} pts</b> over MTD — sustain the fix"))
    if d <= -3: ins.append((-d + 5, f"Yesterday <b>{d} pts</b> under its MTD run-rate"))
    ins = [t for _, t in sorted(ins, key=lambda q: -q[0])][:3]
    z['ins'] = ins or ["Balanced across categories; network-level performance"]
    z.pop('chronic')
D['stores'] = st

json.dump(D, open(out, 'w'), default=str, separators=(',', ':'))
print('Wrote', out, '| date', D['date'], '| stores', D['stores_n'], '| availability', D['ov']['y']['avail'], '/', D['ov']['m']['avail'])
