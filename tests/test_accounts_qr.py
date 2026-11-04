"""الدخول بحساب Microsoft، وقواعد دخول الإدارة، ورمز QR."""
import re
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import make_form, submit
from models import Form, PasswordReset, Response, User, db


class FakeResp:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


@pytest.fixture
def ms(app, monkeypatch):
    app.config.update(MS_TENANT_ID='tenant-x', MS_CLIENT_ID='client-x', MS_CLIENT_SECRET='secret-x', BASE_URL='https://9.iajaward.org')
    calls = {}

    def post(url, data=None, timeout=None, **kw):
        calls['token'] = (url, data)
        return FakeResp(200, {'access_token': 'AT'}) if data.get('code') == 'good' else FakeResp(400, {'error': 'invalid_grant'})

    def get(url, headers=None, timeout=None, **kw):
        calls['me'] = (url, headers)
        return FakeResp(200, {'displayName': 'منى سالم', 'mail': 'Mona@School.jo', 'userPrincipalName': 'mona@school.jo'})
    import msauth
    monkeypatch.setattr(msauth.requests, 'post', post)
    monkeypatch.setattr(msauth.requests, 'get', get)
    return calls


def test_microsoft_sign_in_flow(admin, app, ms):
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'أ', 'required': True}],
                             settings={'require_email': True, 'email_domains': 'school.jo', 'login_method': 'microsoft',
                                       'filler_fields': [{'key': 'name', 'label': 'الاسم', 'required': True}]})
    c = app.test_client()
    page = c.get(f'/f/{slug}/login').data.decode()
    assert 'الدخول بحساب Microsoft' in page and 'name="code"' not in page and 'type="email"' not in page
    assert c.post(f'/f/{slug}/login', data={'action': 'send', 'email': 'a@school.jo'}).status_code == 403
    r = c.get(f'/f/{slug}/login/microsoft')
    loc = urlparse(r.headers['Location'])
    q = parse_qs(loc.query)
    assert loc.netloc == 'login.microsoftonline.com' and loc.path == '/tenant-x/oauth2/v2.0/authorize'
    assert q['redirect_uri'] == ['https://9.iajaward.org/auth/ms/callback'] and q['code_challenge_method'] == ['S256']
    assert q['domain_hint'] == ['school.jo'] and 'User.Read' in q['scope'][0]
    state = q['state'][0]
    # حالة خاطئة تُرفض
    r = c.get('/auth/ms/callback?code=good&state=wrong')
    assert '/login' in r.headers['Location']
    c.get(f'/f/{slug}/login/microsoft')
    with c.session_transaction() as s:
        state = s['ms_oauth']['state']
    r = c.get(f'/auth/ms/callback?code=good&state={state}')
    assert r.headers['Location'].endswith(f'/f/{slug}')
    assert ms['token'][1]['client_secret'] == 'secret-x' and ms['token'][1]['code_verifier']
    # الاسم من الحساب يملأ خطوة بيانات المستجيب
    r = c.get(f'/f/{slug}/details')
    assert 'منى سالم' in r.data.decode()
    c.post(f'/f/{slug}/details', data={'f_name': 'منى سالم'})
    assert submit(c, slug, {'a': 'نعم'}).json['ok']
    with app.app_context():
        resp = Response.query.one()
        assert resp.email == 'mona@school.jo' and resp.filler['name'] == 'منى سالم'


def test_microsoft_sign_in_rejects_other_domain_and_bad_code(admin, app, ms, monkeypatch):
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'أ'}],
                             settings={'require_email': True, 'email_domains': 'other.jo'})
    c = app.test_client()
    page = c.get(f'/f/{slug}/login').data.decode()
    assert 'الدخول بحساب Microsoft' in page and 'type="email"' in page      # الطريقتان معاً
    c.get(f'/f/{slug}/login/microsoft')
    with c.session_transaction() as s:
        state = s['ms_oauth']['state']
    r = c.get(f'/auth/ms/callback?code=good&state={state}', follow_redirects=True)
    assert 'other.jo' in r.data.decode()
    assert c.get(f'/f/{slug}').status_code == 302
    c.get(f'/f/{slug}/login/microsoft')
    with c.session_transaction() as s:
        state = s['ms_oauth']['state']
    r = c.get(f'/auth/ms/callback?code=bad&state={state}', follow_redirects=True)
    assert 'تعذّر الدخول بحساب Microsoft' in r.data.decode() and 'secret-x' not in r.data.decode()


