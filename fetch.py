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

upsert('gsc_device_daily', [{'date': r['keys'][0], 'device': r['keys'][1],
    'clicks': r['clicks'], 'impressions': r['impressions'], 'ctr': round(r['ctr'], 4),
    'position': round(r['position'], 2)} for r in gsc(['date', 'device'])], 'date,device')

upsert('gsc_country_daily', [{'date': r['keys'][0], 'country': r['keys'][1],
    'clicks': r['clicks'], 'impressions': r['impressions'], 'ctr': round(r['ctr'], 4),
    'position': round(r['position'], 2)} for r in gsc(['date', 'country'])], 'date,country')

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

# --- Donusum halkasi (reklam atribusyon): randevu/telefon event'leri kaynak/mecra/kampanya kirilimiyla ---
# Reklam basladiginda cpc kaynaklarini ayirir; simdi organik baseline'i doldurur. Ayri tablo -> ga4_event_daily totalini bozmaz.
crows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
    'dimensions': [{'name': 'date'}, {'name': 'eventName'},
                   {'name': 'sessionSource'}, {'name': 'sessionMedium'},
                   {'name': 'sessionCampaignName'}],
    'metrics': [{'name': 'eventCount'}],
    'dimensionFilter': {'filter': {'fieldName': 'eventName',
        'inListFilter': {'values': ['randevu_tamamlandi', 'telefon_tiklama']}}},
    'limit': 100000})
upsert('ga4_conv_source_daily', [{'date': d8(r['dimensionValues'][0]['value']),
    'event_name': r['dimensionValues'][1]['value'],
    'source': r['dimensionValues'][2]['value'] or '',
    'medium': r['dimensionValues'][3]['value'] or '',
    'campaign': r['dimensionValues'][4]['value'] or '',
    'count': int(r['metricValues'][0]['value'])} for r in crows],
    'date,event_name,source,medium,campaign')

# --- GTM tab: randevu_adim funnel (adim custom dimension, event-scope) ---
# GTM'in izledigi randevu adimlarini adim kirilimiyla ceker. customEvent:adim yoksa fail-soft atlar (fetcher bozulmaz).
try:
    frows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
        'dimensions': [{'name': 'date'}, {'name': 'customEvent:adim'}],
        'metrics': [{'name': 'eventCount'}],
        'dimensionFilter': {'filter': {'fieldName': 'eventName',
            'inListFilter': {'values': ['randevu_adim']}}},
        'limit': 100000})
    upsert('ga4_funnel_daily', [{'date': d8(r['dimensionValues'][0]['value']),
        'adim': (r['dimensionValues'][1]['value'] or '(yok)'),
        'count': int(r['metricValues'][0]['value'])} for r in frows], 'date,adim')
    print('ga4_funnel_daily', len(frows))
except Exception as e:
    print('funnel skip (customEvent:adim?):', repr(e)[:140])

# --- GTM tab: tum izlenen event'ler (isim x gun) ---
erows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
    'dimensions': [{'name': 'date'}, {'name': 'eventName'}],
    'metrics': [{'name': 'eventCount'}], 'limit': 100000})
upsert('ga4_events_all_daily', [{'date': d8(r['dimensionValues'][0]['value']),
    'event_name': r['dimensionValues'][1]['value'],
    'count': int(r['metricValues'][0]['value'])} for r in erows], 'date,event_name')
print('ga4_events_all_daily', len(erows))

# --- GA4 tab: genis GA4 veri seti (overview + kirilimlar + landing + demografi) ---
def gi(v):
    try:
        return int(float(v))
    except Exception:
        return 0
def gf(v):
    try:
        return round(float(v), 4)
    except Exception:
        return 0.0

# Overview: gunluk metrikler (oturum/kullanici/engagement/sure/bounce)
try:
    orows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
        'dimensions': [{'name': 'date'}],
        'metrics': [{'name': 'sessions'}, {'name': 'totalUsers'}, {'name': 'newUsers'},
            {'name': 'screenPageViews'}, {'name': 'engagedSessions'}, {'name': 'engagementRate'},
            {'name': 'averageSessionDuration'}, {'name': 'bounceRate'}], 'limit': 100000})
    upsert('ga4_overview_daily', [{'date': d8(r['dimensionValues'][0]['value']),
        'sessions': gi(r['metricValues'][0]['value']), 'users': gi(r['metricValues'][1]['value']),
        'new_users': gi(r['metricValues'][2]['value']), 'pageviews': gi(r['metricValues'][3]['value']),
        'engaged_sessions': gi(r['metricValues'][4]['value']), 'engagement_rate': gf(r['metricValues'][5]['value']),
        'avg_duration': round(float(r['metricValues'][6]['value']), 1), 'bounce_rate': gf(r['metricValues'][7]['value'])}
        for r in orows], 'date')
    print('ga4_overview_daily', len(orows))
except Exception as e:
    print('overview skip', repr(e)[:120])

