"""طراز الجهاز وإصدار النظام: من تلميح المتصفح أو من User-Agent، ويظهران في التصدير."""
import json

import uaparse
from conftest import make_form
from models import Response

Q = [{'id': 'n', 'type': 'short', 'title': 'الاسم'}]
WIN = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
ANDROID_OLD = 'Mozilla/5.0 (Linux; Android 13; SM-A546E Build/TP1A.220624.014) AppleWebKit/537.36 Chrome/110.0 Mobile Safari/537.36'
ANDROID_REDUCED = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36'
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1'


def test_model_parsing():
    assert uaparse.model(ANDROID_OLD) == 'SM-A546E'
    assert uaparse.model(ANDROID_REDUCED) == ''               # Chrome الحديث يخفي الطراز في User-Agent
    assert uaparse.model(ANDROID_REDUCED, 'Pixel 8') == 'Pixel 8'
    assert uaparse.model(IPHONE) == 'iPhone'
    assert uaparse.model(WIN) == ''
    assert uaparse.os_version(WIN, 'Windows', '15.0.0') == '11'
    assert uaparse.os_version(WIN, 'Windows', '10.0.0') == '10'
    assert uaparse.os_version(WIN, 'Windows') == ''           # لا يُخمَّن بين 10 و11
    assert uaparse.os_version(IPHONE, 'iOS') == '17.4'
    assert uaparse.os_version(ANDROID_REDUCED, 'Android', '14.0.0') == '14'


def _send(app, slug, ua, meta):
    c = app.test_client()
    c.get(f'/f/{slug}', headers={'User-Agent': ua})
    r = c.post(f'/f/{slug}/submit', data={'payload': json.dumps({'answers': {'n': 'أ'}, 'meta': meta})},
               headers={'User-Agent': ua}, content_type='multipart/form-data')
    assert r.status_code == 200 and r.json['ok'], r.data


def test_model_saved_and_exported(admin, app):
    fid, slug, _ = make_form(admin, app, Q)
    _send(app, slug, ANDROID_REDUCED, {'screen': '412x915', 'model': 'Pixel 8', 'os_version': '14.0.0'})
    _send(app, slug, WIN, {'screen': '1366x768', 'model': '', 'os_version': '15.0.0'})
    with app.app_context():
        rs = Response.query.order_by(Response.id).all()
        assert rs[0].meta['model'] == 'Pixel 8' and rs[0].meta['os_version'] == '14'
        assert 'model' not in rs[1].meta and rs[1].meta['os_version'] == '11'
    csv = admin.get(f'/admin/forms/{fid}/export.csv').data.decode('utf-8-sig')
    lines = csv.splitlines()
    assert 'طراز الجهاز' in lines[0]
    assert any('Pixel 8' in x and 'Android 14' in x for x in lines[1:])
    assert any('Windows 11' in x for x in lines[1:])
