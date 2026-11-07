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


_ANDROID_MODEL = re.compile(r'android [\d.]+;(?: [a-z]{2}[-_][a-z]{2};)? ([^;)]+?)(?: build/|\))', re.I)


def model(ua, hint=''):
    """طراز الجهاز: من تلميح المتصفح (Chrome وEdge على أندرويد) وإلا من User-Agent.
    المتصفحات لا تكشف اسم الجهاز ولا عنوان MAC، وآيفون وآيباد لا يذكران الطراز الدقيق."""
    hint = (hint or '').strip()
    if hint:
        return hint[:100]
    ua = ua or ''
    u = ua.lower()
    for k, name in (('iphone', 'iPhone'), ('ipad', 'iPad'), ('ipod', 'iPod')):
        if k in u:
            return name
    m = _ANDROID_MODEL.search(ua)
    if m and m.group(1).strip().lower() not in ('k', 'mobile', 'linux', 'wv', 'tablet'):
        return m.group(1).strip()[:100]
    if 'macintosh' in u:
        return 'Mac'
    if 'cros' in u:
        return 'Chromebook'
    return ''


def os_version(ua, os_name, hint=''):
    """إصدار النظام: Windows 10 أو 11 يُعرف من تلميح المتصفح فقط (User-Agent يذكر 10 للاثنين)."""
    hint = (hint or '').strip()
    major = hint.split('.')[0] if hint else ''
    if os_name == 'Windows':
        if major.isdigit():
            return '11' if int(major) >= 13 else '10' if int(major) > 0 else ''
        return ''
    if major.isdigit() and int(major) > 0 and os_name in ('Android', 'macOS', 'ChromeOS'):
        return hint[:20] if os_name == 'ChromeOS' else major
    u = (ua or '').lower()
    if os_name == 'Android':
        m = re.search(r'android (\d+(?:\.\d+)?)', u)
        return m.group(1) if m else ''
    if os_name == 'iOS':
        m = re.search(r'os (\d+)[_.](\d+)', u)
        return f'{m.group(1)}.{m.group(2)}' if m else ''
    return ''


DEVICE_LABELS = {'mobile': ('هاتف', 'Phone'), 'tablet': ('جهاز لوحي', 'Tablet'), 'desktop': ('حاسوب', 'Computer'),
                 'bot': ('برنامج آلي', 'Bot')}