def test_microsoft_button_hidden_without_settings(admin, app):
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'أ'}], settings={'require_email': True})
    page = app.test_client().get(f'/f/{slug}/login').data.decode()
    assert 'الدخول بحساب Microsoft' not in page and 'type="email"' in page


def test_admin_login_by_email_lockout_reset_and_session_end(app):
    c = app.test_client()
    with app.app_context():
        u = User.query.filter_by(username='admin').one()
        u.email = 'Admin@School.jo'
        db.session.commit()
    assert c.post('/admin/login', data={'username': 'admin@school.jo', 'password': 'admin'}).status_code == 302
    other = app.test_client()
    other.post('/admin/login', data={'username': 'admin', 'password': 'admin'})
    assert other.get('/admin/').status_code == 200
    # تغيير كلمة المرور يُخرج الجلسة الأخرى ويُبقي الحالية
    c.post('/admin/account', data={'current': 'admin', 'new': 'newpass123', 'again': 'newpass123'})
    assert c.get('/admin/').status_code == 200
    assert other.get('/admin/').status_code == 302
    # نسيت كلمة المرور: رابط بالبريد صالح لمرة واحدة
    app.config['MAIL_OUTBOX'].clear()
    app.test_client().post('/admin/forgot', data={'username': 'admin'})
    link = re.search(r'href="https?://[^/]+(/admin/reset/[^"]+)"', app.config['MAIL_OUTBOX'][-1]['html']).group(1)
    t = app.test_client()
    t.post(link, data={'new': 'reset1234', 'again': 'reset1234'})
    assert t.post('/admin/login', data={'username': 'admin', 'password': 'reset1234'}).status_code == 302
    assert 'غير صالح' in t.get(link, follow_redirects=True).data.decode()
    with app.app_context():
        assert PasswordReset.query.one().used
    # عشر محاولات خاطئة توقف الدخول من الجهاز
    bad = app.test_client()
    for _ in range(10):
        bad.post('/admin/login', data={'username': 'admin', 'password': 'x'})
    r = bad.post('/admin/login', data={'username': 'admin', 'password': 'reset1234'})
    assert r.status_code == 200 and 'خمس عشرة دقيقة' in r.data.decode()


def test_qr_has_logo_caption_and_follows_copies(admin, app):
    admin.post('/admin/settings', data={'org_name_ar': 'مدرسة الأمل', 'org_name_en': 'Al Amal School', 'accent': '#0C67EC'})
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'أ'}], title='استبيان المكتبة')
    svg = admin.get(f'/admin/forms/{fid}/qr.svg').data.decode()
    assert svg.startswith('<svg') and '<image' in svg and 'data:image/svg+xml;base64,' in svg
    assert 'مدرسة الأمل' in svg and 'استبيان المكتبة' in svg and f'/f/{slug}' in svg
    plain = admin.get(f'/admin/forms/{fid}/qr.svg?plain=1').data.decode()
    assert 'مدرسة الأمل' not in plain and '<image' in plain
    assert 'attachment' in admin.get(f'/admin/forms/{fid}/qr.svg?download=1').headers['Content-Disposition']
    assert app.test_client().get(f'/f/{slug}/qr.svg').status_code == 200
    page = admin.get(f'/admin/forms/{fid}/qr/print').data.decode()
    assert f'/admin/forms/{fid}/qr.svg' in page
    r = admin.post(f'/admin/forms/{fid}/duplicate')
    cid = int(r.headers['Location'].split('/')[-2])
    with app.app_context():
        cslug = db.session.get(Form, cid).slug
    assert cslug != slug and f'/f/{cslug}' in admin.get(f'/admin/forms/{cid}/qr.svg').data.decode()


def test_qr_matrix_decodes_back_to_the_link():
    """يتحقق أن الرمز المرسوم (بالشعار في وسطه) يطابق مصفوفة segno للرابط نفسه خارج مربع الشعار."""
    import segno
    import qr
    url = 'https://9.iajaward.org/f/abc123'
    s = qr.svg(url, logo='data:image/png;base64,AA==', caption=False)
    m = [list(r) for r in segno.make(url, error='h').matrix]
    assert len(re.findall(r'M\d+,\d+h\d+v10h-\d+z', s)) == sum(1 for row in m for i, v in enumerate(row) if v and (i == 0 or not row[i - 1]))
    n = len(m) + 8
    covered = (0.22 * n) ** 2 / (len(m) ** 2)
    assert covered < 0.08          # الشعار يغطي أقل من 8% والتصحيح H يتحمّل نحو 30%
