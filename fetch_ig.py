import os, datetime as dt, requests

# Instagram (Instagram Login / graph.instagram.com) — bagimsiz IG User token.
# fetch.py'dan AYRI calisir; onun FB/GSC/GA4 akisina dokunmaz.
# META_IG_TOKEN yoksa sessizce cikar. Fail-soft: hata fetcher'i bozmaz.

SB_URL = os.environ['SUPABASE_URL'].rstrip('/')
SB_KEY = os.environ['SUPABASE_SERVICE_KEY']
IG_TOKEN = os.environ.get('META_IG_TOKEN', '').strip()
IG = 'https://graph.instagram.com/'
end = dt.date.today().isoformat()


def upsert(table, rows, conflict):
    r = requests.post(SB_URL + '/rest/v1/' + table + '?on_conflict=' + conflict,
                      headers={'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY,
                               'Content-Type': 'application/json',
                               'Prefer': 'resolution=merge-duplicates'},
                      json=rows, timeout=60)
    r.raise_for_status()
    print('upsert', table, len(rows))


if not IG_TOKEN:
    print('IG skip (META_IG_TOKEN yok)')
    raise SystemExit(0)

# 1) Hesap temel bilgisi (takipci) — instagram_business_basic
me = requests.get(IG + 'me',
                  params={'fields': 'user_id,username,followers_count,media_count',
                          'access_token': IG_TOKEN}, timeout=60).json()
if 'error' in me:
    print('IG me error', str(me['error'].get('message'))[:140])
    raise SystemExit(0)

ig_id = str(me.get('user_id') or me.get('id') or '')
print('IG me OK', me.get('username'), 'followers', me.get('followers_count'),
      'media', me.get('media_count'), 'id', ig_id)

row = {'date': end, 'platform': 'instagram'}
if me.get('followers_count') is not None:
    row['followers'] = me['followers_count']

# 2) Account insights probe (fail-soft) — instagram_business_manage_insights
# Metrik adlari canli test icin; hata verirse o metrik atlanir, digerleri devam.
INSIGHTS = [
    ('reach', 'reach'),
    ('profile_views', 'profile_views'),
    ('accounts_engaged', 'engaged_accounts'),
    ('total_interactions', 'total_interactions'),
    ('likes', 'likes'),
    ('comments', 'comments'),
    ('shares', 'shares'),
    ('saves', 'saves'),
    ('views', 'views'),
]
if ig_id:
    for metric, col in INSIGHTS:
        try:
            ir = requests.get(IG + ig_id + '/insights',
                              params={'metric': metric, 'period': 'day',
                                      'metric_type': 'total_value',
                                      'access_token': IG_TOKEN}, timeout=60).json()
            if 'error' in ir:
                print('IG insight', metric, 'err', str(ir['error'].get('message'))[:70])
                continue
            data = ir.get('data', [])
            tv = data[0].get('total_value', {}).get('value') if data else None
            if isinstance(tv, (int, float)):
                row[col] = int(tv)
        except Exception as e:
            print('IG insight', metric, 'exc', repr(e))
    print('IG insights filled:',
          sorted(k for k in row if k not in ('date', 'platform', 'followers')))

# 3) Yaz. Once tam satiri dene; kolon uyusmazligi olursa takipci-only fallback.
if len(row) > 2 or 'followers' in row:
    try:
        upsert('meta_social_daily', [row], 'date,platform')
        print('IG upserted', {k: row[k] for k in row if k not in ('date', 'platform')})
    except Exception as e:
        print('IG full upsert failed, retry followers-only:', repr(e)[:140])
        base = {'date': end, 'platform': 'instagram'}
        if 'followers' in row:
            base['followers'] = row['followers']
            upsert('meta_social_daily', [base], 'date,platform')
            print('IG followers-only upserted', base.get('followers'))
else:
    print('IG no data to write')

print('IG OK')
