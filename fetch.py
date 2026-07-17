import os, json, datetime as dt, requests
from google.oauth2 import service_account
import google.auth.transport.requests

SITE = 'sc-domain:capaortodonti.com'
PROP = '545364640'
SB_URL = os.environ['SUPABASE_URL'].rstrip('/')
SB_KEY = os.environ['SUPABASE_SERVICE_KEY']
BACKFILL = int(os.environ.get('BACKFILL_DAYS', '4'))
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

def ga4(body):
    r = requests.post(
        'https://analyticsdata.googleapis.com/v1beta/properties/' + PROP + ':runReport',
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
print('OK')
