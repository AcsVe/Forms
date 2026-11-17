"""اشتراك النسخة المستضافة (license.py): الحالات، وما يتوقف وما يبقى مفتوحاً بعد الإيقاف، والربط بالملف المشترك."""
import json
from datetime import timedelta

import pytest

import license as L
from conftest import make_form

KEYS = ('LICENSE_UNTIL', 'LICENSE_WARN_DAYS', 'LICENSE_GRACE_DAYS', 'LICENSE_CONTACT', 'LICENSE_FILE', 'LICENSE_ID')
Q = [{'id': 'q1', 'type': 'short_text', 'title': 'الاسم', 'required': False}]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def until(monkeypatch, days, **env):
    monkeypatch.setenv('LICENSE_UNTIL', (L._today() + timedelta(days=days)).isoformat())
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_without_a_date_nothing_changes(admin):
    assert L.status()['state'] == 'none'
    assert 'license-alert' not in admin.get('/admin/settings').data.decode()


def test_states_follow_the_dates(monkeypatch):
    until(monkeypatch, 100); assert L.status()['state'] == 'ok'
    until(monkeypatch, 10); assert L.status()['state'] == 'warn'
    until(monkeypatch, -3); assert L.status()['state'] == 'grace'
    until(monkeypatch, -9); assert L.status()['state'] == 'expired'
    until(monkeypatch, -3, LICENSE_GRACE_DAYS='1'); assert L.status()['state'] == 'expired'


def test_invalid_date_is_ignored(monkeypatch):
    monkeypatch.setenv('LICENSE_UNTIL', 'not-a-date')
    assert L.status()['state'] == 'none'


def test_banner_before_the_end_and_in_the_grace(admin, monkeypatch):
    until(monkeypatch, 10, LICENSE_CONTACT='0790000000')
    page = admin.get('/admin/settings').data.decode()
    assert 'license-alert' in page and '0790000000' in page
    until(monkeypatch, -3)
    assert 'license-alert' in admin.get('/admin/settings').data.decode()


def test_expired_pauses_admin_and_public_forms_but_keeps_sign_in_open(app, admin, monkeypatch):
    fid, slug, _ = make_form(admin, app, Q)
    until(monkeypatch, -9, LICENSE_CONTACT='0790000000')
    r = admin.get('/admin/settings')
    assert r.status_code == 403 and '0790000000' in r.data.decode()
    assert app.test_client().get(f'/f/{slug}').status_code == 403
    assert admin.post('/admin/forms/new', data={'title': 'x'}).status_code == 403
    assert app.test_client().get('/admin/login').status_code == 200
    assert app.test_client().get('/admin/forgot').status_code == 200
    assert app.test_client().get('/healthz').status_code == 200
    until(monkeypatch, 100)
    assert app.test_client().get(f'/f/{slug}').status_code == 200          # التجديد يعيد كل شيء فوراً


def test_locked_page_speaks_english_on_request(app, monkeypatch):
    until(monkeypatch, -9)
    assert 'The subscription for this system has ended' in app.test_client().get('/admin/?lang=en').data.decode()


def test_shared_file_wins_over_env_and_applies_without_a_restart(app, admin, monkeypatch, tmp_path):
    f = tmp_path / 'licenses.json'
    monkeypatch.setenv('LICENSE_FILE', str(f)); monkeypatch.setenv('LICENSE_ID', 'rasf')
    assert L.status()['state'] == 'none'                                      # الملف مفقود: يرجع إلى .env
    f.write_text(json.dumps({'rasf': {'until': (L._today() - timedelta(days=9)).isoformat(), 'contact': 'c-1'}}))
    assert L.status()['state'] == 'expired' and L.status()['contact'] == 'c-1'
    assert admin.get('/admin/settings').status_code == 403
    f.write_text(json.dumps({'rasf': {'until': (L._today() + timedelta(days=100)).isoformat()}}))
    assert L.status()['state'] == 'ok' and admin.get('/admin/settings').status_code == 200
    f.write_text(json.dumps({'other': {'until': '2020-01-01'}}))
    assert L.status()['state'] == 'none'                                      # مدخل نظام آخر لا يؤثر
    monkeypatch.setenv('LICENSE_UNTIL', '2020-01-01')
    assert L.status()['state'] == 'none'                                      # الملف أقوى من .env
    f.write_text('{not json')
    assert L.status()['state'] == 'expired'                                   # ملف تالف: يرجع إلى .env ولا ينهار
