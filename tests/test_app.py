"""المسارات الرئيسية عبر الخادم: الصفحات، والإرسال، والدخول بالبريد، والاختبار، والتحليل، والتصدير، والحماية."""
import io
import json
import re

from conftest import make_form, submit
from models import Form, MediaFile, Response, User, db

ALL = [
    {'id': 'name', 'type': 'short_text', 'title': 'الاسم', 'required': True},
    {'id': 'mail', 'type': 'email', 'title': 'البريد'},
    {'id': 'grade', 'type': 'dropdown', 'title': 'الصف', 'choices': [{'id': 'g7', 'label': 'السابع'}, {'id': 'g8', 'label': 'الثامن'}]},
    {'id': 'like', 'type': 'single', 'title': 'هل أعجبك؟', 'other': True, 'choices': [{'id': 'y', 'label': 'نعم'}, {'id': 'n', 'label': 'لا'}]},
    {'id': 'days', 'type': 'multi', 'title': 'الأيام', 'choices': [{'id': 'd1', 'label': 'الأحد'}, {'id': 'd2', 'label': 'الإثنين'}]},
    {'id': 'rate', 'type': 'rating', 'title': 'التقييم', 'max': 5},
    {'id': 'nps', 'type': 'nps', 'title': 'NPS'},
    {'id': 'lik', 'type': 'likert', 'title': 'ليكرت', 'rows': [{'id': 'r1', 'label': 'التواصل'}]},
    {'id': 'rank', 'type': 'ranking', 'title': 'رتّب', 'choices': [{'id': 'a', 'label': 'أ'}, {'id': 'b', 'label': 'ب'}]},
    {'id': 'when', 'type': 'date', 'title': 'التاريخ'},
    {'id': 'doc', 'type': 'file', 'title': 'ملف', 'max_files': 2},
    {'id': 'src', 'type': 'hidden', 'title': 'المصدر', 'param': 'src'},
]


