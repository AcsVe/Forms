"""أدوات مشتركة بين صفحات الإدارة: المستخدم الحالي، والصلاحيات، وتصفية الإجابات."""
import functools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import abort, flash, redirect, request, session, url_for

from analytics import keys_of
from i18n import pick
from models import Form, Response, User, db

AMMAN = ZoneInfo('Asia/Amman')
UTC = ZoneInfo('UTC')


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    u = db.session.get(User, uid)
    return u if u and u.active else None


def login_required(view):
    @functools.wraps(view)
    def wrapper(*a, **kw):
        u = current_user()
        if not u:
            session.pop('uid', None)
            if request.path.startswith('/admin/api/'):
                return {'ok': False, 'error': pick('انتهت الجلسة. سجّل الدخول من جديد.', 'Your session ended. Sign in again.')}, 401
            return redirect(url_for('admin.login', next=request.full_path))
        return view(*a, **kw)
    return wrapper


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapper(*a, **kw):
        if not current_user().is_admin:
            flash(pick('هذه الصفحة لمسؤولي النظام فقط.', 'This page is for system administrators only.'), 'error')
            return redirect(url_for('admin.dashboard'))
        return view(*a, **kw)
    return wrapper


def forms_query(include_templates=False):
    """النماذج التي يراها المستخدم: المسؤول يرى الكل، والمحرّر يرى نماذجه."""
    u = current_user()
    q = Form.query
    if not include_templates:
        q = q.filter(Form.is_template.is_(False))
    if not u.is_admin:
        q = q.filter(Form.owner_id == u.id)
    return q


def can_edit(form):
    u = current_user()
    return bool(u and (u.is_admin or form.owner_id == u.id))


def get_form(fid, edit=True):
    f = db.session.get(Form, fid)
    if not f:
        abort(404)
    if edit and not can_edit(f):
        abort(403)
    if not edit and not (can_edit(f) or f.is_template):
        abort(403)
    return f


def local_to_utc(day, end=False):
    try:
        d = datetime.strptime(day, '%Y-%m-%d')
    except (TypeError, ValueError):
        return None
    if end:
        d += timedelta(days=1)
    return d.replace(tzinfo=AMMAN).astimezone(UTC).replace(tzinfo=None)


def today_local():
    return datetime.now(AMMAN).strftime('%Y-%m-%d')


def period_range(period):
    now = datetime.now(AMMAN).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'today':
        start = now
    elif period == 'week':
        start = now - timedelta(days=6)
    elif period == 'month':
        start = now - timedelta(days=29)
    else:
        return None
    return start.astimezone(UTC).replace(tzinfo=None)


def response_filters(query, args):
    if args.get('test') != '1':
        query = query.filter(Response.is_test.is_(False))
    start = local_to_utc(args.get('from'))
    end = local_to_utc(args.get('to'), end=True)
    p = period_range(args.get('period'))
    if p:
        start = max(start, p) if start else p
    if start:
        query = query.filter(Response.submitted_at >= start)
    if end:
        query = query.filter(Response.submitted_at < end)
    for col in ('device', 'browser', 'os'):
        if args.get(col):
            query = query.filter(getattr(Response, col) == args[col])
    if args.get('flagged') == '1':
        query = query.filter(Response.flagged.is_(True))
    if args.get('starred') == '1':
        query = query.filter(Response.starred.is_(True))
    return query


def filtered_responses(form, args):
    rs = response_filters(Response.query.filter_by(form_id=form.id), args).order_by(Response.submitted_at).all()
    seg_q, seg_v = args.get('seg_q'), args.get('seg_v')
    if seg_q and seg_v:
        q = next((x for x in form.questions if x['id'] == seg_q), None)
        if q:
            rs = [r for r in rs if seg_v in keys_of(q, (r.answers or {}).get(seg_q))]
    return rs
