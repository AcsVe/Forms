"""المستهدفون والمجموعات والاستيراد والدعوات وإعدادات حساب Microsoft."""
import io
import re

from conftest import make_form, submit
from models import Form, Group, Invitation, Person, Response, db


def _csv(text):
    return (io.BytesIO(('﻿' + text).encode('utf-8')), 'people.csv')


def test_people_crud_import_template_and_bulk(admin, app):
    r = admin.post('/admin/people/save', data={'name': 'سارة أحمد', 'email': 'Sara@School.jo', 'phone': '0790000000'})
    assert r.status_code == 302
    admin.post('/admin/groups/save', data={'name': 'معلمو العلوم'})
    r = admin.post('/admin/people/import', data={'file': _csv('الاسم,البريد,الهاتف,المجموعات,ملاحظة\n'
                                                              'سارة أحمد,sara@school.jo,,معلمو العلوم،الهيئة,معلمة\n'
                                                              'خالد,khaled@school.jo,,الصف العاشر,طالب\n'
                                                              'بلا بريد,,,,\n'
                                                              'خطأ,not-an-email,,,\n')}, content_type='multipart/form-data')
    page = r.data.decode()
    assert 'اكتمل الاستيراد' in page and 'not-an-email' in page
    with app.app_context():
        assert Person.query.count() == 2
        sara = Person.query.filter_by(email='sara@school.jo').one()
        assert sara.note == 'معلمة' and sorted(g.name for g in sara.groups) == ['الهيئة', 'معلمو العلوم']
        sid, kid = sara.id, Person.query.filter_by(email='khaled@school.jo').one().id
        gid = Group.query.filter_by(name='الصف العاشر').one().id
    # ملف Excel النموذجي يُقرأ كما هو
    x = admin.get('/admin/people/template.xlsx')
    r = admin.post('/admin/people/import', data={'file': (io.BytesIO(x.data), 'people.xlsx')}, content_type='multipart/form-data')
    assert 'اكتمل الاستيراد' in r.data.decode()
    assert '﻿' in admin.get('/admin/people/template.csv').data.decode('utf-8')
    with app.app_context():
        assert Person.query.count() == 4
    # إجراءات جماعية + الحذف المحمي للمجموعة التي فيها أعضاء
    admin.post('/admin/bulk/people', data={'ids': [str(sid)], 'action': 'add_group', 'group_id': str(gid)})
    admin.post('/admin/bulk/people', data={'ids': [str(kid)], 'action': 'deactivate'})
    admin.post('/admin/bulk/groups', data={'ids': [str(gid)], 'action': 'delete'})
    with app.app_context():
        assert db.session.get(Group, gid) is not None
        assert gid in [g.id for g in db.session.get(Person, sid).groups]
        assert db.session.get(Person, kid).active is False
    for lang in ('ar', 'en'):
        admin.get(f'/lang/{lang}')
        for u in ('/admin/people', f'/admin/people?group={gid}', '/admin/people/import', '/admin/settings/microsoft'):
            assert admin.get(u).status_code == 200, u


def test_invitations_restricted_form_tracking_and_reminders(admin, app):
    fid, slug, _ = make_form(admin, app, [{'id': 'a', 'type': 'short_text', 'title': 'رأيك', 'required': True}])
    admin.post('/admin/people/import', data={'file': _csv('الاسم,البريد,المجموعات\nأمل,amal@school.jo,الصف التاسع\n'
                                                          'باسل,basel@school.jo,الصف التاسع\nجود,jood@school.jo,الإداريون\n')},
               content_type='multipart/form-data')
    with app.app_context():
        g9 = Group.query.filter_by(name='الصف التاسع').one().id
    app.config['MAIL_OUTBOX'].clear()
    r = admin.post(f'/admin/forms/{fid}/audience', data={'mode': 'groups', 'group_ids': [str(g9)], 'send': '1'})
    assert r.status_code == 302
    assert len(app.config['MAIL_OUTBOX']) == 2 and app.config['MAIL_OUTBOX'][0]['kind'] == 'invite'
    link = re.search(r'href="[^"]*(/f/[^"?]+\?inv=[^"]+)"', app.config['MAIL_OUTBOX'][0]['html']).group(1)
    to = app.config['MAIL_OUTBOX'][0]['to'][0]
    admin.post(f'/admin/forms/{fid}/audience', data={'mode': 'all'})          # لا تتكرر الدعوات
    with app.app_context():
        assert Invitation.query.filter_by(form_id=fid).count() == 3
    admin.post(f'/admin/forms/{fid}/audience', data={'action': 'settings', 'audience_only': '1'})
    stranger = app.test_client()
    assert 'للمدعوين فقط' in stranger.get(f'/f/{slug}').data.decode()
    assert submit(stranger, slug, {'a': 'x'}).status_code == 403
    guest = app.test_client()
    assert guest.get(link).status_code == 200
    r = submit(guest, slug, {'a': 'ممتاز'})
    assert r.json['ok'], r.data
    with app.app_context():
        inv = Invitation.query.join(Person).filter(Person.email == to).one()
        resp = Response.query.one()
        assert inv.responded_at and inv.response_id == resp.id and inv.opened_at
        assert resp.email == to and resp.filler['name'] == inv.person.name
        waiting = [i.id for i in Invitation.query.filter_by(form_id=fid) if not i.responded_at]
    assert 'سبق أن أرسلت' in guest.get(link).data.decode()
    page = admin.get(f'/admin/forms/{fid}/audience?status=waiting').data.decode()
    assert 'لم يُجيبوا' in page
    app.config['MAIL_OUTBOX'].clear()
    admin.post('/admin/bulk/invitations', data={'ids': [str(i) for i in waiting] + [str(inv.id)], 'action': 'send'})
    kinds = [m['kind'] for m in app.config['MAIL_OUTBOX']]
    assert kinds.count('reminder') == 1 and kinds.count('invite') == 1 and len(kinds) == 2   # من أجاب لا يُذكَّر
    csv_text = admin.get(f'/admin/forms/{fid}/audience/links.csv').data.decode('utf-8')
    assert '?inv=' in csv_text and 'نعم' in csv_text
    # الحذف المحمي: النموذج الذي له مدعوون، والشخص الذي له دعوة
    admin.post(f'/admin/forms/{fid}/delete')
    with app.app_context():
        assert db.session.get(Form, fid) is not None
        pid = inv.person_id
    admin.post('/admin/bulk/people', data={'ids': [str(pid)], 'action': 'delete'})
    with app.app_context():
        assert db.session.get(Person, pid) is not None


