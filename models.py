"""جداول نظام النماذج والاستبيانات.

• بنية النموذج كاملة (الأسئلة والأقسام والمنطق والاختبار) محفوظة في عمود JSON واحد ``forms.schema``؛
  لكل سؤال معرّف نصي ثابت (مثل q_ab12cd) تُربط به الإجابات، فيبقى عند النسخ ويسهّل المقارنة بين النماذج.
• الإجابات في ``responses.answers`` (JSON: معرّف السؤال ← القيمة).
• الملفات (الخلفيات والموسيقى والفيديو والمرفقات والتواقيع) داخل القاعدة نفسها في ``media_files``،
  فتشملها النسخة الاحتياطية دون مجلد آخر.
• الترحيل آلي عند الإقلاع: ``ensure_schema()`` يضيف الأعمدة الجديدة دون مسح أي بيانات.
"""
import json
import secrets
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def new_slug():
    return secrets.token_urlsafe(6).replace('-', 'x').replace('_', 'y')


class JSONText(db.TypeDecorator):
    """JSON محفوظ نصاً (يعمل في SQLite وPostgreSQL بلا فرق)."""
    impl = db.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if not value:
            return None
        try:
            return json.loads(value)
        except ValueError:
            return None


class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    name          = db.Column(db.String(200))
    email         = db.Column(db.String(255))
    role          = db.Column(db.String(20), nullable=False, default='editor')   # admin | editor
    active        = db.Column(db.Boolean, nullable=False, default=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)
    session_ver   = db.Column(db.Integer, nullable=False, default=0)   # يزيد مع تغيير كلمة المرور فتخرج الجلسات القديمة

    forms = db.relationship('Form', backref='owner', lazy='dynamic', foreign_keys='Form.owner_id')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
        self.session_ver = (self.session_ver or 0) + 1

    def check_password(self, pw):
        return bool(pw) and check_password_hash(self.password_hash, pw)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def display(self):
        return self.name or self.username


class Form(db.Model):
    __tablename__ = 'forms'
    id          = db.Column(db.Integer, primary_key=True)
    slug        = db.Column(db.String(40), unique=True, nullable=False, default=new_slug)
    title       = db.Column(db.String(300), nullable=False)
    title_en    = db.Column(db.String(300))
    description = db.Column(db.Text)
    category    = db.Column(db.String(120))
    status      = db.Column(db.String(20), nullable=False, default='draft')   # draft | open | closed
    is_template = db.Column(db.Boolean, nullable=False, default=False)
    archived    = db.Column(db.Boolean, nullable=False, default=False)
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    parent_id   = db.Column(db.Integer, db.ForeignKey('forms.id'))
    source_id   = db.Column(db.Integer)                 # النموذج الذي نُسخ منه (للمقارنة)
    schema      = db.Column(JSONText, nullable=False, default=lambda: {'questions': []})
    settings    = db.Column(JSONText, nullable=False, default=dict)
    views       = db.Column(db.Integer, nullable=False, default=0)
    starts      = db.Column(db.Integer, nullable=False, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = db.relationship('Form', remote_side=[id], backref=db.backref('children', lazy='dynamic'))
    responses = db.relationship('Response', backref='form', lazy='dynamic')

    @property
    def questions(self):
        return (self.schema or {}).get('questions') or []

    def s(self, key, default=None):
        return (self.settings or {}).get(key, default)

    @property
    def response_count(self):
        return self.responses.filter_by(is_test=False).count()

    def title_for(self, lang):
        return (self.title_en or self.title) if lang == 'en' else (self.title or self.title_en)

    def is_accepting(self, now=None):
        """(مفتوح؟, سبب الإغلاق ar, en)"""
        now = now or datetime.utcnow()
        if self.status != 'open' or self.archived:
            return False, 'هذا النموذج لا يستقبل إجابات حالياً.', 'This form is not accepting responses.'
        opens, closes = self.s('open_at'), self.s('close_at')
        if opens and now < _parse_dt(opens):
            return False, 'لم يبدأ استقبال الإجابات بعد.', 'This form has not opened yet.'
        if closes and now > _parse_dt(closes):
            return False, 'انتهى موعد استقبال الإجابات.', 'The deadline for this form has passed.'
        limit = self.s('max_responses')
        if limit and int(limit) > 0 and self.response_count >= int(limit):
            return False, 'اكتمل العدد المطلوب من الإجابات.', 'This form has reached its response limit.'
        return True, '', ''


def _parse_dt(value):
    """تاريخ ووقت عمّان المكتوب في الإعدادات (2026-12-31T14:00) ← UTC بلا منطقة."""
    from zoneinfo import ZoneInfo
    try:
        local = datetime.fromisoformat(str(value)[:16])
    except ValueError:
        return datetime.max
    return local.replace(tzinfo=ZoneInfo('Asia/Amman')).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)


