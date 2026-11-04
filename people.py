"""المستهدفون: الأشخاص والمجموعات (يدوياً، أو من ملف Excel أو CSV، أو من دليل Microsoft للمدرسة)، ودعوات النماذج
بالبريد أو بالرابط ورمز QR، ومتابعة من أجاب ومن لم يُجب، والتذكيرات.

تُسجَّل مساراته على admin_bp نفسه (blueprints/admin.py يستورده في آخره)، فأسماؤها admin.people وغيرها.
"""
import csv
import io
import re
from datetime import datetime

from flask import Response as FlaskResponse, abort, current_app, flash, redirect, render_template, request, session, url_for

from blueprints.common import current_user, get_form, login_required
from i18n import pick
from models import Form, Group, Invitation, Person, db

EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
COLS = {'name': ('الاسم', 'name', 'full name', 'الاسم الكامل', 'displayname'),
        'email': ('البريد', 'البريد الإلكتروني', 'email', 'e-mail', 'mail'),
        'phone': ('الهاتف', 'رقم الهاتف', 'phone', 'mobile'),
        'groups': ('المجموعات', 'المجموعة', 'groups', 'group'),
        'note': ('ملاحظة', 'ملاحظات', 'الصفة', 'note', 'notes', 'title')}


def _norm_header(h):
    h = str(h or '').strip().lower()
    for key, names in COLS.items():
        if h in names:
            return key
    return None


def _group_by_name(name, cache):
    name = name.strip()[:200]
    if not name:
        return None
    if name in cache:
        return cache[name]
    g = Group.query.filter(db.func.lower(Group.name) == name.lower()).first()
    if not g:
        g = Group(name=name)
        db.session.add(g)
        db.session.flush()
    cache[name] = g
    return g


def upsert_person(name, email, phone='', note='', source='local', ms_id=None):
    """يضيف الشخص أو يحدّثه بالبريد (البريد مفتاحه). يعيد (الشخص، جديد؟)."""
    email = (email or '').strip().lower()[:255] or None
    p = Person.query.filter_by(email=email).first() if email else None
    if not p and ms_id:
        p = Person.query.filter_by(ms_id=ms_id).first()
    new = p is None
    if new:
        p = Person(email=email)
        db.session.add(p)
    p.name = (name or '').strip()[:200] or (email or '').split('@')[0] or p.name or '—'
    if phone:
        p.phone = str(phone).strip()[:40]
    if note:
        p.note = str(note).strip()[:300]
    if ms_id:
        p.ms_id, p.source = ms_id, source
    return p, new


def import_rows(rows):
    """rows: قائمة قواميس بالمفاتيح name/email/phone/groups/note. يعيد ملخصاً."""
    added = updated = 0
    skipped = []
    cache = {}
    for i, r in enumerate(rows, start=2):
        email = (r.get('email') or '').strip()
        name = (r.get('name') or '').strip()
        if not name and not email:
            continue
        if email and not EMAIL.match(email):
            skipped.append(pick(f'السطر {i}: البريد «{email}» غير صحيح', f'Row {i}: the email "{email}" is not valid'))
            continue
        if not email:
            skipped.append(pick(f'السطر {i}: لا يوجد بريد لـ «{name}»', f'Row {i}: no email for "{name}"'))
            continue
        p, new = upsert_person(name, email, r.get('phone') or '', r.get('note') or '')
        added += new
        updated += not new
        for gname in re.split(r'[،,;|]', r.get('groups') or ''):
            g = _group_by_name(gname, cache)
            if g and g not in p.groups:
                p.groups.append(g)
    db.session.commit()
    return added, updated, skipped