def test_microsoft_settings_saved_safely_and_tested(admin, app, tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('SECRET_KEY=keep-me\nMS_TENANT_ID=old\n', encoding='utf-8')
    app.config['ENV_FILE'] = str(env)
    tid, cid = '11111111-2222-3333-4444-555555555555', '66666666-7777-8888-9999-000000000000'
    r = admin.post('/admin/settings/microsoft', data={'action': 'save', 'tenant': tid, 'client': cid, 'secret': 'S3cr3t-value',
                                                      'sender': 'forms@school.jo'})
    assert r.status_code == 302
    text = env.read_text(encoding='utf-8')
    assert 'SECRET_KEY=keep-me' in text and f'MS_TENANT_ID={tid}' in text and 'MS_CLIENT_SECRET=S3cr3t-value' in text
    assert app.config['MS_CLIENT_SECRET'] == 'S3cr3t-value'
    page = admin.get('/admin/settings/microsoft').data.decode()
    assert 'S3cr3t-value' not in page and tid in page and '/auth/ms/callback' in page and 'مربوط' in page
    admin.post('/admin/settings/microsoft', data={'action': 'save', 'tenant': tid, 'client': cid, 'secret': '', 'sender': 'forms@school.jo'})
    assert app.config['MS_CLIENT_SECRET'] == 'S3cr3t-value'           # فارغ = يبقى كما هو
    assert admin.post('/admin/settings/microsoft', data={'action': 'save', 'tenant': 'bad id!', 'client': cid}).status_code == 302
    assert app.config['MS_TENANT_ID'] == tid
    import mail
    monkeypatch.setattr(mail, '_graph_token', lambda: 'T')
    calls = []

    def fake_get(path, limit=None):
        calls.append(path)
        if path.startswith('/groups'):
            raise RuntimeError('Graph GET HTTP 403')
        return [{'id': 'x'}]
    monkeypatch.setattr(mail, 'graph_get', fake_get)
    page = admin.post('/admin/settings/microsoft', data={'action': 'test'}).data.decode()
    assert 'الاتصال بحساب Microsoft للمدرسة يعمل' in page and 'قراءة المجموعات غير مسموحة' in page and '403' not in page


def test_import_groups_from_microsoft_directory(admin, app, monkeypatch):
    app.config.update(MS_TENANT_ID='t', MS_CLIENT_ID='c', MS_CLIENT_SECRET='s')
    import mail

    def fake_get(path, limit=None):
        if path.startswith('/groups?$select'):
            return [{'id': 'g-1', 'displayName': 'الصف العاشر ب', 'mail': None}]
        if path.startswith('/groups?$filter'):
            return [{'id': 'g-1', 'displayName': 'الصف العاشر ب', 'description': 'طلبة الصف'}]
        if path.startswith('/groups/g-1/members'):
            return [{'@odata.type': '#microsoft.graph.user', 'id': 'u1', 'displayName': 'ريم', 'mail': 'reem@school.jo'},
                    {'@odata.type': '#microsoft.graph.user', 'id': 'u2', 'displayName': 'بلا بريد', 'mail': None},
                    {'@odata.type': '#microsoft.graph.group', 'id': 'g-2', 'displayName': 'مجموعة داخلية', 'mail': 'x@school.jo'}]
        return []
    monkeypatch.setattr(mail, 'graph_get', fake_get)
    assert 'الصف العاشر ب' in admin.get('/admin/people/microsoft').data.decode()
    r = admin.post('/admin/people/microsoft', data={'ids': ['g-1'], 'action': 'add'})
    assert r.status_code == 302
    with app.app_context():
        g = Group.query.filter_by(ms_id='g-1').one()
        assert g.source == 'microsoft' and [p.email for p in g.people] == ['reem@school.jo']
