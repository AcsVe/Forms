"""لوحة الإدارة: الدخول، واللوحة الرئيسية، والنماذج، والمحرّر، والإجابات، والتحليل، والمقارنة، والمستخدمون، والإعدادات."""
import copy
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

from flask import (Blueprint, Response as FlaskResponse, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import analytics
import exporter
from blueprints.common import (admin_required, can_edit, current_user, filtered_responses, forms_query, get_form,
                               login_required, period_range, response_filters)
from i18n import pick
from importer import parse as parse_paste
from models import AppSetting, EmailLog, Form, MediaFile, Response, User, db
from schema import GROUPS, NO_ANSWER, TYPES, answer_text, grade, normalize_schema, qtitle, walk

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

_LOGIN_FAILS = defaultdict(list)
MEDIA_LIMITS = {'image': 8, 'audio': 20, 'video': 50, 'logo': 4}
MEDIA_TYPES = {'image': ('image/',), 'logo': ('image/',), 'audio': ('audio/',), 'video': ('video/',)}


@admin_bp.app_context_processor
def _inject_user():
    u = current_user() if session.get('uid') else None
    return {'me': u, 'TYPES': TYPES, 'GROUPS': GROUPS}


def _ip():
    return request.headers.get('CF-Connecting-IP') or request.remote_addr or ''


# ── الدخول ───────────────────────────────────────────────────────────────────

LOCK_N, LOCK_SEC = 10, 15 * 60
_RESET_REQ = defaultdict(list)


def _find_user(name):
    name = (name or '').strip().lower()
    if not name:
        return None
    return User.query.filter((db.func.lower(User.username) == name) | (db.func.lower(User.email) == name)).first()


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        ip = _ip()
        now = time.time()
        _LOGIN_FAILS[ip] = [t for t in _LOGIN_FAILS[ip] if now - t < LOCK_SEC]
        if len(_LOGIN_FAILS[ip]) >= LOCK_N:
            error = pick('محاولات خاطئة كثيرة من هذا الجهاز. انتظر خمس عشرة دقيقة ثم أعد المحاولة.',
                         'Too many wrong attempts from this device. Wait fifteen minutes and try again.')
        else:
            u = _find_user(request.form.get('username'))
            if u and u.active and u.check_password(request.form.get('password') or ''):
                lang = session.get('lang', 'ar')
                session.clear()
                session['uid'], session['sv'], session['lang'] = u.id, u.session_ver or 0, lang
                session.permanent = bool(request.form.get('remember'))
                u.last_login_at = datetime.utcnow()
                db.session.commit()
                _LOGIN_FAILS.pop(ip, None)
                nxt = request.args.get('next') or ''
                return redirect(nxt if nxt.startswith('/admin') and not nxt.startswith('//') else url_for('admin.dashboard'))
            _LOGIN_FAILS[ip].append(now)
            error = pick('اسم المستخدم أو البريد أو كلمة المرور غير صحيحة.', 'Wrong user name, email or password.')
    return render_template('admin/login.html', error=error)


@admin_bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    """نسيت كلمة المرور: رابط بالبريد عبر Microsoft Graph، صالح ساعة ولمرة واحدة. الرسالة نفسها في كل الأحوال."""
    import hashlib
    import secrets
    from datetime import timedelta
    from flask import current_app
    from mail import send_email
    from models import PasswordReset
    if request.method == 'POST':
        ip = _ip()
        now = time.time()
        _RESET_REQ[ip] = [t for t in _RESET_REQ[ip] if now - t < 3600]
        u = _find_user(request.form.get('username')) if len(_RESET_REQ[ip]) < 5 else None
        _RESET_REQ[ip].append(now)
        if u and u.active and u.email:
            token = secrets.token_urlsafe(32)
            db.session.add(PasswordReset(user_id=u.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                         expires_at=datetime.utcnow() + timedelta(hours=1)))
            db.session.commit()
            link = (current_app.config.get('BASE_URL') or request.host_url.rstrip('/')) + url_for('admin.reset', token=token)
            send_email([u.email], 'إعادة تعيين كلمة المرور — نظام النماذج والاستبيانات',
                       f'<div dir="rtl" style="font-family:Tahoma,Arial"><p>طُلبت إعادة تعيين كلمة المرور لحسابك <b>{u.username}</b>.</p>'
                       f'<p><a href="{link}">اضغط هنا لتعيين كلمة مرور جديدة</a> (صالح ساعة واحدة ولمرة واحدة).</p>'
                       f'<p>إن لم تطلب ذلك فتجاهل هذه الرسالة.</p></div>', kind='reset')
        flash(pick('إن كان الحساب موجوداً وله بريد، فقد أُرسل إليه رابط صالح ساعة واحدة.',
                   'If the account exists and has an email, a link valid for one hour was sent to it.'), 'ok')
        return redirect(url_for('admin.login'))
    return render_template('admin/forgot.html')


@admin_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    import hashlib
    from models import PasswordReset
    row = PasswordReset.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not row or row.used or row.expires_at < datetime.utcnow():
        flash(pick('الرابط غير صالح أو انتهت صلاحيته. اطلب رابطاً جديداً.', 'The link is invalid or expired. Request a new one.'), 'error')
        return redirect(url_for('admin.forgot'))
    if request.method == 'POST':
        pw = request.form.get('new') or ''
        if len(pw) < 8:
            flash(pick('كلمة المرور 8 أحرف على الأقل.', 'The password needs at least 8 characters.'), 'error')
        elif pw != request.form.get('again'):
            flash(pick('كلمتا المرور غير متطابقتين.', 'The passwords do not match.'), 'error')
        else:
            u = db.session.get(User, row.user_id)
            u.set_password(pw)
            row.used = True
            db.session.commit()
            flash(pick('تغيّرت كلمة المرور. سجّل الدخول بها الآن.', 'The password was changed. Sign in with it now.'), 'ok')
            return redirect(url_for('admin.login'))
    return render_template('admin/reset.html', token=token)


@admin_bp.route('/logout')
def logout():
    lang = session.get('lang', 'ar')
    session.clear()
    session['lang'] = lang
    return redirect(url_for('admin.login'))


# ── اللوحة الرئيسية ──────────────────────────────────────────────────────────

@admin_bp.route('/')
@login_required
def dashboard():
    lang = session.get('lang', 'ar')
    forms = forms_query(include_templates=True).all()
    real = [f for f in forms if not f.is_template]
    ids = [f.id for f in real]
    base = Response.query.filter(Response.form_id.in_(ids or [0]), Response.is_test.is_(False))
    responses = base.all()
    by_form = Counter(r.form_id for r in responses)
    k = {
        'forms': len([f for f in real if not f.archived]),
        'open': len([f for f in real if f.status == 'open' and not f.archived]),
        'draft': len([f for f in real if f.status == 'draft' and not f.archived]),
        'closed': len([f for f in real if f.status == 'closed' and not f.archived]),
        'archived': len([f for f in real if f.archived]),
        'templates': len([f for f in forms if f.is_template]),
        'quizzes': len([f for f in real if f.s('quiz') and not f.archived]),
        'no_responses': len([f for f in real if not by_form.get(f.id) and not f.archived]),
        'responses': len(responses),
        'today': base.filter(Response.submitted_at >= period_range('today')).count(),
        'week': base.filter(Response.submitted_at >= period_range('week')).count(),
        'flagged': len([r for r in responses if r.flagged]),
        'views': sum(f.views or 0 for f in real),
        'subforms': len([f for f in real if f.parent_id]),
    }
    k['completion'] = round(100.0 * k['responses'] / k['views'], 1) if k['views'] else None
    sm = analytics.summary(responses, days=30, lang=lang)
    fmap = {f.id: f for f in real}
    top = [(fmap[fid], n) for fid, n in by_form.most_common(10) if fid in fmap]
    cats = defaultdict(lambda: {'forms': 0, 'n': 0})
    owners = defaultdict(lambda: {'forms': 0, 'n': 0, 'user': None})
    for f in real:
        if f.archived:
            continue
        c = cats[f.category or '']
        c['forms'] += 1
        c['n'] += by_form.get(f.id, 0)
        o = owners[f.owner_id or 0]
        o['forms'] += 1
        o['n'] += by_form.get(f.id, 0)
        o['user'] = f.owner
    recent = base.order_by(Response.submitted_at.desc()).limit(8).all()
    return render_template('admin/dashboard.html', k=k, sm=sm, top=top, cats=sorted(cats.items(), key=lambda x: -x[1]['n']),
                           owners=sorted(owners.items(), key=lambda x: -x[1]['n']), recent=recent, fmap=fmap)


# ── قائمة النماذج ────────────────────────────────────────────────────────────

@admin_bp.route('/forms')
@login_required
def forms():
    a = request.args
    q = forms_query(include_templates=a.get('tpl') == '1')
    if a.get('tpl') == '1':
        q = q.filter(Form.is_template.is_(True))
    if a.get('status') == 'archived':
        q = q.filter(Form.archived.is_(True))
    elif a.get('status') in ('open', 'draft', 'closed'):
        q = q.filter(Form.status == a['status'], Form.archived.is_(False))
    elif a.get('all') != '1':
        q = q.filter(Form.archived.is_(False))
    if 'category' in a:
        q = q.filter(db.func.coalesce(Form.category, '') == a['category'])
    if a.get('owner'):
        q = q.filter(Form.owner_id == int(a['owner']) if a['owner'].isdigit() else Form.owner_id.is_(None))
    if a.get('quiz') == '1':
        q = q.filter(Form.settings.like('%"quiz": true%'))
    if a.get('sub') == '1':
        q = q.filter(Form.parent_id.isnot(None))
    rows = q.order_by(Form.updated_at.desc()).all()
    counts = dict(db.session.query(Response.form_id, db.func.count(Response.id))
                  .filter(Response.is_test.is_(False)).group_by(Response.form_id).all())
    if a.get('empty') == '1':
        rows = [f for f in rows if not counts.get(f.id)]
    return render_template('admin/forms.html', rows=rows, counts=counts, args=a)


@admin_bp.route('/templates')
@login_required
def templates():
    rows = Form.query.filter(Form.is_template.is_(True)).order_by(Form.category, Form.title).all()
    return render_template('admin/templates.html', rows=rows)


@admin_bp.route('/forms/new', methods=['GET', 'POST'])
@login_required
def form_new():
    if request.method == 'POST':
        tid = request.form.get('template_id', type=int)
        if tid:
            src = get_form(tid, edit=False)
            f = _copy_form(src, title=request.form.get('title') or src.title, as_template=False)
            flash(pick('أُنشئ النموذج من القالب.', 'The form was created from the template.'), 'ok')
        else:
            title = (request.form.get('title') or '').strip() or pick('نموذج بلا عنوان', 'Untitled form')
            f = Form(title=title[:300], owner_id=current_user().id, category=(request.form.get('category') or '').strip()[:120] or None,
                     schema={'questions': normalize_schema({'questions': [{'type': 'short_text', 'title': pick('سؤال بلا عنوان', 'Untitled question')}]})['questions']},
                     settings={'accent': AppSetting.get('accent') or '#0C67EC', 'progress': True,
                               'lang': session.get('lang', 'ar')})
            db.session.add(f)
            db.session.commit()
        return redirect(url_for('admin.builder', fid=f.id))
    tpls = Form.query.filter(Form.is_template.is_(True)).order_by(Form.title).all()
    return render_template('admin/form_new.html', templates=tpls)


@admin_bp.route('/forms/import', methods=['GET', 'POST'])
@login_required
def form_import():
    if request.method == 'POST':
        text = request.form.get('text') or ''
        up = request.files.get('file')
        if up and up.filename:
            text = up.read(2 * 1024 * 1024).decode('utf-8-sig', 'replace')
        p = parse_paste(text)
        if not p['questions']:
            flash(pick('لم يُعثر على أي سؤال في النص. راجع الصيغة في الأمثلة.', 'No questions were found in the text. Check the format in the examples.'), 'error')
            return render_template('admin/form_import.html', text=text)
        settings = {'accent': AppSetting.get('accent') or '#0C67EC', 'progress': True, 'lang': session.get('lang', 'ar')}
        if p.get('settings'):
            settings.update({k: v for k, v in p['settings'].items() if k in SETTING_KEYS})
        if any((q.get('quiz') or {}).get('points') for q in p['questions']):
            settings['quiz'] = True
        title = (request.form.get('title') or '').strip() or p['title'] or pick('نموذج مستورد', 'Imported form')
        f = Form(title=title[:300], title_en=(p.get('title_en') or None), description=p['description'] or None,
                 owner_id=current_user().id, schema={'questions': p['questions']}, settings=settings)
        db.session.add(f)
        db.session.commit()
        flash(pick(f'أُنشئ النموذج: {len(p["questions"])} عنصراً.', f'The form was created: {len(p["questions"])} items.'), 'ok')
        return redirect(url_for('admin.builder', fid=f.id))
    return render_template('admin/form_import.html', text='')


@admin_bp.route('/api/parse', methods=['POST'])
@login_required
def api_parse():
    data = request.get_json(silent=True) or {}
    p = parse_paste(data.get('text') or '')
    lang = session.get('lang', 'ar')
    return jsonify({'ok': True, 'format': p['format'], 'title': p['title'], 'description': p['description'],
                    'warnings': p['warnings'],
                    'questions': [{'type': q['type'], 'type_label': TYPES[q['type']][1 if lang == 'en' else 0],
                                   'title': q['title'], 'required': q.get('required', False),
                                   'choices': [c['label'] for c in q.get('choices') or []],
                                   'rows': [r['label'] for r in q.get('rows') or []],
                                   'cols': [c['label'] for c in q.get('cols') or []],
                                   'points': (q.get('quiz') or {}).get('points')} for q in p['questions']]})


def _copy_form(src, title=None, as_template=False, parent_id=None):
    f = Form(title=(title or src.title)[:300], title_en=src.title_en, description=src.description, category=src.category,
             is_template=as_template, status='draft', owner_id=current_user().id, parent_id=parent_id,
             source_id=src.id, schema=copy.deepcopy(src.schema), settings=copy.deepcopy(src.settings or {}))
    db.session.add(f)
    db.session.commit()
    return f


@admin_bp.route('/forms/<int:fid>/duplicate', methods=['POST'])
@login_required
def form_duplicate(fid):
    src = get_form(fid, edit=False)
    f = _copy_form(src, title=src.title + pick(' (نسخة)', ' (copy)'))
    flash(pick('نُسخ النموذج. النسخة مسودة حتى تفتحها.', 'The form was copied. The copy stays a draft until you open it.'), 'ok')
    return redirect(url_for('admin.builder', fid=f.id))


@admin_bp.route('/forms/<int:fid>/save-template', methods=['POST'])
@login_required
def form_save_template(fid):
    src = get_form(fid)
    f = _copy_form(src, title=src.title, as_template=True)
    flash(pick('حُفظ قالباً جديداً في «القوالب».', 'Saved as a new template in Templates.'), 'ok')
    return redirect(url_for('admin.templates') + f'#t{f.id}')


@admin_bp.route('/forms/<int:fid>/subform', methods=['POST'])
@login_required
def form_subform(fid):
    parent = get_form(fid)
    f = Form(title=pick('نموذج فرعي — ', 'Sub-form — ') + parent.title, owner_id=current_user().id, parent_id=parent.id,
             category=parent.category, schema=normalize_schema({'questions': [{'type': 'short_text', 'title': 'Untitled question' if parent.s('lang') == 'en' else 'سؤال بلا عنوان'}]}),
             settings={'accent': parent.s('accent') or '#0C67EC', 'progress': True, 'lang': parent.s('lang', 'ar')})
    db.session.add(f)
    db.session.commit()
    flash(pick('أُنشئ نموذج فرعي مرتبط بالنموذج الأم.', 'A sub-form linked to the parent form was created.'), 'ok')
    return redirect(url_for('admin.builder', fid=f.id))


def _delete_block(f):
    """سبب منع الحذف (ar, en) أو None."""
    if f.responses.count():
        return ('له إجابات — احذف الإجابات أولاً أو أرشفه بدلاً من حذفه', 'it has responses — delete them first, or archive it instead')
    if f.children.count():
        return ('له نماذج فرعية', 'it has sub-forms')
    if f.invitations.count():
        return ('له مدعوون — احذف الدعوات أولاً أو أرشفه', 'it has invited people — delete the invitations first, or archive it')
    return None


@admin_bp.route('/forms/<int:fid>/delete', methods=['POST'])
@login_required
def form_delete(fid):
    f = get_form(fid)
    why = _delete_block(f)
    if why:
        flash(pick(f'لا يمكن حذف «{f.title}»: {why[0]}.', f'"{f.title}" cannot be deleted: {why[1]}.'), 'error')
        return redirect(request.referrer or url_for('admin.forms'))
    tpl = f.is_template
    MediaFile.query.filter_by(form_id=f.id).delete()
    db.session.delete(f)
    db.session.commit()
    flash(pick('حُذف.', 'Deleted.'), 'ok')
    return redirect(url_for('admin.templates' if tpl else 'admin.forms'))


# ── المحرّر ──────────────────────────────────────────────────────────────────

SETTING_KEYS = {
    'lang', 'bilingual', 'accent', 'font', 'bg_color', 'bg_image', 'bg_video', 'bg_music', 'bg_overlay', 'header_image',
    'logo', 'progress', 'shuffle', 'one_per_device', 'one_per_email', 'require_email', 'email_domains',
    'filler_fields', 'filler_intro', 'quiz', 'show_score', 'show_answers', 'pass_mark', 'confirmation', 'confirmation_en',
    'redirect_url', 'allow_another', 'open_at', 'close_at', 'max_responses', 'closed_message', 'notify_emails',
    'send_copy', 'autosave', 'time_limit', 'card_style', 'music_volume', 'question_numbers', 'welcome', 'welcome_en',
    'show_subforms', 'login_method', 'logo_hide', 'logo_size', 'logo_align', 'org_name_hide', 'share_image',
}
MEDIA_KEYS = {'bg_image', 'bg_video', 'bg_music', 'header_image', 'logo', 'share_image'}


def _clean_settings(s):
    out = {}
    for k, v in (s or {}).items():
        if k not in SETTING_KEYS:
            continue
        if k == 'accent' or k == 'bg_color':
            if isinstance(v, str) and re.fullmatch(r'#[0-9A-Fa-f]{6}', v):
                out[k] = v
        elif k == 'filler_fields':
            fields = []
            for fdef in v if isinstance(v, list) else []:
                if not isinstance(fdef, dict):
                    continue
                key = re.sub(r'[^A-Za-z0-9_]', '', str(fdef.get('key') or ''))[:30] or f'f{len(fields) + 1}'
                fields.append({'key': key, 'label': str(fdef.get('label') or key)[:200],
                               'label_en': str(fdef.get('label_en') or '')[:200],
                               'type': fdef.get('type') if fdef.get('type') in ('text', 'email', 'phone', 'number', 'date', 'select') else 'text',
                               'options': str(fdef.get('options') or '')[:1000], 'required': bool(fdef.get('required'))})
            out[k] = fields[:20]
        elif k in ('max_responses', 'time_limit', 'pass_mark', 'music_volume'):
            try:
                out[k] = max(0, int(float(v))) if v not in (None, '') else None
            except (TypeError, ValueError):
                pass
        elif k in MEDIA_KEYS:
            # ملف مرفوع في النظام أو رابط مباشر فقط
            out[k] = v if isinstance(v, str) and re.match(r'^(https?://|/media/\d+/[\w-]+$)', v) else ''
        elif k == 'logo_size':
            out[k] = v if v in ('sm', 'lg') else ''
        elif k == 'logo_align':
            out[k] = v if v == 'center' else ''
        elif k in ('redirect_url',):
            out[k] = v if isinstance(v, str) and re.match(r'^https?://', v) else ''
        elif isinstance(v, (bool, int, float)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)[:5000]
    return out


def _form_json(f):
    return {'id': f.id, 'slug': f.slug, 'title': f.title, 'title_en': f.title_en or '', 'description': f.description or '',
            'category': f.category or '', 'status': f.status, 'is_template': f.is_template, 'parent_id': f.parent_id,
            'schema': f.schema or {'questions': []}, 'settings': f.settings or {},
            'updated_at': f.updated_at.isoformat() if f.updated_at else ''}


@admin_bp.route('/forms/<int:fid>/edit')
@login_required
def builder(fid):
    f = get_form(fid)
    from mail import graph_status
    others = forms_query().filter(Form.id != f.id, Form.archived.is_(False)).order_by(Form.title).all()
    media = MediaFile.query.filter(MediaFile.form_id == f.id, MediaFile.kind.in_(['image', 'audio', 'video'])) \
        .order_by(MediaFile.id.desc()).all()
    cats = sorted({c for (c,) in db.session.query(Form.category).filter(Form.category.isnot(None)).distinct() if c})
    import msauth
    return render_template('admin/builder.html', f=f, data=_form_json(f), others=others, media=media, cats=cats,
                           mail_ready=graph_status()['ready'], ms_ready=msauth.ready(), n_responses=f.response_count,
                           public_url=_public_url(f))


def _public_url(f, suffix=''):
    from flask import current_app
    base = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    return f'{base}/f/{f.slug}{suffix}'


@admin_bp.route('/api/forms/<int:fid>', methods=['GET', 'POST'])
@login_required
def api_form(fid):
    f = get_form(fid)
    if request.method == 'GET':
        return jsonify({'ok': True, 'form': _form_json(f)})
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': pick('بيانات غير صالحة.', 'Invalid data.')}), 400
    if 'title' in data:
        f.title = (str(data.get('title') or '').strip() or pick('نموذج بلا عنوان', 'Untitled form'))[:300]
    for k, n in (('title_en', 300), ('description', 20000), ('category', 120)):
        if k in data:
            setattr(f, k, (str(data.get(k) or '').strip()[:n]) or None)
    if 'schema' in data:
        f.schema = normalize_schema(data['schema'])
    if 'settings' in data:
        f.settings = _clean_settings(data['settings'])
    if 'parent_id' in data:
        pid = data.get('parent_id')
        pid = int(pid) if str(pid or '').isdigit() else None
        if pid and pid != f.id:
            p = db.session.get(Form, pid)
            # لا حلقات: الأم لا تكون أحد فروع هذا النموذج
            cur, ok = p, True
            while cur is not None:
                if cur.id == f.id:
                    ok = False
                    break
                cur = cur.parent
            f.parent_id = pid if (p and ok and can_edit(p)) else f.parent_id
        else:
            f.parent_id = None
    if data.get('status') in ('draft', 'open', 'closed'):
        f.status = data['status']
    f.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'form': _form_json(f)})


