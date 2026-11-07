"""المنطقة التقريبية للمستجيب من عنوان الشبكة، دون أي خدمة خارجية وقت الإجابة.

القاعدة: «IP to City Lite» من DB-IP (رخصة CC BY 4.0، ويلزم ذكر المصدر)، تُحمَّل مرة في الشهر إلى
data/geo/ في الخلفية عند تشغيل الخادم، ويُبحث فيها محلياً. الدقة على مستوى المدينة، وقد تخطئ مع
شبكات الهاتف والشبكات الافتراضية الخاصة. إذا لم تتوفر القاعدة بعدُ تُترك المنطقة فارغة ولا يتعطل شيء.
"""
import gzip
import ipaddress
import logging
import os
import shutil
import threading
import time
from datetime import date

log = logging.getLogger('forms.geo')

URL = 'https://download.db-ip.com/free/dbip-city-lite-{}.mmdb.gz'
MAX_AGE = 35 * 86400          # تُجدَّد القاعدة إذا مضى عليها أكثر من 35 يوماً
CHECK_EVERY = 24 * 3600

_lock = threading.Lock()
_reader = None
_reader_mtime = None
_started = False


def db_path():
    base = os.environ.get('DATA_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    return os.path.join(base, 'geo', 'dbip-city-lite.mmdb')


def _open():
    """يفتح القاعدة، ويعيد فتحها إذا استُبدلت بنسخة أحدث."""
    global _reader, _reader_mtime
    path = db_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _reader is not None and _reader_mtime == mtime:
        return _reader
    with _lock:
        if _reader is not None and _reader_mtime == mtime:
            return _reader
        try:
            import maxminddb
            new = maxminddb.open_database(path, maxminddb.MODE_MMAP)
        except Exception:
            log.exception('Could not open the region database')
            return None
        old, _reader, _reader_mtime = _reader, new, mtime
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        return _reader


def _name(rec, lang):
    names = (rec or {}).get('names') or {}
    return names.get(lang) or names.get('en') or ''


def lookup(ip):
    """{'en': 'Amman, Jordan', 'ar': 'عمّان، الأردن', 'cc': 'JO'} أو {} إذا تعذّر."""
    try:
        addr = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return {}
    if not addr.is_global:
        return {}
    reader = _open()
    if reader is None:
        return {}
    try:
        rec = reader.get(str(addr)) or {}
    except Exception:
        log.exception('Region lookup failed')
        return {}
    country, city = rec.get('country') or {}, rec.get('city') or {}
    subs = rec.get('subdivisions') or [{}]
    out = {'cc': country.get('iso_code', '')}
    for lang, sep in (('en', ', '), ('ar', '، ')):
        place = _name(city, lang) or _name(subs[0], lang)
        out[lang] = sep.join(x for x in (place, _name(country, lang)) if x)
    return out if out['en'] else {}


def text(meta, lang='ar'):
    """نص المنطقة المحفوظ مع الإجابة بلغة العرض."""
    meta = meta or {}
    return (meta.get('region_ar') if lang == 'ar' else '') or meta.get('region') or ''


def _months():
    t = date.today()
    prev = date(t.year - 1, 12, 1) if t.month == 1 else date(t.year, t.month - 1, 1)
    return [t.strftime('%Y-%m'), prev.strftime('%Y-%m')]


def refresh(force=False):
    """يحمّل أحدث قاعدة إذا كانت مفقودة أو قديمة. يعيد True إذا صارت القاعدة جاهزة."""
    path = db_path()
    try:
        fresh = time.time() - os.path.getmtime(path) < MAX_AGE
    except OSError:
        fresh = False
    if fresh and not force:
        return True
    import requests
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gz, tmp = path + '.gz.part', path + '.part'
    for month in _months():
        try:
            with requests.get(URL.format(month), stream=True, timeout=60) as r:
                if r.status_code != 200:
                    continue
                with open(gz, 'wb') as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            with gzip.open(gz, 'rb') as src, open(tmp, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            import maxminddb
            maxminddb.open_database(tmp).close()          # تحقّق أن الملف سليم قبل استبداله
            os.replace(tmp, path)
            log.info('Region database updated (%s)', month)
            return True
        except Exception:
            log.exception('Region database download failed (%s)', month)
        finally:
            for p in (gz, tmp):
                try:
                    os.remove(p)
                except OSError:
                    pass
    return os.path.exists(path)


def start_updater():
    """خيط في الخلفية يحمّل القاعدة عند الحاجة ثم يتحقق يومياً. لا يؤخر تشغيل الخادم."""
    global _started
    if _started or os.environ.get('FORMS_NO_GEO_DOWNLOAD') == '1':
        return
    _started = True

    def loop():
        while True:
            try:
                refresh()
            except Exception:
                log.exception('Region database check failed')
            time.sleep(CHECK_EVERY)

    threading.Thread(target=loop, name='geo-updater', daemon=True).start()