def read_file(up):
    """ملف CSV أو Excel ← قائمة صفوف بالمفاتيح المعروفة."""
    name = (up.filename or '').lower()
    data = up.read()
    table = []
    if name.endswith(('.xlsx', '.xlsm')):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        table = [['' if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
    else:
        text = data.decode('utf-8-sig', 'replace')
        try:
            dialect = csv.Sniffer().sniff(text[:2000], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        table = list(csv.reader(io.StringIO(text), dialect))
    if not table:
        return []
    keys = [_norm_header(h) for h in table[0]]
    if 'email' not in keys:
        raise ValueError(pick('لم أجد عمود «البريد» في السطر الأول. استخدم الملف النموذجي.', 'No "email" column in the first row. Use the template file.'))
    return [{k: (row[i] if i < len(row) else '') for i, k in enumerate(keys) if k} for row in table[1:]]


# ── الدعوات ──────────────────────────────────────────────────────────────────

def public_link(form, inv=None):
    base = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    return f'{base}/f/{form.slug}' + (f'?inv={inv.token}' if inv else '')


def send_invitation(inv, reminder=False):
    from mail import send_email
    from markupsafe import escape
    f, p = inv.form, inv.person
    if not p.email:
        inv.send_failed = True
        return False
    lang = f.s('lang', 'ar')
    en = lang == 'en'
    link = public_link(f, inv)
    title = escape(f.title_for(lang))
    head = ('Reminder: ' if reminder else '') + 'You are invited to fill in a form' if en else \
        ('تذكير: ' if reminder else '') + 'دعوة إلى تعبئة نموذج'
    deadline = ''
    if f.s('close_at'):
        d = str(f.s('close_at')).replace('T', ' ')
        deadline = f'<p>{"Deadline" if en else "آخر موعد"}: {escape(d)}</p>'
    html = (f'<div dir="{"ltr" if en else "rtl"}" style="font-family:Tahoma,Arial;font-size:15px;color:#1e293b">'
            f'<p>{"Dear" if en else "السلام عليكم"} {escape(p.name)}،</p>'
            f'<p>{"Please fill in the form" if en else "نرجو تعبئة النموذج"}: <b>{title}</b></p>{deadline}'
            f'<p><a href="{link}" style="display:inline-block;background:{f.s("accent") or "#0C67EC"};color:#fff;padding:12px 22px;'
            f'border-radius:10px;text-decoration:none;font-weight:bold">{"Open the form" if en else "فتح النموذج"}</a></p>'
            f'<p style="color:#64748b;font-size:13px">{"This link is personal; please do not share it." if en else "هذا الرابط خاص بك، فلا تشاركه مع غيرك."}</p></div>')
    res = send_email([p.email], f'{head}: {f.title_for(lang)}', html, kind='reminder' if reminder else 'invite')
    inv.send_count = (inv.send_count or 0) + (1 if res.ok else 0)
    inv.send_failed = not res.ok
    if res.ok:
        inv.last_sent_at = datetime.utcnow()
    return res.ok


def add_invitations(form, people):
    """ينشئ دعوات لمن ليست له دعوة؛ يعيد الدعوات الجديدة."""
    have = {pid for (pid,) in db.session.query(Invitation.person_id).filter_by(form_id=form.id)}
    new = []
    for p in people:
        if p.id in have or not p.active or not p.email:
            continue
        inv = Invitation(form_id=form.id, person_id=p.id)
        db.session.add(inv)
        new.append(inv)
        have.add(p.id)
    db.session.flush()
    return new


def mark_response(form, response, token=None, email=None):
    """تُربط الإجابة بالدعوة (بالرابط الشخصي، وإلا بالبريد الموثّق)."""
    inv = None
    if token:
        inv = Invitation.query.filter_by(token=token, form_id=form.id).first()
    if not inv and email:
        inv = Invitation.query.join(Person).filter(Invitation.form_id == form.id, db.func.lower(Person.email) == email.lower()).first()
    if inv and not inv.responded_at:
        inv.responded_at = datetime.utcnow()
        inv.response_id = response.id
        if not response.email and inv.person.email:
            response.email = inv.person.email
        if not response.filler:
            response.filler = {'name': inv.person.name}
    return inv


# ── المسارات ─────────────────────────────────────────────────────────────────

def register(bp):
    from blueprints.common import admin_required  # noqa: F401  (الصفحات للمسؤول والمحرّر معاً)

    @bp.route('/people')
    @login_required
    def people():
        a = request.args
        q = Person.query
        if a.get('group', type=int):
            q = q.join(Person.groups).filter(Group.id == a.get('group', type=int))
        if a.get('status') == 'inactive':
            q = q.filter(Person.active.is_(False))
        elif a.get('status') == 'active':
            q = q.filter(Person.active.is_(True))
        rows = q.order_by(Person.name).all()
        groups = Group.query.order_by(Group.name).all()
        counts = dict(db.session.query(Group.id, db.func.count(Person.id)).join(Group.people).group_by(Group.id).all())
        import tenant
        return render_template('admin/people.html', rows=rows, groups=groups, counts=counts, args=a,
                               ms_ok=tenant.status()['complete'], total=Person.query.count(),
                               n_active=Person.query.filter_by(active=True).count())

    @bp.route('/people/save', methods=['POST'])
    @login_required
    def person_save():
        pid = request.form.get('id', type=int)
        email = (request.form.get('email') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        if not name or not EMAIL.match(email):
            flash(pick('اكتب الاسم وبريداً صحيحاً.', 'Enter a name and a valid email.'), 'error')
            return redirect(url_for('admin.people'))
        clash = Person.query.filter(Person.email == email, Person.id != (pid or 0)).first()
        if clash:
            flash(pick(f'البريد مستخدم لـ «{clash.name}».', f'The email is already used by "{clash.name}".'), 'error')
            return redirect(url_for('admin.people'))
        p = db.session.get(Person, pid) if pid else None
        if not p:
            p = Person()
            db.session.add(p)
        p.name, p.email = name[:200], email
        p.phone = (request.form.get('phone') or '').strip()[:40] or None
        p.note = (request.form.get('note') or '').strip()[:300] or None
        ids = {int(i) for i in request.form.getlist('groups') if i.isdigit()}
        p.groups = Group.query.filter(Group.id.in_(ids or [0])).all()
        db.session.commit()
        flash(pick('حُفظ.', 'Saved.'), 'ok')
        return redirect(url_for('admin.people'))

    @bp.route('/groups/save', methods=['POST'])
    @login_required
    def group_save():
        gid = request.form.get('id', type=int)
        name = (request.form.get('name') or '').strip()[:200]
        if not name:
            flash(pick('اكتب اسم المجموعة.', 'Enter the group name.'), 'error')
            return redirect(url_for('admin.people') + '#groups')
        g = db.session.get(Group, gid) if gid else None
        if not g:
            g = Group()
            db.session.add(g)
        g.name = name
        g.description = (request.form.get('description') or '').strip()[:500] or None
        db.session.commit()
        flash(pick('حُفظت المجموعة.', 'The group was saved.'), 'ok')
        return redirect(url_for('admin.people') + '#groups')

    @bp.route('/people/import', methods=['GET', 'POST'])
    @login_required
    def people_import():
        result = None
        if request.method == 'POST':
            up = request.files.get('file')
            if not up or not up.filename:
                flash(pick('اختر ملفاً.', 'Choose a file.'), 'error')
            else:
                try:
                    rows = read_file(up)
                    added, updated, skipped = import_rows(rows)
                    result = {'added': added, 'updated': updated, 'skipped': skipped}
                except ValueError as e:
                    flash(str(e), 'error')
                except Exception:  # noqa: BLE001
                    current_app.logger.exception('[people] import')
                    flash(pick('تعذّرت قراءة الملف. احفظه بصيغة Excel أو CSV كما في الملف النموذجي.',
                               'The file could not be read. Save it as Excel or CSV like the template file.'), 'error')
        import tenant
        return render_template('admin/people_import.html', result=result, ms_ok=tenant.status()['complete'])

    @bp.route('/people/template.<fmt>')
    @login_required
    def people_template(fmt):
        head = ['الاسم', 'البريد', 'الهاتف', 'المجموعات', 'ملاحظة']
        sample = [['سارة أحمد', 'sara@school.edu.jo', '0790000000', 'معلمو العلوم، الهيئة التدريسية', 'معلمة'],
                  ['خالد محمود', 'khaled@school.edu.jo', '', 'الصف العاشر أ', 'طالب']]
        if fmt == 'csv':
            buf = io.StringIO()
            buf.write('﻿')
            w = csv.writer(buf)
            w.writerow(head)
            w.writerows(sample)
            data, mime = buf.getvalue().encode('utf-8'), 'text/csv; charset=utf-8'
        elif fmt == 'xlsx':
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            wb = Workbook()
            ws = wb.active
            ws.title = 'المستهدفون'
            ws.sheet_view.rightToLeft = True
            ws.append(head)
            for c in ws[1]:
                c.font = Font(bold=True, color='FFFFFF')
                c.fill = PatternFill('solid', fgColor='0C67EC')
            for r in sample:
                ws.append(r)
            for col, w in zip('ABCDE', (24, 30, 16, 36, 20)):
                ws.column_dimensions[col].width = w
            out = io.BytesIO()
            wb.save(out)
            data, mime = out.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            abort(404)
        resp = FlaskResponse(data, mimetype=mime)
        resp.headers['Content-Disposition'] = f'attachment; filename="people-template.{fmt}"'
        return resp

    @bp.route('/people/microsoft', methods=['GET', 'POST'])
    @login_required
    def people_microsoft():
        import mail
        import tenant
        if not tenant.status()['complete']:
            flash(pick('اربط حساب Microsoft للمدرسة أولاً من «الإعدادات ← حساب Microsoft».',
                       'Connect the school Microsoft account first in Settings → Microsoft account.'), 'error')
            return redirect(url_for('admin.people_import'))
        sel = '$select=id,displayName,mail,userPrincipalName,mobilePhone,jobTitle,department'
        if request.method == 'POST':
            try:
                added = updated = 0
                if request.form.get('action') == 'users':
                    for u in mail.graph_get(f'/users?{sel}&$top=999'):
                        email = u.get('mail') or ''
                        if not email:
                            continue
                        p, new = upsert_person(u.get('displayName'), email, u.get('mobilePhone') or '',
                                               u.get('jobTitle') or u.get('department') or '', 'microsoft', u.get('id'))
                        added += new
                        updated += not new
                else:
                    for gid in request.form.getlist('ids')[:200]:
                        info = mail.graph_get(f'/groups?$filter=id eq \'{re.sub(r"[^0-9a-fA-F-]", "", gid)}\'&$select=id,displayName,description', limit=1)
                        if not info:
                            continue
                        g = Group.query.filter_by(ms_id=info[0]['id']).first() or Group(ms_id=info[0]['id'], source='microsoft')
                        g.name = (info[0].get('displayName') or g.name or '—')[:200]
                        g.description = (info[0].get('description') or '')[:500] or g.description
                        db.session.add(g)
                        db.session.flush()
                        for u in mail.graph_get(f'/groups/{info[0]["id"]}/members?{sel}&$top=999'):
                            email = u.get('mail') or ''
                            if not email or u.get('@odata.type', '#microsoft.graph.user') != '#microsoft.graph.user':
                                continue
                            p, new = upsert_person(u.get('displayName'), email, u.get('mobilePhone') or '',
                                                   u.get('jobTitle') or '', 'microsoft', u.get('id'))
                            added += new
                            updated += not new
                            if g not in p.groups:
                                p.groups.append(g)
                db.session.commit()
                flash(pick(f'تم الاستيراد: {added} جديد، و{updated} حُدِّث.', f'Imported: {added} new, {updated} updated.'), 'ok')
                return redirect(url_for('admin.people'))
            except Exception:  # noqa: BLE001
                db.session.rollback()
                current_app.logger.exception('[people] microsoft import')
                flash(pick('تعذّرت القراءة من دليل Microsoft. افتح «الإعدادات ← حساب Microsoft» واضغط «فحص الاتصال».',
                           'Reading the Microsoft directory failed. Open Settings → Microsoft account and press "Test connection".'), 'error')
        groups, error = [], None
        try:
            groups = sorted(mail.graph_get('/groups?$select=id,displayName,description,mail&$top=999'), key=lambda g: g.get('displayName') or '')
        except Exception:  # noqa: BLE001
            current_app.logger.exception('[people] microsoft groups')
            error = True
        have = {g.ms_id for g in Group.query.filter(Group.ms_id.isnot(None))}
        return render_template('admin/people_microsoft.html', groups=groups, error=error, have=have)

    # ── جمهور النموذج ──
    @bp.route('/forms/<int:fid>/audience', methods=['GET', 'POST'])
    @login_required
    def audience(fid):
        from mail import graph_status
        f = get_form(fid)
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'settings':
                s = dict(f.settings or {})
                s['audience_only'] = bool(request.form.get('audience_only'))
                f.settings = s
                db.session.commit()
                flash(pick('حُفظ.', 'Saved.'), 'ok')
                return redirect(url_for('admin.audience', fid=f.id))
            mode = request.form.get('mode')
            q = Person.query.filter(Person.active.is_(True))
            if mode == 'groups':
                ids = [int(i) for i in request.form.getlist('group_ids') if i.isdigit()]
                q = q.join(Person.groups).filter(Group.id.in_(ids or [0]), Group.active.is_(True))
            elif mode == 'people':
                ids = [int(i) for i in request.form.getlist('person_ids') if i.isdigit()]
                q = q.filter(Person.id.in_(ids or [0]))
            elif mode != 'all':
                abort(400)
            people = q.distinct().all()
            new = add_invitations(f, people)
            sent = failed = 0
            if request.form.get('send') and new:
                if f.status != 'open':
                    flash(pick('أُضيف المدعوون، ولم تُرسل الدعوات لأن النموذج ليس مفتوحاً. افتحه ثم اضغط «إرسال».',
                               'The people were added, but no invitations were sent because the form is not open. Open it, then press "Send".'), 'error')
                else:
                    for inv in new:
                        if send_invitation(inv):
                            sent += 1
                        else:
                            failed += 1
            db.session.commit()
            msg = pick(f'أُضيف {len(new)} مدعواً', f'{len(new)} people added')
            if sent or failed:
                msg += pick(f'، وأُرسلت {sent} دعوة', f', {sent} invitations sent') + (pick(f'، وتعذّر إرسال {failed}', f', {failed} failed') if failed else '')
            flash(msg + '.', 'ok' if not failed else 'error')
            return redirect(url_for('admin.audience', fid=f.id))
        invs = f.invitations.join(Person).order_by(Person.name).all()
        st = request.args.get('status')
        k = {s: sum(1 for i in invs if i.status == s) for s in ('pending', 'sent', 'opened', 'responded', 'failed')}
        k['all'] = len(invs)
        k['waiting'] = k['all'] - k['responded']
        if st == 'waiting':
            invs = [i for i in invs if not i.responded_at]
        elif st:
            invs = [i for i in invs if i.status == st]
        people = Person.query.filter_by(active=True).order_by(Person.name).all()
        groups = Group.query.filter_by(active=True).order_by(Group.name).all()
        counts = dict(db.session.query(Group.id, db.func.count(Person.id)).join(Group.people).filter(Person.active.is_(True)).group_by(Group.id).all())
        return render_template('admin/audience.html', f=f, invs=invs, k=k, st=st, people=people, groups=groups, counts=counts,
                               mail_ready=graph_status()['ready'] or current_app.config.get('MAIL_BACKEND') == 'memory',
                               link=public_link)

    @bp.route('/forms/<int:fid>/audience/links.csv')
    @login_required
    def audience_links(fid):
        f = get_form(fid)
        buf = io.StringIO()
        buf.write('﻿')
        w = csv.writer(buf)
        w.writerow(['الاسم', 'البريد', 'الرابط الشخصي', 'أجاب'])
        for inv in f.invitations.join(Person).order_by(Person.name):
            w.writerow([inv.person.name, inv.person.email, public_link(f, inv), 'نعم' if inv.responded_at else 'لا'])
        resp = FlaskResponse(buf.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = f'attachment; filename="form-{f.id}-links.csv"'
        return resp


def bulk(entity, ids, action, form_data):
    """الإجراءات الجماعية للأشخاص والمجموعات والدعوات: (عدد المنفَّذ، قائمة المتخطّى)."""
    done, skipped = 0, []
    if entity == 'people':
        gid = form_data.get('group_id', type=int)
        g = db.session.get(Group, gid) if gid else None
        for p in Person.query.filter(Person.id.in_(ids or [0])).all():
            if action == 'activate':
                p.active = True
            elif action == 'deactivate':
                p.active = False
            elif action == 'delete':
                if p.invitations.count():
                    skipped.append(pick(f'{p.name} (له دعوات — عطّله بدلاً من حذفه)', f'{p.name} (has invitations — deactivate instead)'))
                    continue
                db.session.delete(p)
            elif action in ('add_group', 'remove_group') and g:
                if action == 'add_group' and g not in p.groups:
                    p.groups.append(g)
                elif action == 'remove_group' and g in p.groups:
                    p.groups.remove(g)
            else:
                continue
            done += 1
    elif entity == 'groups':
        for g in Group.query.filter(Group.id.in_(ids or [0])).all():
            if action == 'activate':
                g.active = True
            elif action == 'deactivate':
                g.active = False
            elif action == 'delete':
                if g.people.count():
                    skipped.append(pick(f'{g.name} (فيها أعضاء — عطّلها أو أخرج أعضاءها أولاً)', f'{g.name} (has members — deactivate it or remove them first)'))
                    continue
                db.session.delete(g)
            else:
                continue
            done += 1
    elif entity == 'invitations':
        for inv in Invitation.query.filter(Invitation.id.in_(ids or [0])).all():
            if not (current_user().is_admin or inv.form.owner_id == current_user().id):
                continue
            if action == 'send':
                if inv.responded_at:
                    skipped.append(pick(f'{inv.person.name} (أجاب)', f'{inv.person.name} (already answered)'))
                    continue
                if inv.form.status != 'open':
                    skipped.append(pick(f'{inv.person.name} (النموذج ليس مفتوحاً)', f'{inv.person.name} (the form is not open)'))
                    continue
                if not send_invitation(inv, reminder=bool(inv.send_count)):
                    skipped.append(pick(f'{inv.person.name} (تعذّر الإرسال)', f'{inv.person.name} (sending failed)'))
                    continue
            elif action == 'delete':
                if inv.responded_at:
                    skipped.append(pick(f'{inv.person.name} (له إجابة)', f'{inv.person.name} (has a response)'))
                    continue
                db.session.delete(inv)
            else:
                continue
            done += 1
    else:
        return None
    return done, skipped
