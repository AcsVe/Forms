"""الصفحات العامة: تعبئة النموذج بلا دخول، أو بعد التحقق من البريد وإدخال بيانات المستجيب، والإرسال، وصفحة الشكر."""
import base64
import hashlib
import json
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta

from flask import (Blueprint, Response as FlaskResponse, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import uaparse
from blueprints.common import can_edit, current_user
from models import EmailCode, Form, Invitation, MediaFile, Person, Response, db
from schema import NO_ANSWER, answer_text, grade, qtitle, validate

public_bp = Blueprint('public', __name__)

_RATE = defaultdict(list)
ACCEPT = {'image': ('image/',), 'pdf': ('application/pdf',), 'media': ('audio/', 'video/'),
          'doc': ('application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument',
                  'application/vnd.ms-excel', 'application/vnd.ms-powerpoint', 'text/plain', 'image/')}


def _ip():
    return (request.headers.get('CF-Connecting-IP') or request.remote_addr or '')[:64]


def _limited(key, n, per):
    now = time.time()
    _RATE[key] = [t for t in _RATE[key] if now - t < per]
    if len(_RATE[key]) >= n:
        return True
    _RATE[key].append(now)
    return False


def _form_or_404(slug):
    f = Form.query.filter_by(slug=slug).first()
    # القالب يُعرض معاينةً فقط لمن دخل لوحة الإدارة
    if not f or (f.is_template and not (request.args.get('preview') == '1' and current_user())):
        abort(404)
    return f


def _flang(f):
    """لغة واجهة صفحة النموذج: ما اختاره المستجيب، وإلا لغة النموذج."""
    chosen = request.args.get('lang') or session.get(f'fl_{f.slug}')
    if chosen in ('ar', 'en') and (f.s('bilingual') or chosen == f.s('lang', 'ar')):
        return chosen
    return f.s('lang', 'ar') if f.s('lang') in ('ar', 'en') else 'ar'


def T(lang):
    return lambda ar, en: en if lang == 'en' else ar


def _preview(f):
    return request.args.get('preview') == '1' and (can_edit(f) or (f.is_template and current_user() is not None))


def _gates(f):
    """إلى أين يُحوَّل المستجيب قبل النموذج (أو None)."""
    if f.s('require_email') and not (session.get('fv') or {}).get(f.slug):
        return url_for('public.login', slug=f.slug, **_keep_args())
    if f.s('filler_fields') and f.slug not in (session.get('ff') or {}):
        return url_for('public.details', slug=f.slug, **_keep_args())
    return None


def _invitation(f):
    """دعوة هذا المتصفح لهذا النموذج (من ?inv= أو من الجلسة)."""
    tok = request.args.get('inv') or (session.get('inv') or {}).get(f.slug)
    if not tok:
        return None
    inv = Invitation.query.filter_by(token=str(tok)[:40], form_id=f.id).first()
    if inv and request.args.get('inv'):
        d = dict(session.get('inv') or {})
        d[f.slug] = inv.token
        session['inv'] = d
    return inv


def _audience_block(f, inv, lang):
    """رسالة المنع إن كان النموذج للمدعوين فقط والمستجيب ليس منهم (أو None)."""
    L = T(lang)
    email = (session.get('fv') or {}).get(f.slug)
    if not inv and email:
        inv = Invitation.query.join(Person).filter(Invitation.form_id == f.id, db.func.lower(Person.email) == email).first()
    if f.s('audience_only') and not inv:
        return L('هذا النموذج للمدعوين فقط. افتحه من الرابط الذي وصلك في الدعوة.',
                 'This form is for invited people only. Open it from the link in your invitation.')
    if inv and inv.responded_at and not f.s('allow_another'):
        return L('شكراً لك، سبق أن أرسلت إجابتك على هذا النموذج.', 'Thank you, you have already answered this form.')
    return None


def _keep_args():
    return dict(request.args.items())


@public_bp.route('/f/<slug>')
def fill(slug):
    f = _form_or_404(slug)
    lang = _flang(f)
    preview = _preview(f)
    if request.args.get('lang') in ('ar', 'en'):
        session[f'fl_{f.slug}'] = request.args['lang']
    ok, why_ar, why_en = f.is_accepting()
    if not ok and not preview:
        return render_template('public/closed.html', f=f, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                               msg=f.s('closed_message') or (why_en if lang == 'en' else why_ar)), 200
    inv = _invitation(f)
    if inv and not inv.opened_at and not preview:
        inv.opened_at = datetime.utcnow()
        db.session.commit()
    if not (inv and f.s('audience_only')) or f.s('require_email'):
        gate = _gates(f)
        if gate:
            return redirect(gate)
    elif f.s('filler_fields') and f.slug not in (session.get('ff') or {}):
        return redirect(url_for('public.details', slug=f.slug, **_keep_args()))
    if not preview:
        block = _audience_block(f, inv, lang)
        if block:
            return render_template('public/closed.html', f=f, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl', msg=block)
    email = (session.get('fv') or {}).get(f.slug)
    if not preview and f.s('one_per_email') and email and \
            Response.query.filter_by(form_id=f.id, email=email, is_test=False).first():
        return render_template('public/closed.html', f=f, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                               msg=T(lang)('سبق أن أرسلت إجابتك على هذا النموذج بهذا البريد.', 'You have already answered this form with this email.'))
    if not preview and f.s('one_per_device') and request.cookies.get(f'fd_{f.slug}'):
        return render_template('public/closed.html', f=f, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                               msg=T(lang)('سبق أن أُرسلت إجابة على هذا النموذج من هذا الجهاز.', 'A response to this form was already sent from this device.'))
    if not preview:
        Form.query.filter_by(id=f.id).update({Form.views: Form.views + 1})
        db.session.commit()
    session[f'st_{f.slug}'] = int(time.time())
    data = {'slug': f.slug, 'title': f.title, 'title_en': f.title_en or '', 'description': f.description or '',
            'questions': strip_quiz(f.questions), 'settings': _public_settings(f), 'lang': lang, 'preview': preview,
            'parent': request.args.get('parent') or '', 'submit_url': url_for('public.submit', slug=f.slug),
            'start_url': url_for('public.start', slug=f.slug)}
    return render_template('public/fill.html', f=f, data=data, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                           preview=preview, embed=request.args.get('embed') == '1', email=email)


def _public_settings(f):
    s = dict(f.settings or {})
    for k in ('notify_emails', 'email_domains'):
        s.pop(k, None)
    if s.get('quiz'):          # الإجابات الصحيحة لا تصل إلى المتصفح
        s['quiz'] = True
    return s


@public_bp.app_template_global()
def strip_quiz(questions):
    out = []
    for q in questions:
        q = dict(q)
        if 'quiz' in q:
            q['quiz'] = {'points': (q['quiz'] or {}).get('points')}
        out.append(q)
    return out


@public_bp.route('/f/<slug>/start', methods=['POST'])
def start(slug):
    f = Form.query.filter_by(slug=slug).first()
    if f and request.args.get('preview') != '1':
        Form.query.filter_by(id=f.id).update({Form.starts: Form.starts + 1})
        db.session.commit()
    return ('', 204)


def _dataurl_png(value):
    m = re.match(r'^data:image/png;base64,([A-Za-z0-9+/=]+)$', value or '')
    if not m:
        return None
    raw = base64.b64decode(m.group(1))
    return raw if len(raw) <= 600 * 1024 else None


@public_bp.route('/f/<slug>/submit', methods=['POST'])
def submit(slug):
    f = _form_or_404(slug)
    lang = _flang(f)
    L = T(lang)
    preview = _preview(f)
    if f.is_template:
        return jsonify({'ok': False, 'error': L('هذا قالب للمعاينة فقط؛ أنشئ منه نموذجاً لاستقبال الإجابات.', 'This is a template for preview only; create a form from it to collect responses.')}), 409
    ok, why_ar, why_en = f.is_accepting()
    if not ok and not preview:
        return jsonify({'ok': False, 'error': f.s('closed_message') or L(why_ar, why_en)}), 409
    inv = _invitation(f)
    if (not (inv and f.s('audience_only')) or f.s('require_email')) and _gates(f):
        return jsonify({'ok': False, 'error': L('أكمل خطوة الدخول أولاً.', 'Complete the sign-in step first.'), 'redirect': _gates(f)}), 403
    if not preview:
        block = _audience_block(f, inv, lang)
        if block:
            return jsonify({'ok': False, 'error': block}), 403
    if _limited('sub:' + _ip(), 30, 60):
        return jsonify({'ok': False, 'error': L('إرسال متكرر كثير. انتظر دقيقة.', 'Too many submissions. Wait a minute.')}), 429
    try:
        payload = json.loads(request.form.get('payload') or (request.get_data(as_text=True) if request.is_json else '{}'))
    except ValueError:
        payload = {}
    if payload.get('hp'):                 # حقل مصيدة البرامج الآلية
        return jsonify({'ok': True, 'redirect': url_for('public.fill', slug=f.slug)})
    raw = payload.get('answers') if isinstance(payload.get('answers'), dict) else {}
    raw = {str(k)[:60]: v for k, v in list(raw.items())[:600]}
    qmap = {q['id']: q for q in f.questions}
    files_by_q, errors = {}, {}
    # الملفات: تُفحص قبل التحقق حتى يعرف التحقق أن السؤال المطلوب أُجيب
    for qid, q in qmap.items():
        if q['type'] == 'file':
            ups = [u for u in request.files.getlist(f'file__{qid}') if u and u.filename]
            if not ups:
                raw.pop(qid, None)
                continue
            if len(ups) > q.get('max_files', 1):
                errors[qid] = L(f'الحد الأعلى {q.get("max_files", 1)} ملفات.', f'At most {q.get("max_files", 1)} files.')
                continue
            items = []
            for u in ups:
                data = u.read()
                mime = u.mimetype or 'application/octet-stream'
                if len(data) > q.get('max_mb', 10) * 1024 * 1024:
                    errors[qid] = L(f'الملف «{u.filename}» أكبر من {q.get("max_mb", 10)} ميغابايت.', f'"{u.filename}" is larger than {q.get("max_mb", 10)} MB.')
                    break
                acc = q.get('accept', 'any')
                if acc != 'any' and not mime.startswith(ACCEPT.get(acc, ('',))):
                    errors[qid] = L(f'نوع الملف «{u.filename}» غير مقبول هنا.', f'The file type of "{u.filename}" is not accepted here.')
                    break
                items.append({'name': u.filename[:200], 'mime': mime, 'size': len(data), '_data': data})
            files_by_q[qid] = items
            raw[qid] = [{'name': i['name']} for i in items]
        elif q['type'] == 'signature':
            v = raw.get(qid)
            png = _dataurl_png(v) if isinstance(v, str) else None
            if png:
                files_by_q[qid] = [{'name': 'signature.png', 'mime': 'image/png', 'size': len(png), '_data': png}]
                raw[qid] = [{'name': 'signature.png'}]
            else:
                raw.pop(qid, None)
    clean, errs, shown = validate(f.questions, raw)
    if payload.get('timeout') and f.s('time_limit'):     # انتهت المهلة: تُقبل الإجابة ناقصة
        errs = {k: v for k, v in errs.items() if v[0] != 'هذا السؤال مطلوب.'}
    for qid, (ar, en) in errs.items():
        errors.setdefault(qid, L(ar, en))
    shown_ids = {q['id'] for q in shown}
    errors = {k: v for k, v in errors.items() if k in shown_ids}
    if errors:
        return jsonify({'ok': False, 'errors': errors, 'error': L('راجع الأسئلة المظللة.', 'Please check the highlighted questions.')}), 400
    ua = (request.headers.get('User-Agent') or '')[:500]
    info = uaparse.parse(ua)
    meta_in = payload.get('meta') if isinstance(payload.get('meta'), dict) else {}
    meta = {k: str(meta_in.get(k))[:200] for k in ('screen', 'viewport', 'tz', 'lang', 'platform', 'referrer', 'touch', 'source')
            if meta_in.get(k) not in (None, '')}
    meta['browser_version'] = info['version']
    dev_model = uaparse.model(ua, str(meta_in.get('model') or '')[:100])
    os_ver = uaparse.os_version(ua, info['os'], str(meta_in.get('os_version') or '')[:20])
    if dev_model:
        meta['model'] = dev_model
    if os_ver:
        meta['os_version'] = os_ver
    st = session.pop(f'st_{f.slug}', None)
    now = datetime.utcnow()
    dur = int(time.time() - st) if st else None
    if dur is None and str(meta_in.get('elapsed') or '').isdigit():
        dur = int(meta_in['elapsed'])
    dur = max(0, min(dur, 7 * 86400)) if dur is not None else None
    email = (session.get('fv') or {}).get(f.slug)
    filler = (session.get('ff') or {}).get(f.slug)
    if not filler and (session.get('fvn') or {}).get(f.slug):
        filler = {'name': session['fvn'][f.slug]}        # الاسم من حساب Microsoft
    parent = None
    if payload.get('parent') and f.parent_id:
        parent = Response.query.filter_by(token=str(payload['parent'])[:40], form_id=f.parent_id).first()
    ip = _ip()
    dup = (not preview and not email and Response.query.filter(
        Response.form_id == f.id, Response.ip == ip, Response.user_agent == ua,
        Response.submitted_at >= now - timedelta(hours=24)).first() is not None)
    r = Response(form_id=f.id, answers={k: v for k, v in clean.items() if k not in files_by_q}, filler=filler,
                 email=email, submitted_at=now, started_at=now - timedelta(seconds=dur) if dur else None, duration_sec=dur,
                 ip=ip, user_agent=ua, browser=info['browser'], os=info['os'], device=info['device'], lang=lang,
                 meta=meta, is_test=preview, flagged=dup, parent_response_id=parent.id if parent else None)
    db.session.add(r)
    db.session.flush()
    answers = dict(r.answers)
    for qid, items in files_by_q.items():
        if qid not in clean:
            continue
        stored = []
        for it in items:
            m = MediaFile(kind='signature' if qmap[qid]['type'] == 'signature' else 'answer', filename=it['name'],
                          mime=it['mime'], size=it['size'], data=it['_data'], form_id=f.id, response_id=r.id)
            db.session.add(m)
            db.session.flush()
            stored.append({'id': m.id, 'key': m.key, 'name': it['name'], 'size': it['size'], 'mime': it['mime'], 'url': m.url})
        answers[qid] = stored
    r.answers = answers
    if f.s('quiz'):
        r.score, r.max_score, _ = grade(f.questions, answers)
    if not preview:
        import people
        people.mark_response(f, r, inv.token if inv else None, email)
    db.session.commit()
    _after_submit_mail(f, r, lang)
    resp = jsonify({'ok': True, 'redirect': url_for('public.done', slug=f.slug, t=r.token, **({'preview': '1'} if preview else {}))})
    if f.s('one_per_device') and not preview:
        resp.set_cookie(f'fd_{f.slug}', '1', max_age=365 * 86400, samesite='Lax', secure=request.is_secure)
    return resp


def _after_submit_mail(f, r, lang):
    """إشعار أصحاب النموذج ونسخة للمستجيب (إن طُلب وكان البريد مُعدّاً). أي خطأ يُسجَّل ولا يوقف الإرسال."""
    from mail import graph_status, send_email, split_emails
    try:
        if r.is_test or not graph_status()['ready'] and current_app.config.get('MAIL_BACKEND', 'graph') != 'memory':
            return
        rows = ''.join(f'<tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">{_esc(qtitle(q, lang))}</td>'
                       f'<td style="padding:6px;border:1px solid #ddd">{_esc(answer_text(q, r.answers or {}, lang))}</td></tr>'
                       for q in f.questions if q['type'] not in NO_ANSWER and (r.answers or {}).get(q['id']) not in (None, ''))
        table = f'<table style="border-collapse:collapse;font-family:Tahoma,Arial">{rows}</table>'
        d = 'ltr' if lang == 'en' else 'rtl'
        to = split_emails(f.s('notify_emails') or '')
        if to:
            link = (current_app.config.get('BASE_URL') or request.host_url.rstrip('/')) + url_for('admin.response_view', rid=r.id)
            send_email(to, f'إجابة جديدة: {f.title}',
                       f'<div dir="rtl"><p>وصلت إجابة جديدة على النموذج «{_esc(f.title)}».</p>{table}'
                       f'<p><a href="{link}">فتح الإجابة في لوحة الإدارة</a></p></div>', kind='notify')
        if f.s('send_copy') and r.email:
            score = f'<p>{"Your score" if lang == "en" else "درجتك"}: {r.score:g} / {r.max_score:g}</p>' \
                if f.s('quiz') and f.s('show_score') == 'immediate' and r.max_score else ''
            send_email([r.email], ('A copy of your answers: ' if lang == 'en' else 'نسخة من إجاباتك: ') + f.title_for(lang),
                       f'<div dir="{d}"><p>{"Thank you. These are your answers." if lang == "en" else "شكراً لك. هذه إجاباتك."}</p>{score}{table}</div>',
                       kind='copy')
    except Exception as e:   # noqa: BLE001 — البريد لا يُفشل الإرسال
        current_app.logger.error('[forms] after-submit mail failed: %s', e)


def _esc(s):
    from markupsafe import escape
    return str(escape(s or ''))


@public_bp.route('/f/<slug>/done')
def done(slug):
    f = _form_or_404(slug)
    lang = _flang(f)
    r = Response.query.filter_by(token=request.args.get('t') or '', form_id=f.id).first()
    if not r:
        return redirect(url_for('public.fill', slug=slug))
    detail, manual_pending = {}, False
    show_score = f.s('quiz') and f.s('show_score', 'immediate') == 'immediate'
    if show_score:
        _, _, full = grade(f.questions, r.answers or {}, r.manual_points)
        manual_pending = any(ok is None for _, _, ok in full.values())
        if f.s('show_answers'):
            detail = full
    subs = [c for c in f.children.filter(Form.archived.is_(False)).all() if c.status == 'open']
    return render_template('public/done.html', f=f, r=r, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                           show_score=show_score, detail=detail, manual_pending=manual_pending, subs=subs, answer_text=answer_text, qtitle=qtitle,
                           preview=request.args.get('preview') == '1')


@public_bp.route('/f/<slug>/share.jpg')
def share_jpg(slug):
    """صورة معاينة الرابط (og:image) بمقاس 1200×630."""
    import share
    f = _form_or_404(slug)
    data = share.image(f)
    if data is None:                        # مكتبة الصور غير مثبّتة: أيقونة النظام
        return redirect(url_for('static', filename='icons/icon-512.png'))
    resp = FlaskResponse(data, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'public, max-age=600'
    return resp


@public_bp.route('/f/<slug>/qr.svg')
def qr_svg(slug):
    import qr
    f = _form_or_404(slug)
    lang = _flang(f)
    base = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    body = qr.svg(f'{base}/f/{f.slug}', f.title_for(lang), qr.org_name(lang), qr.logo_data_uri(), caption=request.args.get('plain') != '1')
    resp = FlaskResponse(body, mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ── التحقق من البريد وبيانات المستجيب ────────────────────────────────────────

def _domain_ok(f, email):
    doms = [d.strip().lstrip('@').lower() for d in re.split(r'[\s,;]+', f.s('email_domains') or '') if d.strip()]
    return not doms or email.split('@')[-1].lower() in doms


@public_bp.route('/f/<slug>/login', methods=['GET', 'POST'])
def login(slug):
    from mail import graph_status, send_email
    f = _form_or_404(slug)
    lang = _flang(f)
    L = T(lang)
    step, email, dev_code = 'email', '', None
    if request.method == 'POST' and (f.s('login_method') == 'microsoft'):
        abort(403)
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()[:255]
        if request.form.get('action') == 'verify':
            step = 'code'
            code = re.sub(r'\D', '', request.form.get('code') or '')
            row = EmailCode.query.filter_by(form_id=f.id, email=email, used=False).order_by(EmailCode.id.desc()).first()
            if not row or row.expires_at < datetime.utcnow():
                flash(L('انتهت صلاحية الرمز. اطلب رمزاً جديداً.', 'The code has expired. Request a new one.'), 'error')
                step = 'email'
            elif row.attempts >= 5:
                flash(L('محاولات كثيرة. اطلب رمزاً جديداً.', 'Too many attempts. Request a new code.'), 'error')
                step = 'email'
            elif not check_password_hash(row.code_hash, code):
                row.attempts += 1
                db.session.commit()
                flash(L('الرمز غير صحيح.', 'The code is not correct.'), 'error')
            else:
                row.used = True
                db.session.commit()
                fv = dict(session.get('fv') or {})
                fv[f.slug] = email
                session['fv'] = fv
                session.permanent = True
                return redirect(url_for('public.fill', slug=slug, **_keep_args()))
        else:
            if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
                flash(L('اكتب بريداً إلكترونياً صحيحاً.', 'Enter a valid email address.'), 'error')
            elif not _domain_ok(f, email):
                flash(L('هذا النموذج لبريد الجهة فقط: ', 'This form accepts only these domains: ') + (f.s('email_domains') or ''), 'error')
            elif _limited(f'code:{email}', 3, 600) or _limited('codeip:' + _ip(), 10, 600):
                flash(L('طُلبت رموز كثيرة. انتظر عشر دقائق.', 'Too many codes were requested. Wait ten minutes.'), 'error')
            else:
                code = f'{secrets.randbelow(1000000):06d}'
                db.session.add(EmailCode(form_id=f.id, email=email, code_hash=generate_password_hash(code),
                                         expires_at=datetime.utcnow() + timedelta(minutes=15)))
                db.session.commit()
                ready = graph_status()['ready'] or current_app.config.get('MAIL_BACKEND') == 'memory'
                if ready:
                    res = send_email([email], L('رمز الدخول إلى النموذج: ', 'Your sign-in code: ') + code,
                                     f'<div dir="{"ltr" if lang == "en" else "rtl"}" style="font-family:Tahoma,Arial">'
                                     f'<p>{L("رمز الدخول إلى النموذج", "Your code for the form")} «{_esc(f.title_for(lang))}»:</p>'
                                     f'<p style="font-size:28px;letter-spacing:6px;font-weight:bold">{code}</p>'
                                     f'<p>{L("صالح خمس عشرة دقيقة.", "Valid for fifteen minutes.")}</p></div>', kind='code')
                    if res.ok:
                        flash(L('أرسلنا رمزاً من ستة أرقام إلى بريدك.', 'We sent a six-digit code to your email.'), 'ok')
                        step = 'code'
                    else:
                        flash(L('تعذّر إرسال الرمز. أبلغ الجهة صاحبة النموذج.', 'The code could not be sent. Tell the form owner.'), 'error')
                elif current_app.config.get('MAIL_DEV_SHOW'):
                    dev_code, step = code, 'code'
                else:
                    flash(L('البريد غير مُعدّ في النظام، فلا يمكن إرسال رمز الدخول. أبلغ الجهة صاحبة النموذج.',
                            'Mail is not set up on this system, so no sign-in code can be sent. Tell the form owner.'), 'error')
    import msauth
    method = f.s('login_method') or 'any'
    return render_template('public/login.html', f=f, lang=lang, L=L, dir='ltr' if lang == 'en' else 'rtl', step=step,
                           email=email, dev_code=dev_code, args=_keep_args(), ms_ok=msauth.ready() and method != 'code',
                           code_ok=method != 'microsoft')


@public_bp.route('/f/<slug>/details', methods=['GET', 'POST'])
def details(slug):
    f = _form_or_404(slug)
    lang = _flang(f)
    L = T(lang)
    inv = _invitation(f)
    if f.s('require_email') and not (session.get('fv') or {}).get(f.slug):
        return redirect(url_for('public.login', slug=slug, **_keep_args()))
    fields = f.s('filler_fields') or []
    values, errors = dict((session.get('ff') or {}).get(f.slug) or {}), {}
    ms_name = (session.get('fvn') or {}).get(f.slug)
    if ms_name and 'name' in [fd['key'] for fd in fields] and not values.get('name'):
        values['name'] = ms_name
    if inv and 'name' in [fd['key'] for fd in fields] and not values.get('name'):
        values['name'] = inv.person.name
    if request.method == 'POST':
        for fd in fields:
            v = (request.form.get('f_' + fd['key']) or '').strip()[:300]
            values[fd['key']] = v
            if fd.get('required') and not v:
                errors[fd['key']] = L('هذا الحقل مطلوب.', 'This field is required.')
            elif v and fd.get('type') == 'email' and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v):
                errors[fd['key']] = L('اكتب بريداً صحيحاً.', 'Enter a valid email.')
            elif v and fd.get('type') == 'phone' and not re.fullmatch(r'\+?[0-9\s\-()]{6,20}', v):
                errors[fd['key']] = L('اكتب رقم هاتف صحيحاً.', 'Enter a valid phone number.')
        if not errors:
            ff = dict(session.get('ff') or {})
            ff[f.slug] = values
            session['ff'] = ff
            session.permanent = True
            return redirect(url_for('public.fill', slug=slug, **_keep_args()))
    return render_template('public/details.html', f=f, lang=lang, L=L, dir='ltr' if lang == 'en' else 'rtl',
                           fields=fields, values=values, errors=errors, email=(session.get('fv') or {}).get(f.slug),
                           args=_keep_args())


@public_bp.route('/f/<slug>/details/reset', methods=['POST'])
def details_reset(slug):
    ff = dict(session.get('ff') or {})
    ff.pop(slug, None)
    session['ff'] = ff
    fv = dict(session.get('fv') or {})
    if request.form.get('email'):
        fv.pop(slug, None)
        session['fv'] = fv
    return redirect(url_for('public.fill', slug=slug))


@public_bp.app_errorhandler(404)
def not_found(e):
    lang = session.get('lang', 'ar')
    return render_template('public/error.html', code=404, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                           msg=T(lang)('الصفحة أو النموذج غير موجود.', 'The page or form was not found.')), 404


@public_bp.app_errorhandler(403)
def forbidden(e):
    lang = session.get('lang', 'ar')
    return render_template('public/error.html', code=403, lang=lang, L=T(lang), dir='ltr' if lang == 'en' else 'rtl',
                           msg=T(lang)('لا تملك صلاحية فتح هذه الصفحة.', 'You do not have access to this page.')), 403


@public_bp.app_errorhandler(413)
def too_big(e):
    if request.path.endswith('/submit') or request.path.startswith('/admin/api/'):
        return jsonify({'ok': False, 'error': 'الملفات المرفقة أكبر من الحد المسموح. / The attached files are too large.'}), 413
    return 'Too large', 413


# ── الدخول بحساب Microsoft ───────────────────────────────────────────────────

def _set_verified(f, email, name=''):
    fv = dict(session.get('fv') or {})
    fv[f.slug] = email
    session['fv'] = fv
    if name:
        mn = dict(session.get('fvn') or {})
        mn[f.slug] = name
        session['fvn'] = mn
    session.permanent = True


@public_bp.route('/f/<slug>/login/microsoft')
def login_microsoft(slug):
    import msauth
    f = _form_or_404(slug)
    L = T(_flang(f))
    if not msauth.ready() or f.s('login_method') == 'code':
        flash(L('الدخول بحساب Microsoft غير متاح لهذا النموذج.', 'Microsoft sign-in is not available for this form.'), 'error')
        return redirect(url_for('public.login', slug=slug))
    doms = [d.strip().lstrip('@') for d in re.split(r'[\s,;]+', f.s('email_domains') or '') if d.strip()]
    url, st = msauth.start(doms[0] if len(doms) == 1 else '')
    st.update(slug=slug, args=_keep_args())
    session['ms_oauth'] = st
    return redirect(url)


@public_bp.route('/auth/ms/callback')
def ms_callback():
    import msauth
    st = session.pop('ms_oauth', None) or {}
    f = Form.query.filter_by(slug=st.get('slug') or '').first()
    if not f:
        abort(404)
    L = T(_flang(f))
    back = url_for('public.login', slug=f.slug, **(st.get('args') or {}))
    if request.args.get('error'):
        flash(L('أُلغي الدخول بحساب Microsoft أو رُفض.', 'Microsoft sign-in was cancelled or refused.'), 'error')
        return redirect(back)
    if not request.args.get('code') or not secrets.compare_digest(request.args.get('state', ''), st.get('state', '')):
        flash(L('انتهت صلاحية طلب الدخول. أعد المحاولة.', 'The sign-in request expired. Try again.'), 'error')
        return redirect(back)
    try:
        who = msauth.finish(request.args['code'], st['verifier'])
    except Exception as e:  # noqa: BLE001 — يُسجَّل ويُعرض للمستخدم بلا تفاصيل سرية
        current_app.logger.error('[forms] Microsoft sign-in failed: %s', e)
        flash(L('تعذّر الدخول بحساب Microsoft. أبلغ الجهة صاحبة النموذج.', 'Microsoft sign-in failed. Tell the form owner.'), 'error')
        return redirect(back)
    if not _domain_ok(f, who['email']):
        flash(L('هذا النموذج لحسابات الجهة فقط: ', 'This form accepts only these domains: ') + (f.s('email_domains') or ''), 'error')
        return redirect(back)
    _set_verified(f, who['email'], who['name'])
    return redirect(url_for('public.fill', slug=f.slug, **(st.get('args') or {})))
