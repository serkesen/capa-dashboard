import os, json, datetime as dt, requests
from google.oauth2 import service_account
import google.auth.transport.requests

SITE = 'sc-domain:capaortodonti.com'
PROP = '545364640'
OLD_PROP = '355419399'   # eski (donmus) GA4 property - tek seferlik baseline
SB_URL = os.environ['SUPABASE_URL'].rstrip('/')
SB_KEY = os.environ['SUPABASE_SERVICE_KEY']
BACKFILL = int(os.environ.get('BACKFILL_DAYS', '4'))
BASELINE_DAYS = int(os.environ.get('BASELINE_DAYS', '540'))
BRAND = ('capa', 'çapa')

creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ['GOOGLE_CREDENTIALS']),
    scopes=['https://www.googleapis.com/auth/analytics.readonly',
            'https://www.googleapis.com/auth/webmasters.readonly'])
creds.refresh(google.auth.transport.requests.Request())
GH = {'Authorization': 'Bearer ' + creds.token}

def upsert(table, rows, conflict):
    for i in range(0, len(rows), 500):
        r = requests.post(SB_URL + '/rest/v1/' + table + '?on_conflict=' + conflict,
            headers={'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY,
                     'Content-Type': 'application/json',
                     'Prefer': 'resolution=merge-duplicates'},
            json=rows[i:i+500], timeout=60)
        r.raise_for_status()
    print(table, len(rows))

today = dt.date.today()
start = (today - dt.timedelta(days=BACKFILL)).isoformat()
end = today.isoformat()
print('BACKFILL', BACKFILL, start, end)

def gsc(dims):
    out, sr = [], 0
    while True:
        r = requests.post(
            'https://www.googleapis.com/webmasters/v3/sites/' +
            requests.utils.quote(SITE, safe='') + '/searchAnalytics/query',
            headers=GH, json={'startDate': start, 'endDate': end,
                'dimensions': dims, 'rowLimit': 25000, 'startRow': sr}, timeout=120)
        r.raise_for_status()
        rows = r.json().get('rows', [])
        out += rows
        if len(rows) < 25000:
            return out
        sr += 25000

upsert('gsc_site_daily', [{'date': r['keys'][0], 'clicks': r['clicks'],
    'impressions': r['impressions'], 'ctr': round(r['ctr'], 4),
    'position': round(r['position'], 2)} for r in gsc(['date'])], 'date')

upsert('gsc_page_daily', [{'date': r['keys'][0], 'page': r['keys'][1],
    'clicks': r['clicks'], 'impressions': r['impressions'], 'ctr': round(r['ctr'], 4),
    'position': round(r['position'], 2)} for r in gsc(['date', 'page'])], 'date,page')

upsert('gsc_query_daily', [{'date': r['keys'][0], 'query': r['keys'][1],
    'clicks': r['clicks'], 'impressions': r['impressions'], 'ctr': round(r['ctr'], 4),
    'position': round(r['position'], 2),
    'branded': any(b in r['keys'][1].lower() for b in BRAND)}
    for r in gsc(['date', 'query'])], 'date,query')

def ga4(body, prop=PROP):
    r = requests.post(
        'https://analyticsdata.googleapis.com/v1beta/properties/' + prop + ':runReport',
        headers=GH, json=body, timeout=120)
    r.raise_for_status()
    return r.json().get('rows', [])

d8 = lambda s: s[0:4] + '-' + s[4:6] + '-' + s[6:8]

rows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
    'dimensions': [{'name': 'date'}, {'name': 'sessionDefaultChannelGroup'}],
    'metrics': [{'name': 'sessions'}, {'name': 'totalUsers'}], 'limit': 100000})
upsert('ga4_channel_daily', [{'date': d8(r['dimensionValues'][0]['value']),
    'channel': r['dimensionValues'][1]['value'],
    'sessions': int(r['metricValues'][0]['value']),
    'users': int(r['metricValues'][1]['value'])} for r in rows], 'date,channel')

rows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
    'dimensions': [{'name': 'date'}, {'name': 'eventName'}],
    'metrics': [{'name': 'eventCount'}],
    'dimensionFilter': {'filter': {'fieldName': 'eventName',
        'inListFilter': {'values': ['randevu_tamamlandi', 'telefon_tiklama']}}},
    'limit': 100000})
upsert('ga4_event_daily', [{'date': d8(r['dimensionValues'][0]['value']),
    'event_name': r['dimensionValues'][1]['value'], 'dim1': '', 'dim2': '',
    'count': int(r['metricValues'][0]['value'])} for r in rows],
    'date,event_name,dim1,dim2')