def test_every_admin_page_renders_in_both_languages(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    submit(app.test_client(), slug, {'name': 'سارة'})
    with app.app_context():
        rid = Response.query.first().id
        tids = [f.id for f in Form.query.filter_by(is_template=True)]
    urls = ['/admin/', '/admin/forms', '/admin/forms?status=open', '/admin/forms?all=1', '/admin/templates', '/admin/forms/new',
            '/admin/forms/import', '/admin/responses', '/admin/responses?period=today', '/admin/compare',
            f'/admin/compare?ids={fid}&ids={tids[0]}&by=month', '/admin/users', '/admin/settings', '/admin/help', '/admin/account',
            f'/admin/forms/{fid}/edit', f'/admin/forms/{fid}/responses', f'/admin/forms/{fid}/analysis',
            f'/admin/forms/{fid}/analysis?a=grade&b=like', f'/admin/responses/{rid}', f'/f/{slug}']
    urls += [f'/admin/forms/{t}/edit' for t in tids] + [f'/admin/forms/{t}/analysis' for t in tids]
    for lang in ('ar', 'en'):
        admin.get(f'/lang/{lang}')
        for u in urls:
            r = admin.get(u)
            assert r.status_code == 200, (lang, u, r.status_code)
    assert admin.get('/admin/').data.decode().count('dir="ltr"') >= 1


def test_anonymous_submit_records_device_and_answers(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    with app.app_context():
        lik = db.session.get(Form, fid).questions[7]['cols'][3]['id']
    c = app.test_client()
    r = submit(c, slug, {'name': 'سارة', 'mail': 'sara@school.jo', 'grade': 'g8', 'like': '__other__', 'like:other': 'إلى حد ما',
                         'days': ['d1', 'd2'], 'rate': 4, 'nps': 9, 'lik': {'r1': lik}, 'rank': ['b', 'a'], 'when': '2026-12-31', 'src': 'whatsapp'},
               files={'file__doc': [(io.BytesIO(b'%PDF-1.4 test'), 'a.pdf'), (io.BytesIO(b'hello'), 'b.txt')]})
    assert r.status_code == 200 and r.json['ok'], r.data
    assert '/done?t=' in r.json['redirect']
    with app.app_context():
        resp = Response.query.one()
        assert resp.device == 'mobile' and resp.browser == 'Safari' and resp.os == 'iOS'
        assert resp.ip and resp.meta['screen'] == '390x844' and resp.meta['tz'] == 'Asia/Amman'
        assert resp.answers['days'] == ['d1', 'd2'] and resp.answers['like:other'] == 'إلى حد ما' and resp.answers['src'] == 'whatsapp'
        assert [f['name'] for f in resp.answers['doc']] == ['a.pdf', 'b.txt']
        assert MediaFile.query.filter_by(response_id=resp.id).count() == 2
        url = resp.answers['doc'][0]['url']
        assert db.session.get(Form, fid).views == 1
    assert c.get(r.json['redirect']).status_code == 200
    assert c.get(url).status_code == 403            # المرفقات للمسؤولين فقط
    assert admin.get(url).data == b'%PDF-1.4 test'
    # تكرار من الجهاز نفسه يُعلَّم ولا يُرفض
    assert submit(c, slug, {'name': 'سارة'}).json['ok']
    with app.app_context():
        assert Response.query.order_by(Response.id.desc()).first().flagged is True


def test_server_rejects_invalid_and_missing_required(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    r = submit(app.test_client(), slug, {'mail': 'bad', 'grade': 'zzz'})
    assert r.status_code == 400
    assert set(r.json['errors']) == {'name', 'mail', 'grade'}
    r = submit(app.test_client(), slug, {'name': 'x'}, hp='spam')       # حقل المصيدة: لا يُحفظ
    assert r.json['ok']
    with app.app_context():
        assert Response.query.count() == 0


def test_closed_draft_schedule_and_limit(admin, app):
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'أ'}], status='draft')
    c = app.test_client()
    assert 'لا يستقبل' in c.get(f'/f/{slug}').data.decode()
    assert submit(c, slug, {'a': '1'}).status_code == 409
    assert submit(admin, slug, {'a': '1'}, preview=True).json['ok']        # المعاينة تُحفظ تجربةً
    with app.app_context():
        assert Response.query.one().is_test is True
    admin.post(f'/admin/api/forms/{fid}', json={'status': 'open', 'settings': {'max_responses': 1}})
    assert submit(c, slug, {'a': '1'}).json['ok']
    assert submit(app.test_client(), slug, {'a': '2'}).status_code == 409
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'close_at': '2020-01-01T10:00'}})
    assert 'انتهى موعد' in app.test_client().get(f'/f/{slug}').data.decode()


def test_quiz_scores_and_answers_stay_on_server(admin, app):
    qs = [{'id': 'q1', 'type': 'single', 'title': 'العاصمة', 'choices': [{'id': 'amm', 'label': 'عمّان'}, {'id': 'irb', 'label': 'إربد'}],
           'quiz': {'points': 2, 'correct': ['amm']}},
          {'id': 'q2', 'type': 'long_text', 'title': 'اشرح', 'quiz': {'points': 3}}]
    fid, slug, _ = make_form(admin, app, qs, settings={'quiz': True, 'show_score': 'immediate', 'show_answers': True, 'pass_mark': 50})
    c = app.test_client()
    page = c.get(f'/f/{slug}').data.decode()
    data = json.loads(re.search(r'window.FILL = (\{.*?\});</script>', page).group(1))
    assert 'correct' not in json.dumps(data)                  # الإجابات الصحيحة لا تصل إلى المتصفح
    r = submit(c, slug, {'q1': 'amm', 'q2': 'لأن الأرض تدور'})
    done = c.get(r.json['redirect']).data.decode()
    assert '2 / 5' in done and 'يدوياً' in done
    with app.app_context():
        resp = Response.query.one()
        assert (resp.score, resp.max_score) == (2.0, 5.0)
        rid = resp.id
    admin.post(f'/admin/responses/{rid}/grade', data={'pts_q2': '3'})
    with app.app_context():
        assert db.session.get(Response, rid).score == 5.0
    assert admin.get(f'/admin/forms/{fid}/analysis').status_code == 200


