"""شعار الجهة أعلى النموذج، ومعاينة الرابط عند مشاركته (og:image بمقاس 1200×630)."""
import io

from PIL import Image

from conftest import make_form
from models import AppSetting, Form, MediaFile, db

Q = [{'id': 'a', 'type': 'short_text', 'title': 'الاسم', 'required': False}]


def _png(w, h, color=(200, 30, 30)):
    out = io.BytesIO()
    Image.new('RGB', (w, h), color).save(out, 'PNG')
    return out.getvalue()


def _upload(admin, fid, data, kind='image'):
    r = admin.post('/admin/api/media', data={'file': (io.BytesIO(data), 'x.png', 'image/png'), 'kind': kind, 'form_id': str(fid)},
                   content_type='multipart/form-data')
    assert r.json['ok'], r.data
    return r.json['url']


def _set_org_logo(app, data):
    with app.app_context():
        m = MediaFile(kind='logo', filename='logo.png', mime='image/png', size=len(data), data=data)
        db.session.add(m)
        db.session.commit()
        AppSetting.set('org_logo_id', str(m.id))
        AppSetting.set('org_name_ar', 'مدرسة التجربة')
        db.session.commit()
        return m.url


def test_link_preview_tags_and_branded_card(admin, app):
    app.config['BASE_URL'] = 'https://9.iajaward.org'
    fid, slug, _ = make_form(admin, app, Q, title='استبيان رضا أولياء الأمور')
    admin.post(f'/admin/api/forms/{fid}', json={'description': 'سطر أول\nسطر ثانٍ', 'settings': {'lang': 'ar', 'accent': '#0f766e'}})
    page = app.test_client().get(f'/f/{slug}').data.decode()
    assert '<meta property="og:title" content="استبيان رضا أولياء الأمور">' in page
    assert '<meta property="og:description" content="سطر أول سطر ثانٍ">' in page
    assert f'content="https://9.iajaward.org/f/{slug}/share.jpg?v=' in page
    assert 'summary_large_image' in page
    r = app.test_client().get(f'/f/{slug}/share.jpg')
    assert r.status_code == 200 and r.mimetype == 'image/jpeg'
    img = Image.open(io.BytesIO(r.data))
    assert img.size == (1200, 630) and len(r.data) < 300_000
    assert img.getpixel((5, 5))[1] > img.getpixel((5, 5))[0]      # لون النموذج (أخضر مزرق) لا الأزرق الافتراضي


def test_share_image_uses_header_then_share_image(admin, app):
    fid, slug, _ = make_form(admin, app, Q)
    header = _upload(admin, fid, _png(1600, 400, (10, 200, 10)))
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'lang': 'ar', 'header_image': header}})
    px = Image.open(io.BytesIO(app.test_client().get(f'/f/{slug}/share.jpg').data)).getpixel((600, 315))
    assert px[1] > 180 and px[0] < 60                                 # صورة الترويسة مقصوصة لتملأ المقاس
    share = _upload(admin, fid, _png(1200, 630, (20, 20, 220)))
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'lang': 'ar', 'header_image': header, 'share_image': share}})
    px = Image.open(io.BytesIO(app.test_client().get(f'/f/{slug}/share.jpg').data)).getpixel((600, 315))
    assert px[2] > 180 and px[1] < 60                                 # صورة المعاينة لها الأولوية


def test_org_logo_on_form_and_thank_you_page(admin, app):
    logo = _set_org_logo(app, _png(120, 120))
    fid, slug, _ = make_form(admin, app, Q)
    c = app.test_client()
    page = c.get(f'/f/{slug}').data.decode()
    assert 'class="f-brand' in page and f'src="{logo}"' in page and 'مدرسة التجربة' in page
    # الإخفاء، وإظهار الشعار دون الاسم، وشعار خاص بالنموذج
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'lang': 'ar', 'org_name_hide': True, 'logo_size': 'lg', 'logo_align': 'center'}})
    page = c.get(f'/f/{slug}').data.decode()
    assert 'f-brand center sz-lg' in page and 'مدرسة التجربة</span>' not in page
    own = _upload(admin, fid, _png(80, 80, (0, 0, 0)))
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'lang': 'ar', 'logo': own}})
    assert f'src="{own}"' in c.get(f'/f/{slug}').data.decode()
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'lang': 'ar', 'logo_hide': True}})
    assert 'class="f-brand' not in c.get(f'/f/{slug}').data.decode()


def test_media_settings_accept_only_safe_links(admin, app):
    fid, slug, _ = make_form(admin, app, Q, settings={'logo': 'javascript:alert(1)', 'share_image': 'https://example.com/a.jpg',
                                                    'logo_size': 'huge'})
    with app.app_context():
        f = db.session.get(Form, fid)
        assert f.s('logo') == '' and f.s('share_image') == 'https://example.com/a.jpg' and f.s('logo_size') == ''
