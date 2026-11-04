import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('FORMS_DB_PATH', str(tmp_path / 'forms.db'))
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.delenv('DATABASE_URL', raising=False)
    from app import create_app
    app = create_app({'TESTING': True, 'MAIL_BACKEND': 'memory', 'MAIL_OUTBOX': [],
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/forms.db'})
    # حدود السرعة في الذاكرة تُصفَّر بين الاختبارات
    from blueprints import admin, public
    admin._LOGIN_FAILS.clear()
    public._RATE.clear()
    yield app


@pytest.fixture
def admin(app):
    c = app.test_client()
    r = c.post('/admin/login', data={'username': 'admin', 'password': 'admin'})
    assert r.status_code == 302
    return c


def make_form(admin, app, questions, settings=None, status='open', title='نموذج تجربة'):
    r = admin.post('/admin/forms/new', data={'title': title})
    fid = int(r.headers['Location'].rstrip('/').split('/')[-2])
    body = {'schema': {'questions': questions}, 'settings': dict({'lang': 'ar'}, **(settings or {})), 'status': status}
    r = admin.post(f'/admin/api/forms/{fid}', json=body)
    assert r.status_code == 200 and r.json['ok'], r.data
    from models import Form, db
    with app.app_context():
        f = db.session.get(Form, fid)
        return fid, f.slug, f.questions


def submit(client, slug, answers, files=None, preview=False, ua='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1', **extra):
    import json
    client.get(f'/f/{slug}' + ('?preview=1' if preview else ''), headers={'User-Agent': ua})
    data = {'payload': json.dumps(dict({'answers': answers, 'meta': {'screen': '390x844', 'tz': 'Asia/Amman'}}, **extra))}
    if files:
        data.update(files)
    return client.post(f'/f/{slug}/submit' + ('?preview=1' if preview else ''), data=data, headers={'User-Agent': ua},
                       content_type='multipart/form-data')
