"""نظام النماذج والاستبيانات — 9.iajaward.org (المنفذ 8009). التشغيل: python serve.py"""
import os
import re as _re
from datetime import timedelta

from flask import Flask, Response as FlaskResponse, abort, redirect, request, send_file, session, url_for

from models import AppSetting, MediaFile, db, ensure_schema

# في النص العربي يظهر «1-3» معكوساً؛ نعزل أرقام النطاقات باتجاه من اليسار إلى اليمين.
_NUM_RANGE = _re.compile(r'(?<![⁦\d:./\-])(\d+\s*[-+–]\s*\d+)(?![\d⁩:./\-])')
_ARABIC = _re.compile('[؀-ۿ]')
_TOKEN = _re.compile(r'[A-Za-z0-9_\-]{12,}')
_DATEISH = _re.compile(r'^\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2})?)?$')


def bidi_fix(value):
    if not isinstance(value, str) or _TOKEN.fullmatch(value) or _DATEISH.match(value):
        return value
    if _NUM_RANGE.search(value) and '⁦' not in value and _ARABIC.search(value):
        from markupsafe import Markup
        fixed = _NUM_RANGE.sub('⁦\\1⁩', str(value))
        return Markup(fixed) if isinstance(value, Markup) else fixed
    return value


def _secret_key():
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    folder = os.environ.get('DATA_DIR') or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(folder, '.secret_key')
    try:
        with open(path, encoding='utf-8') as f:
            key = f.read().strip()
    except OSError:
        key = ''
    if len(key) < 32:
        import secrets
        key = secrets.token_hex(32)
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(key)
        except OSError:
            pass
    return key


def create_app(test_config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = _secret_key()
    app.config['ADMIN_USER'] = os.environ.get('ADMIN_USER', 'admin')
    app.config['ADMIN_PASS'] = os.environ.get('ADMIN_PASS', 'admin')
    for key in ('MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'MS_SENDER_EMAIL'):
        app.config[key] = os.environ.get(key, '')
    app.config['BASE_URL'] = (os.environ.get('BASE_URL') or '').rstrip('/')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 7
    # FORMS_MAIL_DEV=1 (للتجربة المحلية فقط): يظهر رمز التحقق على الشاشة إن لم يكن البريد مُعدّاً.
    app.config['MAIL_DEV_SHOW'] = os.environ.get('FORMS_MAIL_DEV') == '1'
    db_path = os.environ.get('FORMS_DB_PATH') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'forms.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    database_url = os.environ.get('DATABASE_URL') or 'sqlite:///' + db_path.replace('\\', '/')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
    if os.environ.get('SECURE_COOKIES') == '1':
        app.config['SESSION_COOKIE_SECURE'] = True
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.jinja_env.finalize = bidi_fix

    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        from sqlalchemy import event
        with app.app_context():
            @event.listens_for(db.engine, 'connect')
            def _sqlite_pragmas(conn, _):
                cur = conn.cursor()
                cur.execute('PRAGMA journal_mode=WAL')
                cur.execute('PRAGMA busy_timeout=15000')
                cur.close()

    from blueprints.admin import admin_bp
    from blueprints.public import public_bp
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)

    with app.app_context():
        db.create_all()
        ensure_schema(app.config['ADMIN_USER'], app.config['ADMIN_PASS'])

    from filters import install as install_filters
    install_filters(app)

    @app.context_processor
    def inject_asset():
        def asset(filename):
            try:
                v = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
            except OSError:
                v = 0
            return url_for('static', filename=filename, v=v)
        return {'asset': asset}

    @app.context_processor
    def inject_lang():
        lang = session.get('lang', 'ar')

        def L(ar, en):
            return en if lang == 'en' else ar
        return {'lang': lang, 'L': L, 'dir': 'ltr' if lang == 'en' else 'rtl'}

    @app.context_processor
    def inject_brand():
        from datetime import datetime
        try:
            org_ar = AppSetting.get('org_name_ar') or ''
            org_en = AppSetting.get('org_name_en') or ''
            accent = AppSetting.get('accent') or ''
            logo_id = AppSetting.get('org_logo_id') or ''
            logo = db.session.get(MediaFile, int(logo_id)) if logo_id else None
        except Exception:
            db.session.rollback()
            org_ar = org_en = accent = ''
            logo = None
        lang = session.get('lang', 'ar')
        org = (org_en or org_ar) if lang == 'en' else (org_ar or org_en)
        return {'org_name': org,
                'accent': accent if _re.fullmatch(r'#[0-9A-Fa-f]{6}', accent or '') else '#0C67EC',
                'brand_logo_url': logo.url if logo else url_for('static', filename='brand/system.svg'),
                'brand_is_icon': not logo, 'now_year': datetime.now().year}

    @app.route('/')
    def index():
        return redirect(url_for('admin.dashboard'))

    @app.route('/lang/<code>')
    def set_lang(code):
        session['lang'] = 'en' if code == 'en' else 'ar'
        session.permanent = True
        nxt = request.args.get('next') or ''
        if not nxt.startswith('/') or nxt.startswith('//'):
            nxt = url_for('admin.dashboard')
        return redirect(nxt)

    @app.route('/media/<int:media_id>/<key>')
    def media(media_id, key):
        import io
        m = db.session.get(MediaFile, media_id)
        if not m or m.key != key:
            abort(404)
        # المرفقات من المستجيبين لا تُعرض إلا للمسؤولين
        if m.kind in ('answer', 'signature') and not session.get('uid'):
            abort(403)
        resp = send_file(io.BytesIO(m.data), mimetype=m.mime, conditional=True, download_name=m.filename or f'file-{m.id}',
                         as_attachment=request.args.get('download') == '1', max_age=31536000)
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        if m.kind in ('answer', 'signature'):
            resp.headers['Cache-Control'] = 'private, no-store'
            resp.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'"
        return resp

    @app.route('/healthz')
    def healthz():
        return FlaskResponse('ok', mimetype='text/plain')

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        # صفحات الإدارة لا تُعرض داخل إطار؛ صفحة التضمين /f/<slug>/embed مسموحة في أي موقع
        if request.path.startswith('/admin'):
            resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        return resp

    return app


if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ops'))
    from common import load_env
    load_env()
    create_app().run(host='127.0.0.1', port=int(os.environ.get('PORT', 8009)), debug=True)