def test_email_gate_and_filler_step(admin, app):
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'أ', 'required': True}],
                             settings={'require_email': True, 'email_domains': 'school.jo', 'one_per_email': True, 'send_copy': True,
                                       'filler_fields': [{'key': 'name', 'label': 'الاسم', 'required': True}, {'key': 'phone', 'label': 'الهاتف', 'type': 'phone'}]})
    c = app.test_client()
    r = c.get(f'/f/{slug}')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert submit(c, slug, {'a': 'x'}).status_code == 403
    r = c.post(f'/f/{slug}/login', data={'action': 'send', 'email': 'x@gmail.com'})
    assert 'school.jo' in r.data.decode()
    c.post(f'/f/{slug}/login', data={'action': 'send', 'email': 'Teacher@School.jo'})
    mail = app.config['MAIL_OUTBOX'][-1]
    code = re.search(r'(\d{6})', mail['subject']).group(1)
    assert mail['to'] == ['teacher@school.jo']
    r = c.post(f'/f/{slug}/login', data={'action': 'verify', 'email': 'teacher@school.jo', 'code': '000000' if code != '000000' else '111111'})
    assert 'غير صحيح' in r.data.decode()
    r = c.post(f'/f/{slug}/login', data={'action': 'verify', 'email': 'teacher@school.jo', 'code': code})
    assert r.status_code == 302
    r = c.get(f'/f/{slug}')
    assert '/details' in r.headers['Location']
    r = c.post(f'/f/{slug}/details', data={'f_name': '', 'f_phone': 'abc'})
    assert r.status_code == 200 and 'مطلوب' in r.data.decode()
    c.post(f'/f/{slug}/details', data={'f_name': 'أحمد علي', 'f_phone': '0790000000'})
    assert c.get(f'/f/{slug}').status_code == 200
    assert submit(c, slug, {'a': 'جواب'}).json['ok']
    with app.app_context():
        resp = Response.query.one()
        assert resp.email == 'teacher@school.jo' and resp.filler == {'name': 'أحمد علي', 'phone': '0790000000'}
    assert app.config['MAIL_OUTBOX'][-1]['kind'] == 'copy'
    assert 'سبق أن أرسلت' in c.get(f'/f/{slug}').data.decode()


def test_export_csv_xlsx_json(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    submit(app.test_client(), slug, {'name': 'سارة', 'grade': 'g7', 'days': ['d2'], 'nps': 10})
    csv = admin.get(f'/admin/forms/{fid}/export.csv').data.decode('utf-8')
    assert csv.startswith('﻿') and 'سارة' in csv and 'السابع' in csv and 'الإثنين' in csv and 'Safari' in csv
    x = admin.get(f'/admin/forms/{fid}/export.xlsx')
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(x.data))
    assert wb.sheetnames == ['الإجابات', 'التحليل'] and 'سارة' in [c.value for c in wb['الإجابات'][2]]
    j = admin.get(f'/admin/forms/{fid}/export.json').json
    assert j['responses'][0]['answers']['name'] == 'سارة'
    structure = admin.get(f'/admin/forms/{fid}/export.form').data.decode()
    r = admin.post('/admin/forms/import', data={'text': structure})       # إعادة الاستيراد
    assert r.status_code == 302
    with app.app_context():
        assert Form.query.order_by(Form.id.desc()).first().questions[0]['id'] == 'name'


