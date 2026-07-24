import os, json, requests

# SURVIVOR PROBE — Meta'nin deprecated-metrics dokumaninin "AYAKTA" dedigi metrikler
# bu sayfa (New Pages Experience) icin gercekten veri donuyor mu?
# KARAR METRIGI: page_media_view (page_impressions yerine gecen gorunum/erisim).
# Ana fetcher'a dokunmaz. Mevcut META_PAGE_TOKEN secret'i ile calisir.

T = os.environ['META_PAGE_TOKEN'].strip()
P = os.environ.get('META_PAGE_ID', '233229654211').strip()
G = 'https://graph.facebook.com/v25.0/'


def get(path, params):
    q = dict(params); q['access_token'] = T
    try:
        return requests.get(G + path, params=q, timeout=60).json()
    except Exception as e:
        return {'__exc': repr(e)}


def show(node, metric, params, tag):
    r = get(node + '/insights/' + metric, params)
    if '__exc' in r:
        return tag + ':exc ' + r['__exc'][:40]
    if 'error' in r:
        return tag + ':ERR ' + str(r['error'].get('message', ''))[:55]
    d = r.get('data', [])
    if not d:
        return tag + ':EMPTY'
    row = d[0]
    val = row.get('total_value', row.get('values'))
    return tag + ':DATA ' + json.dumps(val)[:130]


print('=== SURVIVOR PROBE (page-level, dokumante ayakta metrikler) ===')
PAGE = [
    ('page_media_view',              {'metric_type': 'total_value', 'period': 'day'},     'media_view/tv-day'),
    ('page_media_view',              {'metric_type': 'total_value', 'period': 'days_28'}, 'media_view/tv-28'),
    ('page_total_media_view_unique', {'metric_type': 'total_value', 'period': 'day'},     'media_view_unq/tv-day'),
    ('page_total_media_view_unique', {'metric_type': 'total_value', 'period': 'days_28'}, 'media_view_unq/tv-28'),
    ('page_follows',                 {'period': 'day'},                                   'follows/day'),
    ('page_daily_follows_unique',    {'period': 'day'},                                   'd_follows_unq/day'),
    ('page_daily_unfollows_unique',  {'period': 'day'},                                   'd_unfollows_unq/day'),
    ('page_post_engagements',        {'metric_type': 'total_value', 'period': 'day'},     'post_eng/tv-day'),
    ('page_video_views',             {'metric_type': 'total_value', 'period': 'day'},     'video_views/tv-day'),
]
for metric, params, tag in PAGE:
    print(metric.ljust(30), show(P, metric, params, tag))

print('=== POST-LEVEL (post_media_view, son 3 gonderi) ===')
posts = get(P + '/posts', {'fields': 'id,created_time', 'limit': 3})
if 'error' in posts:
    print('posts err', str(posts['error'].get('message'))[:60])
else:
    pl = posts.get('data', [])
    print('post sayisi:', len(pl))
    for i, pst in enumerate(pl[:3]):
        pid = pst['id']; ct = pst.get('created_time', '')[:10]
        print(pid, ct, show(pid, 'post_media_view', {'metric_type': 'total_value', 'period': 'day'}, 'pmv/tv-day'))
        if i == 0:
            print(pid, ct, show(pid, 'post_media_view', {'period': 'lifetime'}, 'pmv/lifetime'))
print('=== SURVIVOR PROBE DONE ===')
