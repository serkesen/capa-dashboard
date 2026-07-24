import os, datetime as dt, requests

# Instagram (Instagram Login / graph.instagram.com) — bagimsiz IG User token.
# TOKEN YONETIMI: app_config (Supabase) oncelikli; yoksa env META_IG_TOKEN bootstrap edilir.
# 60 gunluk token ~20 gunde bir OTOMATIK yenilenir (refresh_access_token) -> elle bakim YOK.
# Not: secret elle degistirilirse app_config'teki 'meta_ig_token' satirini SIL (yeniden bootstrap).
# fetch.py'dan AYRI calisir; fail-soft: IG hatasi pipeline'i (GSC/GA4/FB) bozmaz.

SB_URL = os.environ['SUPABASE_URL'].rstrip('/')
SB_KEY = os.environ['SUPABASE_SERVICE_KEY']
ENV_TOKEN = os.environ.get('META_IG_TOKEN', '').strip()
IG = 'https://graph.instagram.com/'
end = dt.date.today().isoformat()
SBH = {'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY}
TOKEN_KEY = 'meta_ig_token'
REFRESH_AFTER_DAYS = 20


def upsert(table, rows, conflict):
    r = requests.post(SB_URL + '/rest/v1/' + table + '?on_conflict=' + conflict,
                      headers={**SBH, 'Content-Type': 'application/json',
                               'Prefer': 'resolution=merge-duplicates'},
                      json=rows, timeout=60)
    r.raise_for_status()
    print('upsert', table, len(rows))


def cfg_get(key):
    r = requests.get(SB_URL + '/rest/v1/app_config', headers=SBH,
                     params={'key': 'eq.' + key, 'select': 'val,updated_at'}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return (d[0]['val'], d[0]['updated_at']) if d else (None, None)


def cfg_set(key, val):
    r = requests.post(SB_URL + '/rest/v1/app_config?on_conflict=key',
                      headers={**SBH, 'Content-Type': 'application/json',
                               'Prefer': 'resolution=merge-duplicates'},
                      json=[{'key': key, 'val': val,
                             'updated_at': dt.datetime.now(dt.timezone.utc).isoformat()}],
                      timeout=30)
    r.raise_for_status()


def get_ig_token():
    try:
        stored, updated_at = cfg_get(TOKEN_KEY)
    except Exception as e:
        print('IG cfg_get err (env fallback)', repr(e)[:80])
        return ENV_TOKEN
    if not stored:
        if ENV_TOKEN:
            try:
                cfg_set(TOKEN_KEY, ENV_TOKEN)
                print('IG token bootstrap: env -> app_config')
            except Exception as e:
                print('IG cfg_set bootstrap err', repr(e)[:80])
        return ENV_TOKEN
    try:
        ua = dt.datetime.fromisoformat(str(updated_at).replace('Z', '+00:00'))
        age = (dt.datetime.now(dt.timezone.utc) - ua).days
    except Exception:
        age = 0
    if age >= REFRESH_AFTER_DAYS:
        try:
            rr = requests.get(IG + 'refresh_access_token',
                              params={'grant_type': 'ig_refresh_token', 'access_token': stored},
                              timeout=60).json()
            new = rr.get('access_token')
            if new:
                cfg_set(TOKEN_KEY, new)
                print('IG token refreshed (age', age, 'gun)')
                return new
            print('IG refresh no token:', str(rr.get('error', ''))[:80])
        except Exception as e:
            print('IG refresh err', repr(e)[:80])
    return stored


IG_TOKEN = get_ig_token()
if not IG_TOKEN:
    print('IG skip (token yok)')
    raise SystemExit(0)

# 1) Hesap temel bilgisi (takipci)
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

# 3) Yaz (fail-soft: kolon uyusmazliginda takipci-only fallback)
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