# Kirilimlar: device / city / newVsReturning / browser -> ga4_breakdown_daily
for kind, dim in [('device', 'deviceCategory'), ('city', 'city'), ('usertype', 'newVsReturning'), ('browser', 'browser')]:
    try:
        brows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
            'dimensions': [{'name': 'date'}, {'name': dim}],
            'metrics': [{'name': 'sessions'}, {'name': 'totalUsers'}], 'limit': 100000})
        upsert('ga4_breakdown_daily', [{'date': d8(r['dimensionValues'][0]['value']), 'kind': kind,
            'label': (r['dimensionValues'][1]['value'] or '(yok)'),
            'sessions': gi(r['metricValues'][0]['value']), 'users': gi(r['metricValues'][1]['value'])}
            for r in brows], 'date,kind,label')
        print('ga4_breakdown', kind, len(brows))
    except Exception as e:
        print('breakdown skip', kind, repr(e)[:100])

# Landing page (query string strip + gunluk topla)
try:
    lrows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
        'dimensions': [{'name': 'date'}, {'name': 'landingPagePlusQueryString'}],
        'metrics': [{'name': 'sessions'}, {'name': 'engagedSessions'}], 'limit': 100000})
    lagg = {}
    for r in lrows:
        dt2 = d8(r['dimensionValues'][0]['value'])
        lp = (r['dimensionValues'][1]['value'] or '/').split('?')[0][:200]
        k = (dt2, lp); a = lagg.get(k, {'s': 0, 'e': 0})
        a['s'] += gi(r['metricValues'][0]['value']); a['e'] += gi(r['metricValues'][1]['value']); lagg[k] = a
    upsert('ga4_landing_daily', [{'date': k[0], 'landing': k[1], 'sessions': v['s'], 'engaged_sessions': v['e']}
        for k, v in lagg.items()], 'date,landing')
    print('ga4_landing_daily', len(lagg))
except Exception as e:
    print('landing skip', repr(e)[:120])

# Demografi (fail-soft; Google Signals kapaliysa/thresholded -> bos)
try:
    dmrows = ga4({'dateRanges': [{'startDate': start, 'endDate': end}],
        'dimensions': [{'name': 'date'}, {'name': 'userGender'}, {'name': 'userAgeBracket'}],
        'metrics': [{'name': 'totalUsers'}], 'limit': 100000})
    upsert('ga4_demo_daily', [{'date': d8(r['dimensionValues'][0]['value']),
        'gender': (r['dimensionValues'][1]['value'] or '(yok)'), 'age': (r['dimensionValues'][2]['value'] or '(yok)'),
        'users': gi(r['metricValues'][0]['value'])} for r in dmrows], 'date,gender,age')
    print('ga4_demo_daily', len(dmrows))
except Exception as e:
    print('demo skip', repr(e)[:120])

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
# FB Page insights: pages_read_engagement izni YETIYOR (read_insights GEREKMIYOR; 23 Tem canli Graph API v25 ile dogrulandi).
# Asagidaki metrikler v25'te gecerli; metrik-basi fail-soft (kolon NULL kalir), fetcher'i bozmaz. (date,platform) satirina yazilir.
# Not: page_impressions*/reach + page_fan_adds/removes Meta tarafindan KALDIRILDI -> reach FB'de artik yok.
FB_INSIGHTS = [
    ('page_post_engagements', 'total_interactions'),
    ('page_views_total', 'views'),
    ('page_daily_follows_unique', 'follower_adds'),
    ('page_daily_unfollows_unique', 'follower_removes'),
    ('page_actions_post_reactions_total', 'likes'),
    ('page_total_actions', 'total_actions'),
    ('page_video_views', 'video_views'),
]
def fb_insight(metric):
    try:
        r = requests.get(GRAPH + META_PAGE + '/insights/' + metric,
            params={'period': 'day', 'access_token': META_TOKEN}, timeout=60).json()
        if 'error' in r:
            print('META insight', metric, 'err', str(r['error'].get('message'))[:70])
            return None
        data = r.get('data', [])
        vals = data[0].get('values', []) if data else []
        v = vals[-1].get('value') if vals else None
        return int(v) if isinstance(v, (int, float)) else None
    except Exception as e:
        print('META insight', metric, 'exc', repr(e))
        return None
if META_TOKEN:
    try:
        srows = []
        fb = requests.get(GRAPH + META_PAGE,
            params={'fields': 'followers_count,fan_count', 'access_token': META_TOKEN},
            timeout=60).json()
        if 'error' in fb:
            print('META fb error', fb['error'].get('message'))
        else:
            frow = {'date': end, 'platform': 'facebook',
                'followers': fb.get('followers_count', fb.get('fan_count'))}
            for _m, _c in FB_INSIGHTS:
                _v = fb_insight(_m)
                if _v is not None:
                    frow[_c] = _v
            print('META fb insights filled:',
                sorted(k for k in frow if k not in ('date', 'platform', 'followers')))
            srows.append(frow)
        # IG: META_IG_ID env yoksa sayfaya bagli IG hesabini OTOMATIK bul
        if not META_IG:
            try:
                pg = requests.get(GRAPH + META_PAGE,
                    params={'fields': 'instagram_business_account', 'access_token': META_TOKEN},
                    timeout=60).json()
                iba = pg.get('instagram_business_account') or {}
                META_IG = str(iba.get('id') or '')
                print('META ig auto-discover:', META_IG or 'YOK',
                      (pg.get('error') or {}).get('message', ''))
            except Exception as e:
                print('META ig discover err', repr(e))
        if META_IG:
            ig = requests.get(GRAPH + META_IG,
                params={'fields': 'followers_count,media_count,username', 'access_token': META_TOKEN},
                timeout=60).json()
            if 'error' in ig:
                print('META ig error', str(ig['error'].get('message'))[:80])
            else:
                print('META ig OK', ig.get('username'), 'followers', ig.get('followers_count'))
                if ig.get('followers_count') is not None:
                    srows.append({'date': end, 'platform': 'instagram',
                        'followers': ig['followers_count']})
        if srows:
            upsert('meta_social_daily', srows, 'date,platform')
        print('META', [s['platform'] + ':' + str(s['followers']) for s in srows])
    except Exception as e:
        print('META error', repr(e))
