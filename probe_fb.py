import os, json, requests

# GECICI PROBE: FB sayfasi Graph API'den NE veriyor? (page node alanlari + insight metrikleri)
# Ana fetcher'a dokunmaz. META_PAGE_TOKEN (mevcut secret) ile calisir.

T = os.environ['META_PAGE_TOKEN'].strip()
P = os.environ.get('META_PAGE_ID', '233229654211').strip()
G = 'https://graph.facebook.com/v25.0/'


def get(path, params):
    q = dict(params); q['access_token'] = T
    try:
        return requests.get(G + path, params=q, timeout=60).json()
    except Exception as e:
        return {'__exc': repr(e)}


print('=== FB PAGE NODE FIELDS (insight API disi) ===')
fields = ('followers_count,fan_count,new_like_count,rating_count,overall_star_rating,'
          'talking_about_count,were_here_count,name,category,link,verification_status')
print(json.dumps(get(P, {'fields': fields}))[:1000])

print('=== FB INSIGHTS PROBE (metric x [day, total_value]) ===')
METRICS = [
    'page_impressions', 'page_impressions_unique', 'page_post_engagements', 'page_engaged_users',
    'page_views_total', 'page_fans', 'page_fan_adds', 'page_fan_adds_unique',
    'page_fan_removes', 'page_fan_removes_unique', 'page_daily_follows', 'page_daily_follows_unique',
    'page_daily_unfollows_unique', 'page_follows', 'page_actions_post_reactions_total',
    'page_total_actions', 'page_video_views', 'page_content_activity',
    'page_posts_impressions', 'page_posts_impressions_unique', 'page_cta_clicks_logged_in_total',
]
for m in METRICS:
    parts = [m]
    for tag, pt in [('day', {'period': 'day'}), ('tv', {'metric_type': 'total_value', 'period': 'day'})]:
        r = get(P + '/insights/' + m, pt)
        if '__exc' in r:
            parts.append(tag + ':exc'); continue
        if 'error' in r:
            parts.append(tag + ':ERR ' + str(r['error'].get('message', ''))[:40]); continue
        d = r.get('data', [])
        if not d:
            parts.append(tag + ':empty'); continue
        payload = d[0].get('values')
        if payload is None:
            payload = d[0].get('total_value')
        parts.append(tag + ':' + json.dumps(payload)[:80])
    print(' || '.join(parts))
print('=== PROBE DONE ===')
