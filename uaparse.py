"""استخراج المتصفح ونظام التشغيل ونوع الجهاز من User-Agent (بلا مكتبات خارجية)."""
import re


def parse(ua):
    ua = ua or ''
    u = ua.lower()
    if 'edg/' in u or 'edga/' in u or 'edgios/' in u:
        browser = 'Edge'
    elif 'opr/' in u or 'opera' in u:
        browser = 'Opera'
    elif 'samsungbrowser' in u:
        browser = 'Samsung Internet'
    elif 'fban' in u or 'fbav' in u:
        browser = 'Facebook'
    elif 'instagram' in u:
        browser = 'Instagram'
    elif 'whatsapp' in u:
        browser = 'WhatsApp'
    elif 'firefox/' in u or 'fxios/' in u:
        browser = 'Firefox'
    elif 'crios/' in u or ('chrome/' in u and 'chromium' not in u):
        browser = 'Chrome'
    elif 'safari/' in u and 'version/' in u:
        browser = 'Safari'
    elif 'msie' in u or 'trident/' in u:
        browser = 'Internet Explorer'
    elif not u:
        browser = 'غير معروف'
    else:
        browser = 'أخرى'
    m = re.search(r'(?:edg|edga|opr|samsungbrowser|firefox|fxios|crios|chrome|version)/(\d+)', u)
    version = m.group(1) if m else ''
    if 'windows' in u:
        os_name = 'Windows'
    elif 'iphone' in u or 'ipad' in u or 'ipod' in u:
        os_name = 'iOS'
    elif 'android' in u:
        os_name = 'Android'
    elif 'mac os x' in u or 'macintosh' in u:
        os_name = 'macOS'
    elif 'cros' in u:
        os_name = 'ChromeOS'
    elif 'linux' in u:
        os_name = 'Linux'
    else:
        os_name = 'غير معروف' if not u else 'أخرى'
    if 'ipad' in u or 'tablet' in u or ('android' in u and 'mobile' not in u):
        device = 'tablet'
    elif 'mobi' in u or 'iphone' in u or 'ipod' in u:
        device = 'mobile'
    else:
        device = 'desktop'
    if re.search(r'bot|crawl|spider|headless', u):
        device = 'bot'
    return {'browser': browser, 'version': version, 'os': os_name, 'device': device}


DEVICE_LABELS = {'mobile': ('هاتف', 'Phone'), 'tablet': ('جهاز لوحي', 'Tablet'), 'desktop': ('حاسوب', 'Computer'),
                 'bot': ('برنامج آلي', 'Bot')}