else:
    print('META skip (token yok)')

# --- MS Clarity (Data Export API) — token varsa, gunde ~1 kez (rate-limit 10/gun) ---
CLARITY_TOKEN = os.environ.get('CLARITY_TOKEN', '')
_run_clarity = bool(CLARITY_TOKEN) and (os.environ.get('CLARITY_RUN') == '1' or dt.datetime.utcnow().hour < 6)
if _run_clarity:
    try:
        def clarity(dims=None):
            params = {'numOfDays': 1}
            if dims:
                for _i, _d in enumerate(dims, 1):
                    params['dimension' + str(_i)] = _d
            _r = requests.get('https://www.clarity.ms/export-data/api/v1/project-live-insights',
                headers={'Authorization': 'Bearer ' + CLARITY_TOKEN}, params=params, timeout=120)
            _r.raise_for_status()
            return _r.json()

        def _cnum(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _norm(s):
            return ''.join(ch for ch in str(s).lower() if ch.isalnum())

        cday = today.isoformat()
        agg = clarity()
        by = {}
        for m in (agg or []):
            info = m.get('information') or []
            by[_norm(m.get('metricName'))] = info[0] if info else {}
        for _a, _b in [('excessivescrolling', 'excessivescroll'), ('quickback', 'quickbackclick'),
                       ('deadclick', 'deadclickcount'), ('rageclick', 'rageclickcount'),
                       ('scripterror', 'scripterrorcount'), ('errorclick', 'errorclickcount'),
                       ('engagement', 'engagementtime')]:
            if _a in by and _b not in by:
                by[_b] = by[_a]

        def pk(name, *keys):
            row = by.get(name, {})
            for k in keys:
                if k in row and _cnum(row[k]) is not None:
                    return _cnum(row[k])
            for k, v in row.items():
                n = _cnum(v)
                if n is not None:
                    return n
            return None

        tr = by.get('traffic', {})
        crow = {'date': cday,
                'sessions': _cnum(tr.get('totalSessionCount')),
                'bot_sessions': _cnum(tr.get('totalBotSessionCount')),
                'distinct_users': _cnum(tr.get('distinctUserCount') or tr.get('distantUserCount')),
                'pages_per_session': _cnum(tr.get('PagesPerSessionPercentage') or tr.get('pagesPerSessionPercentage')),
                'scroll_depth': pk('scrolldepth', 'averageScrollDepth', 'AverageScrollDepth'),
                'engage_active': pk('engagementtime', 'activeTime', 'totalActiveTime'),
                'engage_total': pk('engagementtime', 'totalTime', 'totalSessionTime'),
                'dead_clicks': pk('deadclickcount', 'subTotal', 'totalCount'),
                'rage_clicks': pk('rageclickcount', 'subTotal', 'totalCount'),
                'quickbacks': pk('quickbackclick', 'subTotal', 'totalCount'),
                'excessive_scroll': pk('excessivescroll', 'subTotal', 'totalCount'),
                'script_errors': pk('scripterrorcount', 'subTotal', 'totalCount'),
                'error_clicks': pk('errorclickcount', 'subTotal', 'totalCount'),
                'raw': agg}
        upsert('clarity_daily', [crow], 'date')

        brk = []
        for kind, dim in [('device', 'Device'), ('country', 'Country')]:
            try:
                data = clarity([dim])
                for m in (data or []):
                    if _norm(m.get('metricName')) == 'traffic':
                        for info in (m.get('information') or []):
                            lbl = info.get(dim) or info.get('Country/Region') or info.get('Country') or info.get('Device') or '(yok)'
                            sc = _cnum(info.get('totalSessionCount'))
                            if sc is not None:
                                brk.append({'date': cday, 'kind': kind, 'label': str(lbl)[:80], 'sessions': sc})
            except Exception as _e:
                print('clarity brk', kind, 'ERR', repr(_e))
        if brk:
            upsert('clarity_breakdown_daily', brk, 'date,kind,label')
        print('clarity OK metrics:', list(by.keys()))
    except Exception as e:
        print('clarity ERR', repr(e))
else:
    print('clarity skip (token yok / gun-ici)')

print('OK')