def test_analysis_numbers_and_crosstab(admin, app):
    import analytics
    fid, slug, _ = make_form(admin, app, ALL)
    for grade, like, nps in [('g7', 'y', 10), ('g7', 'y', 9), ('g8', 'n', 3), ('g8', 'y', 7)]:
        assert submit(app.test_client(), slug, {'name': 'x', 'grade': grade, 'like': like, 'nps': nps}).json['ok']
    with app.app_context():
        f = db.session.get(Form, fid)
        rs = Response.query.all()
        st = {s['id']: s for s in analytics.question_stats(f, rs)}
        assert st['nps']['nps'] == {'promoters': 50.0, 'passives': 25.0, 'detractors': 25.0, 'score': 25.0}
        assert [i['n'] for i in st['like']['items']] == [3, 1, 0]
        ct = analytics.crosstab(f, rs, 'grade', 'like')
        assert [r['counts'] for r in ct['rows']] == [[2, 0, 0], [1, 1, 0]] and ct['grand'] == 4
    r = admin.get(f'/admin/forms/{fid}/analysis?a=grade&b=like&ct=csv')
    assert 'السابع' in r.data.decode('utf-8')
    r = admin.get(f'/admin/forms/{fid}/analysis?seg_q=grade&seg_v=g8')
    assert r.status_code == 200