class Response(db.Model):
    __tablename__ = 'responses'
    id           = db.Column(db.Integer, primary_key=True)
    form_id      = db.Column(db.Integer, db.ForeignKey('forms.id'), nullable=False, index=True)
    token        = db.Column(db.String(40), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(16))
    parent_response_id = db.Column(db.Integer, db.ForeignKey('responses.id'))
    answers      = db.Column(JSONText, nullable=False, default=dict)
    filler       = db.Column(JSONText)                    # بيانات المستجيب (الاسم، الهاتف…)
    email        = db.Column(db.String(255), index=True)  # البريد الموثّق (إن طُلب الدخول)
    score        = db.Column(db.Float)
    max_score    = db.Column(db.Float)
    manual_points = db.Column(JSONText)                   # تصحيح يدوي: معرّف السؤال ← الدرجة
    started_at   = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    duration_sec = db.Column(db.Integer)
    ip           = db.Column(db.String(64))
    user_agent   = db.Column(db.String(500))
    browser      = db.Column(db.String(60))
    os           = db.Column(db.String(60))
    device       = db.Column(db.String(20))              # mobile | tablet | desktop
    lang         = db.Column(db.String(5))
    meta         = db.Column(JSONText)                    # الشاشة، المنطقة الزمنية، لغة المتصفح، المصدر…
    is_test      = db.Column(db.Boolean, nullable=False, default=False)
    flagged      = db.Column(db.Boolean, nullable=False, default=False)   # تكرار محتمل من الجهاز نفسه
    starred      = db.Column(db.Boolean, nullable=False, default=False)

    parent_response = db.relationship('Response', remote_side=[id], backref='child_responses')

    @property
    def percent(self):
        if self.max_score:
            return round(100.0 * (self.score or 0) / self.max_score, 1)
        return None

    @property
    def who(self):
        f = self.filler or {}
        return f.get('name') or self.email or ''


class MediaFile(db.Model):
    __tablename__ = 'media_files'
    id          = db.Column(db.Integer, primary_key=True)
    kind        = db.Column(db.String(20), nullable=False)    # logo | image | video | audio | answer | signature
    filename    = db.Column(db.String(255))
    mime        = db.Column(db.String(100), nullable=False)
    size        = db.Column(db.Integer, default=0)
    data        = db.Column(db.LargeBinary, nullable=False)
    form_id     = db.Column(db.Integer, index=True)
    response_id = db.Column(db.Integer, index=True)
    key         = db.Column(db.String(40), nullable=False, default=lambda: secrets.token_urlsafe(12))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def url(self):
        return f'/media/{self.id}/{self.key}'


class EmailCode(db.Model):
    """رمز التحقق من البريد قبل فتح نموذج يتطلب الدخول."""
    __tablename__ = 'email_codes'
    id         = db.Column(db.Integer, primary_key=True)
    form_id    = db.Column(db.Integer, nullable=False, index=True)
    email      = db.Column(db.String(255), nullable=False)
    code_hash  = db.Column(db.String(255), nullable=False)
    attempts   = db.Column(db.Integer, nullable=False, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PasswordReset(db.Model):
    """رابط «نسيت كلمة المرور»: صالح ساعة ولمرة واحدة؛ يُحفظ ملخّص الرمز لا الرمز نفسه."""
    __tablename__ = 'password_resets'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppSetting(db.Model):
    __tablename__ = 'app_settings'
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

    @staticmethod
    def get(key, default=None):
        row = db.session.get(AppSetting, key)
        return row.value if row else default

    @staticmethod
    def set(key, value):
        row = db.session.get(AppSetting, key)
        if row:
            row.value = str(value)
        else:
            db.session.add(AppSetting(key=key, value=str(value)))


class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id         = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    recipients = db.Column(db.String(1000), nullable=False)
    subject    = db.Column(db.String(500))
    kind       = db.Column(db.String(40))
    status     = db.Column(db.String(20), nullable=False)
    error      = db.Column(db.Text)


# الأعمدة المضافة بعد أول إصدار تُكتب هنا: (الجدول، العمود، تعريف SQL). تُضاف عند الإقلاع إن لم تكن موجودة.
MIGRATIONS = [
    ('forms', 'source_id', 'INTEGER'),
    ('forms', 'starts', 'INTEGER NOT NULL DEFAULT 0'),
    ('responses', 'manual_points', 'TEXT'),
    ('responses', 'starred', 'BOOLEAN NOT NULL DEFAULT 0'),
    ('users', 'session_ver', 'INTEGER NOT NULL DEFAULT 0'),
]


def ensure_schema(admin_user='admin', admin_pass='admin'):
    """create_all() يضيف الجداول الجديدة فقط؛ هذه الدالة تضيف الأعمدة الجديدة وتنشئ أول مدير (مرة واحدة)."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    for table, col, ddl in MIGRATIONS:
        if table in tables and col not in {c['name'] for c in insp.get_columns(table)}:
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}'))
    if not User.query.first():
        u = User(username=admin_user or 'admin', name='مسؤول النظام', role='admin')
        u.set_password(admin_pass or 'admin')
        db.session.add(u)
        db.session.commit()
    if not AppSetting.get('templates_seeded'):
        from seed_templates import seed
        seed()
        AppSetting.set('templates_seeded', '1')
        db.session.commit()
