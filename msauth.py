"""الدخول بحساب Microsoft للمدرسة (Microsoft Entra / Tenant) للنماذج التي تتطلب الدخول.

يستخدم تسجيل التطبيق نفسه الذي تستخدمه الأنظمة الأخرى للبريد (قيم MS_* في .env). يلزم مرة واحدة في بوابة Azure:
  • Authentication ← Web ← Redirect URI:  <BASE_URL>/auth/ms/callback   (مثل https://9.iajaward.org/auth/ms/callback)
  • API permissions ← Microsoft Graph ← Delegated: openid, profile, email, User.Read  (ثم Grant admin consent)

المسار: authorization code + PKCE ← تبادل الرمز على الخادم بسرّ التطبيق ← قراءة الحساب من Graph (/me).
لا يُقبل البريد إلا من Graph نفسها عبر اتصال آمن، فلا حاجة لفك رموز JWT.
"""
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests
from flask import current_app, request

SCOPE = 'openid profile email User.Read'


def ready():
    c = current_app.config
    return bool(c.get('MS_TENANT_ID') and c.get('MS_CLIENT_ID') and c.get('MS_CLIENT_SECRET'))


def redirect_uri():
    base = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    return base.rstrip('/') + '/auth/ms/callback'


def start(domain_hint=''):
    """(رابط صفحة Microsoft، الحالة المحفوظة في الجلسة)"""
    c = current_app.config
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    q = {'client_id': c['MS_CLIENT_ID'], 'response_type': 'code', 'redirect_uri': redirect_uri(), 'response_mode': 'query',
         'scope': SCOPE, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'prompt': 'select_account'}
    if domain_hint:
        q['domain_hint'] = domain_hint
    url = f'https://login.microsoftonline.com/{c["MS_TENANT_ID"]}/oauth2/v2.0/authorize?' + urlencode(q)
    return url, {'state': state, 'verifier': verifier}


def finish(code, verifier):
    """يبادل الرمز ويقرأ الحساب: {'email', 'name'}؛ يرفع RuntimeError برسالة لا تحوي أسراراً."""
    c = current_app.config
    r = requests.post(f'https://login.microsoftonline.com/{c["MS_TENANT_ID"]}/oauth2/v2.0/token',
                      data={'client_id': c['MS_CLIENT_ID'], 'client_secret': c['MS_CLIENT_SECRET'], 'grant_type': 'authorization_code',
                            'code': code, 'redirect_uri': redirect_uri(), 'code_verifier': verifier, 'scope': SCOPE}, timeout=20)
    if r.status_code != 200:
        err = ''
        try:
            err = r.json().get('error', '')
        except ValueError:
            pass
        raise RuntimeError(f'token HTTP {r.status_code} {err}'.strip())
    token = r.json().get('access_token')
    me = requests.get('https://graph.microsoft.com/v1.0/me?$select=displayName,mail,userPrincipalName',
                      headers={'Authorization': f'Bearer {token}'}, timeout=20)
    if me.status_code != 200:
        raise RuntimeError(f'graph /me HTTP {me.status_code}')
    d = me.json()
    email = (d.get('mail') or d.get('userPrincipalName') or '').strip().lower()
    if '@' not in email:
        raise RuntimeError('no email on the account')
    return {'email': email, 'name': (d.get('displayName') or '').strip()}
