"""المنطقة التقريبية من عنوان الشبكة: تُحفظ مع الإجابة وتظهر في التصدير، ولا يتعطل شيء بلا قاعدة."""
import geo
from conftest import make_form, submit
from models import Response

Q = [{'id': 'n', 'type': 'short', 'title': 'الاسم'}]


def test_lookup_without_database_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    assert geo.lookup('188.123.180.129') == {}
    assert geo.lookup('127.0.0.1') == {} and geo.lookup('192.168.1.5') == {} and geo.lookup('not-an-ip') == {}
    assert len(geo._months()) == 2


def test_region_saved_and_exported(admin, app, monkeypatch):
    monkeypatch.setattr(geo, 'lookup', lambda ip: {'en': 'Amman, Jordan', 'ar': 'عمّان، الأردن', 'cc': 'JO'})
    fid, slug, _ = make_form(admin, app, Q)
    assert submit(app.test_client(), slug, {'n': 'أ'}).json['ok']
    with app.app_context():
        r = Response.query.one()
        assert r.meta['region'] == 'Amman, Jordan' and r.meta['region_ar'] == 'عمّان، الأردن' and r.meta['country_code'] == 'JO'
        rid = r.id
    csv = admin.get(f'/admin/forms/{fid}/export.csv').data.decode('utf-8-sig')
    assert 'المنطقة التقريبية' in csv.splitlines()[0] and 'عمّان، الأردن' in csv
    page = admin.get(f'/admin/responses/{rid}').data.decode()
    assert 'عمّان، الأردن' in page


def test_no_region_when_lookup_fails(admin, app, monkeypatch):
    monkeypatch.setattr(geo, 'lookup', lambda ip: {})
    _, slug, _ = make_form(admin, app, Q)
    assert submit(app.test_client(), slug, {'n': 'أ'}).json['ok']
    with app.app_context():
        assert 'region' not in Response.query.one().meta