# --- Tek seferlik baseline: eski (donmus) GA4 property 355419399 ---
# ga4_baseline_daily bostaysa eski property'nin gecmis trafigini bir kez ceker,
# sonraki calismalarda dolu oldugu icin atlar. Yeni property'nin canli
# tablolarina dokunmaz.
chk = requests.get(SB_URL + '/rest/v1/ga4_baseline_daily?select=date&limit=1',
    headers={'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY}, timeout=30)
chk.raise_for_status()
if len(chk.json()) == 0:
    bstart = (today - dt.timedelta(days=BASELINE_DAYS)).isoformat()
    brows = ga4({'dateRanges': [{'startDate': bstart, 'endDate': end}],
        'dimensions': [{'name': 'date'}, {'name': 'sessionDefaultChannelGroup'}],
        'metrics': [{'name': 'sessions'}, {'name': 'totalUsers'}], 'limit': 100000},
        prop=OLD_PROP)
    upsert('ga4_baseline_daily', [{'date': d8(r['dimensionValues'][0]['value']),
        'channel': r['dimensionValues'][1]['value'],
        'sessions': int(r['metricValues'][0]['value']),
        'users': int(r['metricValues'][1]['value'])} for r in brows], 'date,channel')
    print('BASELINE rows', len(brows),
          'range', (min(d8(r['dimensionValues'][0]['value']) for r in brows) if brows else '-'),
          (max(d8(r['dimensionValues'][0]['value']) for r in brows) if brows else '-'))
else:
    print('BASELINE skip (dolu)')

# --- Tek seferlik teshis: eski property landing-page dususu (zirve vs son) ---
# ga4_page_compare bostaysa eski property'nin iki donem landing-page oturumlarini
# bir kez ceker (hangi sayfalar dustu analizi). Bir kez calisir, sonra atlar.
chk2 = requests.get(SB_URL + '/rest/v1/ga4_page_compare?select=page&limit=1',
    headers={'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY}, timeout=30)
chk2.raise_for_status()
if len(chk2.json()) == 0:
    for period, ps, pe in [('peak', '2025-02-01', '2025-04-30'),
                           ('recent', '2026-04-01', '2026-06-30')]:
        prows = ga4({'dateRanges': [{'startDate': ps, 'endDate': pe}],
            'dimensions': [{'name': 'landingPagePlusQueryString'}],
            'metrics': [{'name': 'sessions'}], 'limit': 100000}, prop=OLD_PROP)
        agg = {}
        for r in prows:
            pg = r['dimensionValues'][0]['value'].split('?')[0][:300]
            agg[pg] = agg.get(pg, 0) + int(r['metricValues'][0]['value'])
        upsert('ga4_page_compare', [{'period': period, 'page': pg, 'sessions': s}
            for pg, s in agg.items()], 'period,page')
    print('PAGE_COMPARE done')
else:
    print('PAGE_COMPARE skip (dolu)')

# --- Meta: Facebook sayfa (+ bagliysa Instagram) takipci snapshot ---
# META_PAGE_TOKEN secret'i yoksa sessizce atlar; hata cikarsa fetcher'i bozmaz.
# Takipci toplam sayisidir; her calismada bugunun satiri uzerine yazilir (son snapshot).
META_TOKEN = os.environ.get('META_PAGE_TOKEN', '').strip()
META_PAGE = os.environ.get('META_PAGE_ID', '233229654211').strip()
META_IG = os.environ.get('META_IG_ID', '').strip()
GRAPH = 'https://graph.facebook.com/v25.0/'
if META_TOKEN:
    try:
        srows = []
        fb = requests.get(GRAPH + META_PAGE,
            params={'fields': 'followers_count,fan_count', 'access_token': META_TOKEN},
            timeout=60).json()
        if 'error' in fb:
            print('META fb error', fb['error'].get('message'))
        else:
            srows.append({'date': end, 'platform': 'facebook',
                'followers': fb.get('followers_count', fb.get('fan_count'))})
        if META_IG:
            ig = requests.get(GRAPH + META_IG,
                params={'fields': 'followers_count', 'access_token': META_TOKEN},
                timeout=60).json()
            if 'error' in ig:
                print('META ig error', ig['error'].get('message'))
            elif 'followers_count' in ig:
                srows.append({'date': end, 'platform': 'instagram',
                    'followers': ig['followers_count']})
        if srows:
            upsert('meta_social_daily', srows, 'date,platform')
        print('META', [s['platform'] + ':' + str(s['followers']) for s in srows])
    except Exception as e:
        print('META error', repr(e))
else:
    print('META skip (token yok)')

print('OK')