@admin_bp.route('/api/media', methods=['POST'])
@login_required
def api_media():
    up = request.files.get('file')
    kind = request.form.get('kind') or 'image'
    if kind not in MEDIA_LIMITS or not up or not up.filename:
        return jsonify({'ok': False, 'error': pick('اختر ملفاً.', 'Choose a file.')}), 400
    data = up.read()
    mime = up.mimetype or 'application/octet-stream'
    if not mime.startswith(MEDIA_TYPES[kind]):
        return jsonify({'ok': False, 'error': pick('نوع الملف غير مناسب لهذا الحقل.', 'This file type does not fit this field.')}), 400
    if len(data) > MEDIA_LIMITS[kind] * 1024 * 1024:
        return jsonify({'ok': False, 'error': pick(f'الملف أكبر من {MEDIA_LIMITS[kind]} ميغابايت.', f'The file is larger than {MEDIA_LIMITS[kind]} MB.')}), 400
    fid = request.form.get('form_id', type=int)
    if fid:
        get_form(fid)
    m = MediaFile(kind=kind, filename=up.filename[:255], mime=mime, size=len(data), data=data, form_id=fid)
    db.session.add(m)
    db.session.commit()
    return jsonify({'ok': True, 'id': m.id, 'url': m.url, 'name': m.filename, 'mime': m.mime, 'kind': kind})


