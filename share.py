"""صورة معاينة رابط النموذج (واتساب وتيمز وتويتر وغيرها): ملف JPEG بمقاس 1200×630.

- المصدر بالترتيب: «صورة معاينة الرابط» ← صورة الترويسة ← صورة الخلفية؛ تُقصّ لتملأ المقاس.
- إن لم توجد صورة: بطاقة بلون النموذج الرئيسي وفي وسطها شعار النموذج أو شعار الجهة.
- الصورة تُضغط (أقل من 300 كيلوبايت تقريباً) لأن واتساب يتجاهل الصور الكبيرة.
- النتيجة تُحفظ في الذاكرة حسب آخر تعديل للنموذج والشعار، فلا تُرسم في كل طلب.
"""
import io
import re

from models import AppSetting, MediaFile, db

W, H = 1200, 630
_cache = {}
_MEDIA = re.compile(r'^/media/(\d+)/([\w-]+)$')


def _media_bytes(url):
    """بيانات صورة محفوظة في النظام فقط (لا جلب لروابط خارجية)."""
    m = _MEDIA.match(url or '')
    if not m:
        return None
    f = db.session.get(MediaFile, int(m.group(1)))
    if not f or f.key != m.group(2) or not (f.mime or '').startswith('image/') or 'svg' in f.mime:
        return None
    return f.data


def _org_logo_url():
    lid = AppSetting.get('org_logo_id') or ''
    f = db.session.get(MediaFile, int(lid)) if str(lid).isdigit() else None
    return f.url if f else ''


def source_urls(f):
    return [f.s('share_image'), f.s('header_image'), f.s('bg_image')]


def logo_url(f):
    """شعار النموذج إن وُجد، وإلا شعار الجهة."""
    return f.s('logo') or _org_logo_url()


def _hex(c, default=(12, 103, 236)):
    if isinstance(c, str) and re.fullmatch(r'#[0-9A-Fa-f]{6}', c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    return default


def _cover(img):
    from PIL import Image
    img = img.convert('RGB')
    r = max(W / img.width, H / img.height)
    img = img.resize((max(W, round(img.width * r)), max(H, round(img.height * r))), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))


def _branded(f, logo_data):
    """بطاقة بلون النموذج وشعار في الوسط داخل لوحة بيضاء مستديرة."""
    from PIL import Image, ImageDraw
    c1 = _hex(f.s('accent'))
    c2 = tuple(max(0, int(v * .55)) for v in c1)
    img = Image.new('RGB', (W, H), c1)
    d = ImageDraw.Draw(img)
    for y in range(H):                      # تدرّج عمودي من اللون إلى نسخته الداكنة
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(c1, c2)))
    # دوائر شفافة للزينة
    deco = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    dd.ellipse((-160, -200, 380, 340), fill=(255, 255, 255, 26))
    dd.ellipse((880, 330, 1360, 810), fill=(255, 255, 255, 20))
    img = Image.alpha_composite(img.convert('RGBA'), deco)
    d = ImageDraw.Draw(img)
    box = 360
    x0, y0 = (W - box) // 2, (H - box) // 2
    d.rounded_rectangle((x0, y0, x0 + box, y0 + box), radius=56, fill=(255, 255, 255, 255))
    logo = None
    if logo_data:
        try:
            logo = Image.open(io.BytesIO(logo_data))
            logo.load()
        except Exception:
            logo = None
    if logo is not None:
        logo = logo.convert('RGBA')
        logo.thumbnail((box - 70, box - 70), Image.LANCZOS)
        img.alpha_composite(logo, (x0 + (box - logo.width) // 2, y0 + (box - logo.height) // 2))
    else:                                   # رمز نموذج بسيط عند غياب الشعار
        cx = x0 + 95
        d.rounded_rectangle((cx, y0 + 70, cx + 170, y0 + 290), radius=18, outline=c1, width=10)
        for i, wd in enumerate((110, 90, 110, 70)):
            d.rounded_rectangle((cx + 30, y0 + 112 + i * 42, cx + 30 + wd, y0 + 126 + i * 42), radius=7, fill=c1)
    return img.convert('RGB')


def image(f):
    """بيانات JPEG لصورة المعاينة، أو None إن لم تتوفر مكتبة الصور."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return None
    src = next((u for u in source_urls(f) if _media_bytes(u)), '')
    logo = '' if src else logo_url(f)
    key = (f.id, f.updated_at.isoformat() if f.updated_at else '', src, logo, f.s('accent'))
    if _cache.get(f.id, (None,))[0] == key:
        return _cache[f.id][1]
    img = None
    if src:
        try:
            from PIL import Image
            img = _cover(Image.open(io.BytesIO(_media_bytes(src))))
        except Exception:
            img = None
    if img is None:
        img = _branded(f, _media_bytes(logo))
    out = io.BytesIO()
    img.save(out, 'JPEG', quality=84, optimize=True, progressive=True)
    data = out.getvalue()
    if len(data) > 290_000:                 # صورة كثيرة التفاصيل: ضغط أعلى
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=68, optimize=True, progressive=True)
        data = out.getvalue()
    _cache[f.id] = (key, data)
    return data