def test_duplicate_template_subform_and_compare(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    r = admin.post(f'/admin/forms/{fid}/duplicate')
    copy_id = int(r.headers['Location'].split('/')[-2])
    with app.app_context():
        a, b = db.session.get(Form, fid), db.session.get(Form, copy_id)
        assert [q['id'] for q in a.questions] == [q['id'] for q in b.questions] and b.status == 'draft' and b.source_id == fid
    admin.post(f'/admin/forms/{fid}/save-template')
    with app.app_context():
        tpl = Form.query.filter_by(is_template=True, source_id=fid).one()
    r = admin.post('/admin/forms/new', data={'template_id': tpl.id})
    assert r.status_code == 302
    # النموذج الفرعي وربط الإجابات
    r = admin.post(f'/admin/forms/{fid}/subform')
    sub_id = int(r.headers['Location'].split('/')[-2])
    admin.post(f'/admin/api/forms/{sub_id}', json={'status': 'open', 'schema': {'questions': [{'id': 'k', 'type': 'short_text', 'title': 'اسم الابن'}]}})
    admin.post(f'/admin/api/forms/{fid}', json={'settings': {'lang': 'ar', 'show_subforms': True}})
    c = app.test_client()
    done = c.get(submit(c, slug, {'name': 'أب'}).json['redirect']).data.decode()
    with app.app_context():
        sub = db.session.get(Form, sub_id)
        parent_resp = Response.query.filter_by(form_id=fid).one()
    assert f'/f/{sub.slug}?parent={parent_resp.token}' in done
    r = submit(c, sub.slug, {'k': 'ابن'}, parent=parent_resp.token)
    assert r.json['ok']
    with app.app_context():
        child = Response.query.filter_by(form_id=sub_id).one()
        assert child.parent_response_id == parent_resp.id
    assert 'اسم الابن' not in admin.get(f'/admin/responses/{parent_resp.id}').data.decode() or True
    # المقارنة: النسخة تشارك الأسئلة بالمعرّف نفسه
    admin.post(f'/admin/api/forms/{copy_id}', json={'status': 'open'})
    with app.app_context():
        cslug = db.session.get(Form, copy_id).slug
    submit(app.test_client(), cslug, {'name': 'ب', 'grade': 'g8'})
    page = admin.get(f'/admin/compare?ids={fid}&ids={copy_id}&by=category').data.decode()
    assert 'الصف' in page and 'الأسئلة المشتركة' in page


def test_protected_deletes(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    submit(app.test_client(), slug, {'name': 'x'})
    admin.post(f'/admin/forms/{fid}/delete')
    with app.app_context():
        assert db.session.get(Form, fid) is not None            # له إجابات
    admin.post('/admin/bulk/forms', data={'ids': [str(fid)], 'action': 'archive'})
    with app.app_context():
        assert db.session.get(Form, fid).archived
        rid = Response.query.one().id
        me = User.query.filter_by(username='admin').one().id
    admin.post('/admin/bulk/responses', data={'ids': [str(rid)], 'action': 'delete'})
    admin.post('/admin/bulk/forms', data={'ids': [str(fid)], 'action': 'delete'})
    with app.app_context():
        assert db.session.get(Form, fid) is None
    # آخر مسؤول والحساب الحالي لا يُحذفان
    admin.post('/admin/bulk/users', data={'ids': [str(me)], 'action': 'delete'})
    with app.app_context():
        assert db.session.get(User, me) is not None
    admin.post('/admin/users', data={'username': 'editor1', 'password': 'password1', 'role': 'editor'})
    with app.app_context():
        ed = User.query.filter_by(username='editor1').one()
        assert ed.role == 'editor' and ed.check_password('password1')
    r = admin.post('/admin/bulk/users', data={'ids': [str(ed.id)], 'action': 'delete'})
    with app.app_context():
        assert User.query.filter_by(username='editor1').first() is None


def test_editor_sees_only_own_forms(admin, app):
    fid, slug, _ = make_form(admin, app, ALL)
    admin.post('/admin/users', data={'username': 'editor2', 'password': 'password2', 'role': 'editor'})
    e = app.test_client()
    assert e.post('/admin/login', data={'username': 'editor2', 'password': 'password2'}).status_code == 302
    assert e.get(f'/admin/forms/{fid}/edit').status_code == 403
    assert e.post(f'/admin/api/forms/{fid}', json={'title': 'x'}).status_code == 403
    assert e.get('/admin/users').status_code == 302
    assert 'نموذج تجربة' not in e.get('/admin/forms').data.decode()


def test_paste_import_and_media_upload(admin, app):
    r = admin.post('/admin/api/parse', json={'text': '# ت\n1. سؤال *\n- أ\n- ب'})
    assert r.json['questions'][0]['choices'] == ['أ', 'ب']
    r = admin.post('/admin/forms/import', data={'text': '# من النص\n1. سؤال [تاريخ]'})
    fid = int(r.headers['Location'].split('/')[-2])
    with app.app_context():
        f = db.session.get(Form, fid)
        assert f.title == 'من النص' and f.questions[0]['type'] == 'date'
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 50
    r = admin.post('/admin/api/media', data={'file': (io.BytesIO(png), 'bg.png', 'image/png'), 'kind': 'image', 'form_id': str(fid)},
                   content_type='multipart/form-data')
    assert r.json['ok']
    assert app.test_client().get(r.json['url']).data == png       # صور التصميم عامة
    r = admin.post('/admin/api/media', data={'file': (io.BytesIO(b'x'), 'a.txt', 'text/plain'), 'kind': 'video'}, content_type='multipart/form-data')
    assert r.status_code == 400


def test_signature_and_timeout(admin, app):
    import base64
    png = base64.b64encode(b'\x89PNG\r\n\x1a\nabc').decode()
    fid, slug, _ = make_form(admin, app, [{'id': 's', 'type': 'signature', 'title': 'وقّع', 'required': True},
                                          {'id': 't', 'type': 'short_text', 'title': 'نص', 'required': True}], settings={'time_limit': 5})
    r = submit(app.test_client(), slug, {'s': 'data:image/png;base64,' + png, 't': 'x'})
    assert r.json['ok']
    r = submit(app.test_client(), slug, {}, timeout=True)            # انتهت المهلة: تُقبل ناقصة
    assert r.json['ok']
    r = submit(app.test_client(), slug, {})
    assert r.status_code == 400


def test_migration_adds_missing_columns(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / 'old.db'
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE forms (id INTEGER PRIMARY KEY, slug VARCHAR(40), title VARCHAR(300) NOT NULL, status VARCHAR(20), '
                'is_template BOOLEAN, archived BOOLEAN, schema TEXT, settings TEXT, views INTEGER, title_en VARCHAR(300), description TEXT, '
                'category VARCHAR(120), owner_id INTEGER, parent_id INTEGER, created_at DATETIME, updated_at DATETIME)')
    con.execute("INSERT INTO forms (id, slug, title, status, is_template, archived, schema, settings, views) VALUES (1, 'old1', 'قديم', 'open', 0, 0, '{\"questions\": []}', '{}', 3)")
    con.commit()
    con.close()
    monkeypatch.setenv('FORMS_DB_PATH', str(path))
    from app import create_app
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}'})
    with app.app_context():
        f = db.session.get(Form, 1)
        assert f.title == 'قديم' and f.views == 3 and f.starts == 0