@admin_bp.route('/forms/<int:fid>/qr.svg')
@login_required
def form_qr(fid):
    import qr
    f = get_form(fid, edit=False)
    lang = session.get('lang', 'ar')
    plain = request.args.get('plain') == '1'
    body = qr.svg(_public_url(f), f.title_for(lang), qr.org_name(lang), qr.logo_data_uri(), caption=not plain)
    resp = FlaskResponse(body, mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'no-store'
    if request.args.get('download'):
        resp.headers['Content-Disposition'] = f'attachment; filename="form-{f.slug}-qr.svg"'
    return resp


@admin_bp.route('/forms/<int:fid>/qr/print')
@login_required
def form_qr_print(fid):
    f = get_form(fid, edit=False)
    return render_template('admin/qr_print.html', f=f, public_url=_public_url(f))


# ── الإجراءات الجماعية ───────────────────────────────────────────────────────

@admin_bp.route('/bulk/<entity>', methods=['POST'])
@login_required
def bulk(entity):
    ids = [int(i) for i in request.form.getlist('ids') if i.isdigit()]
    action = request.form.get('action')
    done, skipped = 0, []
    back = request.referrer or url_for('admin.dashboard')
    if entity in ('forms', 'templates'):
        for f in Form.query.filter(Form.id.in_(ids or [0])).all():
            if not can_edit(f):
                skipped.append(f.title)
                continue
            if action in ('open', 'closed', 'draft'):
                f.status = action
            elif action == 'archive':
                f.archived = True
            elif action == 'unarchive':
                f.archived = False
            elif action == 'duplicate':
                _copy_form(f, title=f.title + pick(' (نسخة)', ' (copy)'), as_template=f.is_template)
            elif action == 'template':
                _copy_form(f, title=f.title, as_template=True)
            elif action == 'delete':
                why = _delete_block(f)
                if why:
                    skipped.append(f'{f.title} ({pick(why[0], why[1])})')
                    continue
                MediaFile.query.filter_by(form_id=f.id).delete()
                db.session.delete(f)
            else:
                continue
            done += 1
    elif entity == 'responses':
        for r in Response.query.filter(Response.id.in_(ids or [0])).all():
            if not can_edit(r.form):
                continue
            if action == 'delete':
                if r.child_responses:
                    for c in r.child_responses:
                        c.parent_response_id = None
                MediaFile.query.filter_by(response_id=r.id).delete()
                db.session.delete(r)
            elif action == 'star':
                r.starred = True
            elif action == 'unstar':
                r.starred = False
            elif action == 'unflag':
                r.flagged = False
            elif action == 'real':
                r.is_test = False
            else:
                continue
            done += 1
    elif entity == 'users':
        me = current_user()
        if not me.is_admin:
            abort(403)
        admins = User.query.filter_by(role='admin', active=True).count()
        for u in User.query.filter(User.id.in_(ids or [0])).all():
            if action in ('deactivate', 'delete') and u.id == me.id:
                skipped.append(pick(f'{u.username} (حسابك الحالي)', f'{u.username} (your own account)'))
                continue
            if action in ('deactivate', 'delete') and u.is_admin and u.active and admins <= 1:
                skipped.append(pick(f'{u.username} (آخر مسؤول)', f'{u.username} (the last administrator)'))
                continue
            if action == 'activate':
                u.active = True
            elif action == 'deactivate':
                if u.is_admin and u.active:
                    admins -= 1
                u.active = False
            elif action == 'delete':
                if u.forms.count():
                    skipped.append(pick(f'{u.username} (له نماذج — عطّله بدلاً من حذفه)', f'{u.username} (owns forms — deactivate instead)'))
                    continue
                if u.is_admin and u.active:
                    admins -= 1
                db.session.delete(u)
            else:
                continue
            done += 1
    elif entity in ('people', 'groups', 'invitations'):
        import people as people_mod
        done, skipped = people_mod.bulk(entity, ids, action, request.form)
    else:
        abort(404)
    db.session.commit()
    if done:
        flash(pick(f'تم تنفيذ الإجراء على {done} عنصراً.', f'Done for {done} item(s).'), 'ok')
    if skipped:
        flash(pick('لم يُنفَّذ على: ', 'Skipped: ') + '، '.join(skipped[:10]), 'error')
    return redirect(back)


# ── الإجابات ─────────────────────────────────────────────────────────────────

@admin_bp.route('/forms/<int:fid>/responses')
@login_required
def responses(fid):
    f = get_form(fid)
    rs = filtered_responses(f, request.args)[::-1]
    lang = session.get('lang', 'ar')
    cols = [q for q in f.questions if q['type'] not in NO_ANSWER][:6]
    return render_template('admin/responses.html', f=f, rows=rs, cols=cols, answer_text=answer_text, qtitle=qtitle, lang=lang,
                           args=request.args, n_test=f.responses.filter_by(is_test=True).count())


@admin_bp.route('/responses')
@login_required
def all_responses():
    forms = {f.id: f for f in forms_query().all()}
    q = response_filters(Response.query.filter(Response.form_id.in_(list(forms) or [0])), request.args)
    if request.args.get('form', type=int):
        q = q.filter(Response.form_id == request.args.get('form', type=int))
    rows = q.order_by(Response.submitted_at.desc()).limit(2000).all()
    return render_template('admin/all_responses.html', rows=rows, forms=forms, args=request.args)


@admin_bp.route('/responses/<int:rid>')
@login_required
def response_view(rid):
    r = db.session.get(Response, rid) or abort(404)
    f = get_form(r.form_id)
    lang = session.get('lang', 'ar')
    _, shown, _ = walk(f.questions, r.answers or {})
    detail = {}
    if f.s('quiz'):
        _, _, detail = grade(f.questions, r.answers or {}, r.manual_points)
    ids = [x for (x,) in db.session.query(Response.id).filter_by(form_id=f.id).order_by(Response.id).all()]
    i = ids.index(r.id)
    return render_template('admin/response.html', r=r, f=f, shown=shown, detail=detail, answer_text=answer_text,
                           qtitle=qtitle, lang=lang, prev_id=ids[i - 1] if i > 0 else None,
                           next_id=ids[i + 1] if i + 1 < len(ids) else None, pos=i + 1, total=len(ids))


@admin_bp.route('/responses/<int:rid>/grade', methods=['POST'])
@login_required
def response_grade(rid):
    r = db.session.get(Response, rid) or abort(404)
    f = get_form(r.form_id)
    manual = dict(r.manual_points or {})
    for q in f.questions:
        key = f'pts_{q["id"]}'
        if key in request.form:
            v = request.form.get(key, '').strip()
            if v == '':
                manual.pop(q['id'], None)
            else:
                try:
                    manual[q['id']] = float(v)
                except ValueError:
                    pass
    r.manual_points = manual
    r.score, r.max_score, _ = grade(f.questions, r.answers or {}, manual)
    db.session.commit()
    flash(pick('حُفظت الدرجات.', 'The marks were saved.'), 'ok')
    return redirect(url_for('admin.response_view', rid=r.id))


@admin_bp.route('/forms/<int:fid>/export.<fmt>')
@login_required
def export(fid, fmt):
    f = get_form(fid)
    rs = filtered_responses(f, request.args)
    lang = session.get('lang', 'ar')
    name = re.sub(r'[^\w\-]+', '_', f.title_en or f'form-{f.id}')[:60] or f'form-{f.id}'
    if fmt == 'csv':
        data, mime = exporter.to_csv(f, rs, lang), 'text/csv; charset=utf-8'
    elif fmt == 'xlsx':
        data, mime = exporter.to_xlsx(f, rs, lang), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'json':
        data = json.dumps({'form': _form_json(f), 'responses': [
            {'id': r.id, 'submitted_at': exporter.local(r.submitted_at), 'email': r.email, 'filler': r.filler,
             'answers': r.answers, 'score': r.score, 'max_score': r.max_score, 'device': r.device, 'browser': r.browser,
             'os': r.os, 'ip': r.ip, 'duration_sec': r.duration_sec} for r in rs]}, ensure_ascii=False, indent=1).encode('utf-8')
        mime = 'application/json'
    elif fmt == 'form':     # بنية النموذج فقط — تُستورد في أي نظام نماذج آخر من صفحة اللصق
        data = json.dumps({'title': f.title, 'title_en': f.title_en, 'description': f.description,
                           'settings': f.settings, 'questions': f.questions}, ensure_ascii=False, indent=1).encode('utf-8')
        mime, fmt = 'application/json', 'form.json'
    else:
        abort(404)
    resp = FlaskResponse(data, mimetype=mime)
    resp.headers['Content-Disposition'] = f'attachment; filename="{name}-{datetime.now():%Y-%m-%d}.{fmt}"'
    return resp


# ── التحليل ──────────────────────────────────────────────────────────────────

@admin_bp.route('/forms/<int:fid>/analysis')
@login_required
def analysis(fid):
    f = get_form(fid)
    lang = session.get('lang', 'ar')
    rs = filtered_responses(f, request.args)
    stats = analytics.question_stats(f, rs, lang)
    sm = analytics.summary(rs, days=30, lang=lang)
    ct = None
    a, b = request.args.get('a'), request.args.get('b')
    if a and b:
        ct = analytics.crosstab(f, rs, a, b, lang)
        if ct and request.args.get('ct') == 'csv':
            headers = [ct['a_title'] + ' \\ ' + ct['b_title']] + ct['cols'] + [pick('المجموع', 'Total')]
            rows = [[r['label']] + r['counts'] + [r['total']] for r in ct['rows']]
            rows.append([pick('المجموع', 'Total')] + ct['col_totals'] + [ct['grand']])
            resp = FlaskResponse(exporter.table_csv(headers, rows), mimetype='text/csv; charset=utf-8')
            resp.headers['Content-Disposition'] = f'attachment; filename="crosstab-{f.id}.csv"'
            return resp
    quiz = None
    if f.s('quiz'):
        pcts = [r.percent for r in rs if r.percent is not None]
        bins = [0] * 10
        for p in pcts:
            bins[min(9, int(p // 10))] += 1
        pm = f.s('pass_mark')
        quiz = {'n': len(pcts), 'avg': round(sum(pcts) / len(pcts), 1) if pcts else None,
                'max': max(pcts) if pcts else None, 'min': min(pcts) if pcts else None,
                'bins': [{'label': f'{i * 10}–{i * 10 + 10}', 'n': n} for i, n in enumerate(bins)],
                'pass_mark': pm, 'passed': len([p for p in pcts if pm and p >= pm]) if pm else None}
    crossable = analytics.crossable(f)
    seg_questions = [q for q in crossable if analytics.categories(q, lang)]
    seg_cats = {q['id']: analytics.categories(q, lang) for q in seg_questions}
    return render_template('admin/analysis.html', f=f, stats=stats, sm=sm, ct=ct, quiz=quiz, rs=rs, args=request.args,
                           crossable=crossable, qtitle=qtitle, lang=lang, seg_questions=seg_questions, seg_cats=seg_cats)


# ── المقارنة بين النماذج ─────────────────────────────────────────────────────

@admin_bp.route('/compare')
@login_required
def compare():
    lang = session.get('lang', 'ar')
    all_forms = forms_query().order_by(Form.updated_at.desc()).all()
    ids = [int(i) for i in request.args.getlist('ids') if i.isdigit()]
    if request.args.get('category') is not None and not ids:
        ids = [f.id for f in all_forms if (f.category or '') == request.args['category']]
    chosen = [f for f in all_forms if f.id in ids]
    by = request.args.get('by') or 'form'
    result = None
    if chosen:
        rbf = {f.id: response_filters(Response.query.filter_by(form_id=f.id), request.args).all() for f in chosen}
        metrics = [analytics.form_metrics(f, rbf[f.id]) for f in chosen]
        groups = analytics.group_metrics(chosen, rbf, by, lang)
        shared = [analytics.compare_question(g, rbf, lang) for g in analytics.shared_questions(chosen, lang)]
        monthly = analytics.monthly_series(chosen, rbf, lang)
        devices = []
        for f in chosen:
            c = Counter(r.device or 'desktop' for r in rbf[f.id])
            devices.append({'label': f.title_for(lang), 'mobile': c.get('mobile', 0), 'tablet': c.get('tablet', 0),
                            'desktop': c.get('desktop', 0) + c.get('bot', 0)})
        result = {'metrics': metrics, 'groups': groups, 'shared': shared, 'monthly': monthly, 'devices': devices}
    cats = sorted({f.category or '' for f in all_forms})
    return render_template('admin/compare.html', all_forms=all_forms, chosen=chosen, ids=ids, by=by, result=result,
                           args=request.args, cats=cats)


# ── المستخدمون والحساب ───────────────────────────────────────────────────────

@admin_bp.route('/users', methods=['GET', 'POST'])
@admin_required
def users():
    if request.method == 'POST':
        uid = request.form.get('id', type=int)
        username = (request.form.get('username') or '').strip()
        pw = request.form.get('password') or ''
        role = 'admin' if request.form.get('role') == 'admin' else 'editor'
        if not re.fullmatch(r'[A-Za-z0-9_.@\-]{3,80}', username):
            flash(pick('اسم المستخدم من 3 أحرف على الأقل (أحرف إنجليزية وأرقام و. _ - @).', 'The user name needs at least 3 characters (letters, digits, . _ - @).'), 'error')
            return redirect(url_for('admin.users'))
        clash = User.query.filter(db.func.lower(User.username) == username.lower(), User.id != (uid or 0)).first()
        if clash:
            flash(pick('اسم المستخدم مستخدم من قبل.', 'This user name is already taken.'), 'error')
            return redirect(url_for('admin.users'))
        if uid:
            u = db.session.get(User, uid) or abort(404)
            if u.is_admin and role != 'admin' and User.query.filter_by(role='admin', active=True).count() <= 1:
                flash(pick('لا يمكن تحويل آخر مسؤول إلى محرّر.', 'The last administrator cannot become an editor.'), 'error')
                return redirect(url_for('admin.users'))
        else:
            if len(pw) < 8:
                flash(pick('كلمة المرور 8 أحرف على الأقل.', 'The password needs at least 8 characters.'), 'error')
                return redirect(url_for('admin.users'))
            u = User(username=username)
            db.session.add(u)
        u.username = username
        u.name = (request.form.get('name') or '').strip()[:200] or None
        u.email = (request.form.get('email') or '').strip()[:255] or None
        u.role = role
        if pw:
            if len(pw) < 8:
                flash(pick('كلمة المرور 8 أحرف على الأقل.', 'The password needs at least 8 characters.'), 'error')
                db.session.rollback()
                return redirect(url_for('admin.users'))
            u.set_password(pw)
        db.session.commit()
        flash(pick('حُفظ المستخدم.', 'The user was saved.'), 'ok')
        return redirect(url_for('admin.users'))
    rows = User.query.order_by(User.username).all()
    counts = dict(db.session.query(Form.owner_id, db.func.count(Form.id)).group_by(Form.owner_id).all())
    return render_template('admin/users.html', rows=rows, counts=counts)


@admin_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    u = current_user()
    if request.method == 'POST':
        if not u.check_password(request.form.get('current') or ''):
            flash(pick('كلمة المرور الحالية غير صحيحة.', 'The current password is wrong.'), 'error')
        elif len(request.form.get('new') or '') < 8:
            flash(pick('كلمة المرور الجديدة 8 أحرف على الأقل.', 'The new password needs at least 8 characters.'), 'error')
        elif request.form.get('new') != request.form.get('again'):
            flash(pick('كلمتا المرور غير متطابقتين.', 'The passwords do not match.'), 'error')
        else:
            u.set_password(request.form['new'])
            u.name = (request.form.get('name') or '').strip()[:200] or u.name
            db.session.commit()
            session['sv'] = u.session_ver          # هذه الجلسة تبقى، والجلسات الأخرى تخرج
            flash(pick('تغيّرت كلمة المرور.', 'The password was changed.'), 'ok')
        return redirect(url_for('admin.account'))
    return render_template('admin/account.html', u=u)


# ── الإعدادات ────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    from mail import graph_status, send_email
    if request.method == 'POST':
        if request.form.get('action') == 'test_mail':
            to = (request.form.get('to') or '').strip()
            res = send_email([to], pick('رسالة تجربة من نظام النماذج', 'Test message from the forms system'),
                             '<p dir="rtl">' + pick('هذه رسالة تجربة. البريد يعمل.', 'This is a test message. Mail works.') + '</p>', kind='test')
            flash(pick('أُرسلت رسالة التجربة.', 'The test message was sent.') if res.ok else
                  pick('تعذّر الإرسال. افتح «حساب Microsoft» واضغط «فحص الاتصال»، وتأكد من بريد المرسل.',
                       'Sending failed. Open "Microsoft account", press "Test connection", and check the sender mailbox.'), 'ok' if res.ok else 'error')
            return redirect(url_for('admin.settings'))
        AppSetting.set('org_name_ar', (request.form.get('org_name_ar') or '').strip()[:200])
        AppSetting.set('org_name_en', (request.form.get('org_name_en') or '').strip()[:200])
        acc = request.form.get('accent') or ''
        if re.fullmatch(r'#[0-9A-Fa-f]{6}', acc):
            AppSetting.set('accent', acc)
        up = request.files.get('logo')
        if up and up.filename:
            data = up.read()
            if not (up.mimetype or '').startswith('image/') or len(data) > 4 * 1024 * 1024:
                flash(pick('الشعار يجب أن يكون صورة أصغر من 4 ميغابايت.', 'The logo must be an image under 4 MB.'), 'error')
            else:
                m = MediaFile(kind='logo', filename=up.filename[:255], mime=up.mimetype, size=len(data), data=data)
                db.session.add(m)
                db.session.flush()
                AppSetting.set('org_logo_id', m.id)
        if request.form.get('remove_logo'):
            AppSetting.set('org_logo_id', '')
        db.session.commit()
        flash(pick('حُفظت الإعدادات.', 'Settings saved.'), 'ok')
        return redirect(url_for('admin.settings'))
    logs = EmailLog.query.order_by(EmailLog.id.desc()).limit(30).all()
    import msauth
    return render_template('admin/settings.html', mail=graph_status(), logs=logs, ms_redirect=msauth.redirect_uri(),
                           org_ar=AppSetting.get('org_name_ar') or '', org_en=AppSetting.get('org_name_en') or '',
                           acc=AppSetting.get('accent') or '#0C67EC')


@admin_bp.route('/settings/microsoft', methods=['GET', 'POST'])
@admin_required
def settings_microsoft():
    """ربط حساب Microsoft للمدرسة: المعرّفات والسر (يُحفظ في ملف الإعدادات على الخادم ولا يُعرض)، وفحص الاتصال."""
    import msauth
    import tenant
    checks = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            vals = {}
            guid = re.compile(r'^[0-9a-fA-F-]{36}$|^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
            tid = (request.form.get('tenant') or '').strip()
            cid = (request.form.get('client') or '').strip()
            sender = (request.form.get('sender') or '').strip()
            secret = (request.form.get('secret') or '').strip()
            if tid and not guid.match(tid):
                flash(pick('معرّف الجهة غير صحيح؛ انسخه كما هو من صفحة التطبيق في Azure.', 'The tenant ID is not valid; copy it as shown on the app page in Azure.'), 'error')
                return redirect(url_for('admin.settings_microsoft'))
            if cid and not re.match(r'^[0-9a-fA-F-]{36}$', cid):
                flash(pick('معرّف التطبيق غير صحيح؛ انسخه كما هو من صفحة التطبيق في Azure.', 'The application ID is not valid; copy it as shown on the app page in Azure.'), 'error')
                return redirect(url_for('admin.settings_microsoft'))
            if sender and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', sender):
                flash(pick('بريد المرسل غير صحيح.', 'The sender mailbox is not valid.'), 'error')
                return redirect(url_for('admin.settings_microsoft'))
            vals.update(MS_TENANT_ID=tid, MS_CLIENT_ID=cid, MS_SENDER_EMAIL=sender)
            if secret:
                vals['MS_CLIENT_SECRET'] = secret
            if request.form.get('clear_secret'):
                vals['MS_CLIENT_SECRET'] = ''
            tenant.save(vals)
            flash(pick('حُفظت الإعدادات وطُبِّقت فوراً.', 'The settings were saved and applied at once.'), 'ok')
            return redirect(url_for('admin.settings_microsoft') + '#test')
        if action == 'test':
            checks = tenant.test()
    return render_template('admin/settings_microsoft.html', st=tenant.status(), checks=checks, redirect_uri=msauth.redirect_uri())


@admin_bp.route('/help')
@login_required
def help_page():
    return render_template('admin/help.html')


import people as _people  # noqa: E402  — مسارات المستهدفين والدعوات على admin_bp نفسه
_people.register(admin_bp)
