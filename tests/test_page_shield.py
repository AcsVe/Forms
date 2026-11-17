"""حماية مصدر الصفحات: لوحة الإدارة مشفّرة، وصفحات النماذج العامة والملفات تبقى كما هي."""
import pytest


@pytest.fixture
def shielded(app):
    app.config['PAGE_SHIELD'] = True        # الحماية معطّلة افتراضياً في وضع الاختبار
    return app


def test_admin_pages_are_encoded(shielded):
    r = shielded.test_client().get('/admin/login')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert '<title>' not in body and 'form' not in body.split('<script>')[0]
    assert 'atob' in body                    # سطر الفك الصغير فقط
    assert r.headers['Cache-Control'] == 'no-store'


def test_public_pages_stay_readable(shielded, admin):
    from conftest import make_form
    _fid, slug, _q = make_form(admin, shielded, [{'id': 'q1', 'type': 'short', 'title': 'الاسم'}])
    body = shielded.test_client().get(f'/f/{slug}').get_data(as_text=True)
    assert '<title>' in body and 'atob' not in body and 'fill.js' in body


def test_json_is_untouched(shielded, admin):
    r = admin.get('/healthz')
    assert r.status_code == 200 and 'atob' not in r.get_data(as_text=True)
