import os, json, datetime as dt, requests

# PROBE v3 — "Sayfa atil mi, yoksa API insight'i hic yayinlamiyor mu?"
# Test 1: gonderi etkilesimi (node alanlari, insight DEGIL -> New Pages'te de calisir) = sayfanin nabzi
# Test 2: insight'i AKTIF DONEME (Mart 2026, since/until) sorar -> API-vs-atillik ayrimi
# Test 3: aktif gonderinin lifetime post insight'i

T = os.environ['META_PAGE_TOKEN'].strip()
P = os.environ.get('META_PAGE_ID', '233229654211').strip()
G = 'https://graph.facebook.com/v25.0/'


def get(path, params):
    q = dict(params); q['access_token'] = T
    try:
        return requests.get(G + path, params=q, timeout=60).json()
    except Exception as e:
        return {'__exc': repr(e)}


def ts(y, m, d):
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp())


# ---------- TEST 1: SAYFA NABZI (gonderi etkilesimi, node alanlari) ----------
print('=== TEST 1: GONDERI ETKILESIMI (node alanlari, insight DEGIL) ===')
fields = 'id,created_time,message,shares,likes.summary(true),comments.summary(true),reactions.summary(true)'
posts = get(P + '/posts', {'fields': fields, 'limit': 10})
if 'error' in posts:
    print('posts err', str(posts['error'].get('message'))[:90])
else:
    pl = posts.get('data', [])
    print('cekilen gonderi sayisi:', len(pl))
    for p in pl:
        d = p.get('created_time', '')[:10]
        msg = (p.get('message', '') or '').replace('\n', ' ')[:42]
        lk = p.get('likes', {}).get('summary', {}).get('total_count', '?')
        cm = p.get('comments', {}).get('summary', {}).get('total_count', '?')
        rx = p.get('reactions', {}).get('summary', {}).get('total_count', '?')
        sh = (p.get('shares') or {}).get('count', 0)
        print(d, '| begeni:' + str(lk), 'yorum:' + str(cm), 'reaksiyon:' + str(rx),
              'paylasim:' + str(sh), '|', msg)

# ---------- TEST 2: AKTIF DONEM INSIGHT PENCERESI (since/until) ----------
print('=== TEST 2: AKTIF DONEM INSIGHT (Mart 2026 + Sub 2025 penceresi) ===')
MAR_S, MAR_U = ts(2026, 3, 1), ts(2026, 3, 31)
FEB_S, FEB_U = ts(2025, 2, 10), ts(2025, 3, 5)


def show_win(metric, params, tag):
    r = get(P + '/insights/' + metric, params)
    if '__exc' in r:
        return tag + ':exc'
    if 'error' in r:
        return tag + ':ERR ' + str(r['error'].get('message', ''))[:50]
    d = r.get('data', [])
    if not d:
        return tag + ':EMPTY-ARRAY'
    row = d[0]
    val = row.get('total_value', row.get('values'))
    return tag + ':DATA ' + json.dumps(val)[:160]


WIN = [
    ('page_media_view',       {'metric_type': 'total_value', 'since': MAR_S, 'until': MAR_U}, 'media_view/tv/Mar26'),
    ('page_media_view',       {'period': 'day', 'since': MAR_S, 'until': MAR_U},              'media_view/day/Mar26'),
    ('page_views_total',      {'metric_type': 'total_value', 'since': MAR_S, 'until': MAR_U}, 'views_total/tv/Mar26'),
    ('page_views_total',      {'period': 'day', 'since': MAR_S, 'until': MAR_U},              'views_total/day/Mar26'),
    ('page_post_engagements', {'period': 'day', 'since': MAR_S, 'until': MAR_U},              'post_eng/day/Mar26'),
    ('page_daily_follows_unique', {'period': 'day', 'since': MAR_S, 'until': MAR_U},          'd_follows/day/Mar26'),
    ('page_impressions',      {'period': 'day', 'since': MAR_S, 'until': MAR_U},              'impressions/day/Mar26(eski)'),
    ('page_media_view',       {'metric_type': 'total_value', 'since': FEB_S, 'until': FEB_U}, 'media_view/tv/Feb25'),
]
for metric, params, tag in WIN:
    print(metric.ljust(26), show_win(metric, params, tag))

# ---------- TEST 3: AKTIF GONDERININ LIFETIME POST INSIGHT'I ----------
print('=== TEST 3: 20 Mart gonderisi lifetime post insight ===')
POST = '233229654211_1528479829277240'
for metric in ['post_impressions', 'post_media_view', 'post_activity', 'post_clicks', 'post_reactions_by_type_total']:
    r = get(POST + '/insights/' + metric, {'period': 'lifetime'})
    if '__exc' in r:
        print(metric, 'exc'); continue
    if 'error' in r:
        print(metric, 'ERR', str(r['error'].get('message'))[:55]); continue
    d = r.get('data', [])
    if not d:
        print(metric, 'EMPTY-ARRAY'); continue
    print(metric, 'DATA', json.dumps(d[0].get('values', d[0].get('total_value')))[:130])
print('=== PROBE v3 DONE ===')
