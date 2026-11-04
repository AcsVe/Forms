"""مرشّحات القوالب: الوقت بتوقيت عمّان بالصيغة 2026-12-31 14:30، والمدة، وأسماء الأجهزة."""
from zoneinfo import ZoneInfo

from flask import session

from uaparse import DEVICE_LABELS

AMMAN = ZoneInfo('Asia/Amman')
UTC = ZoneInfo('UTC')


def to_local(dt):
    return dt.replace(tzinfo=UTC).astimezone(AMMAN) if dt else None


def local(dt, fmt='%Y-%m-%d %H:%M'):
    d = to_local(dt)
    return d.strftime(fmt) if d else ''


def duration(sec):
    if not sec:
        return '—'
    sec = int(sec)
    if sec < 60:
        return f'{sec} ' + ('ث' if session.get('lang', 'ar') != 'en' else 's')
    m, s = divmod(sec, 60)
    if m < 60:
        return f'{m}:{s:02d}'
    h, m = divmod(m, 60)
    return f'{h}:{m:02d}:{s:02d}'


def device_label(key):
    a, e = DEVICE_LABELS.get(key or 'desktop', (key or '—', key or '—'))
    return e if session.get('lang', 'ar') == 'en' else a


def install(app):
    app.jinja_env.filters['local'] = local
    app.jinja_env.filters['localdate'] = lambda dt: local(dt, '%Y-%m-%d')
    app.jinja_env.filters['dur'] = duration
    app.jinja_env.filters['device'] = device_label
