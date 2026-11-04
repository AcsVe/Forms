"""رمز QR لرابط النموذج: يُبنى على الخادم (مكتبة segno، بلا أي خدمة خارجية)، بشعار الجهة في وسطه واسمها وعنوان النموذج تحته.

تصحيح الأخطاء بالمستوى H (يتحمّل تغطية نحو 30% من الرمز)، والشعار لا يغطي أكثر من 5% تقريباً، فيبقى الرمز مقروءاً.
"""
import base64
import os

import segno
from markupsafe import escape

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


def logo_data_uri():
    """شعار الجهة من الإعدادات، وإلا أيقونة النظام."""
    from models import AppSetting, MediaFile, db
    try:
        lid = AppSetting.get('org_logo_id') or ''
        m = db.session.get(MediaFile, int(lid)) if lid else None
    except Exception:  # noqa: BLE001
        m = None
    if m:
        return f'data:{m.mime};base64,' + base64.b64encode(m.data).decode()
    with open(os.path.join(STATIC, 'brand', 'system.svg'), 'rb') as fh:
        return 'data:image/svg+xml;base64,' + base64.b64encode(fh.read()).decode()


def svg(url, title='', org='', logo=None, scale=10, caption=True):
    q = segno.make(url, error='h', micro=False)
    rows = [list(r) for r in q.matrix]
    n = len(rows)
    border = 4
    size = (n + 2 * border) * scale
    path = []
    for y, row in enumerate(rows):
        x = 0
        while x < n:
            if row[x]:
                start = x
                while x < n and row[x]:
                    x += 1
                path.append(f'M{(start + border) * scale},{(y + border) * scale}h{(x - start) * scale}v{scale}h-{(x - start) * scale}z')
            else:
                x += 1
    lw = int(size * 0.22)                       # مربع الشعار
    lx = (size - lw) // 2
    pad = int(lw * 0.08)
    cap_h = 0
    texts = []
    if caption and (org or title):
        lines = [(org, 30, 800, '#0f2a52'), (title, 26, 600, '#334155')]
        y = size + 8
        for text, fs, fw, color in lines:
            if not text:
                continue
            text = text if len(text) <= 48 else text[:47] + '…'
            y += fs + 10
            texts.append(f'<text x="{size // 2}" y="{y}" text-anchor="middle" direction="rtl" font-family="Tajawal, Tahoma, Arial, sans-serif" '
                         f'font-size="{fs}" font-weight="{fw}" fill="{color}">{escape(text)}</text>')
        y += 30
        texts.append(f'<text x="{size // 2}" y="{y}" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" fill="#64748b" direction="ltr">{escape(url)}</text>')
        cap_h = y - size + 18
    total_h = size + cap_h
    logo_el = ''
    if logo:
        logo_el = (f'<rect x="{lx}" y="{lx}" width="{lw}" height="{lw}" rx="{lw // 6}" fill="#fff"/>'
                   f'<image x="{lx + pad}" y="{lx + pad}" width="{lw - 2 * pad}" height="{lw - 2 * pad}" href="{logo}" preserveAspectRatio="xMidYMid meet"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {total_h}" width="{size}" height="{total_h}" role="img" aria-label="QR">'
            f'<rect width="{size}" height="{total_h}" fill="#fff"/>'
            f'<path d="{"".join(path)}" fill="#0f2a52"/>{logo_el}{"".join(texts)}</svg>')


def org_name(lang='ar'):
    from models import AppSetting
    ar, en = AppSetting.get('org_name_ar') or '', AppSetting.get('org_name_en') or ''
    return (en or ar) if lang == 'en' else (ar or en)
