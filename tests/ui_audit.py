"""مراجعة المظهر في متصفح حقيقي: كل صفحة بالعربية والإنجليزية على الحاسوب والهاتف.

يقيس: تباين النص مع خلفيته (4.5 على الأقل، و3 للنص الكبير)، والخط الأصغر من 13 بكسل، والتمرير الأفقي، والعناصر
الخارجة عن حدود بطاقتها، وأخطاء JavaScript. ويحفظ صوراً مصغّرة في E2E_OUT.

    venv\\Scripts\\python tests\\ui_audit.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get('E2E_OUT') or tempfile.mkdtemp(prefix='forms-ui-')
os.makedirs(OUT, exist_ok=True)
DB = os.path.join(OUT, 'ui.db')
for ext in ('', '-wal', '-shm'):
    if os.path.exists(DB + ext):
        os.remove(DB + ext)
PORT = 5097
BASE = f'http://127.0.0.1:{PORT}'
os.environ.update(FORMS_DB_PATH=DB, DATA_DIR=OUT, PYTHONUTF8='1', FORMS_NO_DOTENV='1', FORMS_NO_GEO_DOWNLOAD='1')
for _k in ('MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'MS_SENDER_EMAIL'):
    os.environ.pop(_k, None)
os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from models import Form, Group, Response, db  # noqa: E402

app = create_app({'MAIL_BACKEND': 'memory', 'MAIL_OUTBOX': []})
c = app.test_client()
c.post('/admin/login', data={'username': 'admin', 'password': 'admin'})
c.post('/admin/settings', data={'org_name_ar': 'مدرسة الأمل النموذجية', 'org_name_en': 'Al Amal Model School', 'accent': '#0C67EC'})
with app.app_context():
    tpl = Form.query.filter_by(is_template=True).order_by(Form.id).first().id
r = c.post('/admin/forms/new', data={'template_id': tpl})
FID = int(r.headers['Location'].split('/')[-2])
c.post(f'/admin/api/forms/{FID}', json={'status': 'open', 'category': 'استبيانات'})
with app.app_context():
    f = db.session.get(Form, FID)
    SLUG = f.slug
    qs = f.questions
c.post('/admin/people/import', data={'file': (io.BytesIO(('﻿الاسم,البريد,المجموعات,ملاحظة\n' + '\n'.join(
    f'ولي أمر {i},parent{i}@school.jo,{"الصف السابع" if i % 2 else "الصف الثامن"},ولي أمر' for i in range(1, 9))).encode('utf-8')), 'p.csv')},
    content_type='multipart/form-data')
c.post(f'/admin/forms/{FID}/audience', data={'mode': 'all', 'send': '1'})
for i in range(6):
    tc = app.test_client()
    tc.get(f'/f/{SLUG}')
    lik = {r['id']: qs[1]['cols'][(i + j) % 5]['id'] for j, r in enumerate(qs[1]['rows'])}
    tc.post(f'/f/{SLUG}/submit', data={'payload': json.dumps({'answers': {qs[0]['id']: qs[0]['choices'][i % 4]['id'], qs[1]['id']: lik,
                                                                         qs[2]['id']: 3 + i % 3, qs[3]['id']: 5 + i, qs[4]['id']: 'تحسين المواصلات والمكتبة'}})})
with app.app_context():
    RID = Response.query.first().id
    GID = Group.query.first().id
    TIDS = [x.id for x in Form.query.filter_by(is_template=True)]

srv = subprocess.Popen([sys.executable, os.path.join(ROOT, 'serve.py')], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=dict(os.environ, PORT=str(PORT), HOST='127.0.0.1', FORMS_MAIL_DEV='1'))
for _ in range(60):
    try:
        if urllib.request.urlopen(BASE + '/healthz', timeout=1).read() == b'ok':
            break
    except Exception:
        time.sleep(0.5)

PAGES = ['/admin/', '/admin/forms', '/admin/templates', '/admin/forms/new', '/admin/forms/import', '/admin/responses',
         f'/admin/compare?ids={FID}&ids={TIDS[1]}', '/admin/people', '/admin/people#groups', '/admin/people/import',
         '/admin/settings', '/admin/settings/microsoft', '/admin/users', '/admin/account', '/admin/help',
         f'/admin/forms/{FID}/edit', f'/admin/forms/{FID}/edit#settings', f'/admin/forms/{FID}/edit#design', f'/admin/forms/{FID}/edit#access',
         f'/admin/forms/{FID}/edit#share', f'/admin/forms/{FID}/responses', f'/admin/forms/{FID}/analysis',
         f'/admin/forms/{FID}/audience', f'/admin/responses/{RID}', f'/admin/forms/{FID}/qr/print']
PUBLIC = [f'/f/{SLUG}', '/admin/login', '/admin/forgot']

AUDIT_JS = r"""() => {
  const lum = (c) => { const m = c.match(/[\d.]+/g); if (!m) return null; const [r, g, b] = m.slice(0, 3).map((v) => { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return { l: 0.2126 * r + 0.7152 * g + 0.0722 * b, a: m.length > 3 ? Number(m[3]) : 1 }; };
  const bgOf = (el) => { while (el) { const s = getComputedStyle(el); const b = s.backgroundColor; const L = lum(b);
      if (s.backgroundImage !== 'none') return null; if (L && L.a > 0.9) return L.l; el = el.parentElement; } return 1; };
  const out = { contrast: [], small: [], spill: [], bidi: [] };
  // اتجاه النص: نص عربي البداية في عنصر من اليسار لليمين (أو إنجليزي البداية في عنصر من اليمين) ومعه أرقام أو علامات
  // يظهر مقلوباً («صف ابنكم .1»). يحدث حين يُعرض محتوى بلغة داخل واجهة باللغة الأخرى دون dir مناسب.
  const AR = /[\u0600-\u06FF]/, LA = /[A-Za-z]/, NEUTRAL = /[0-9٠-٩.:*?؟()\-–—%/]/;
  const firstStrong = (t) => { for (const ch of t) { if (AR.test(ch)) return 'rtl'; if (LA.test(ch)) return 'ltr'; } return null; };
  const seen = new Set();
  document.querySelectorAll('body *').forEach((el) => {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!own) return;
    const s = getComputedStyle(el); if (s.visibility === 'hidden') return;
    // الشفافية الفعلية = حاصل ضرب شفافية العنصر وكل آبائه (المكتبات تُبهت الأب لا النص نفسه)
    let op = 1; for (let n = el; n; n = n.parentElement) op *= Number(getComputedStyle(n).opacity);
    if (op < 0.15) return;
    if (el.closest('canvas,svg,.chart-box,option,select')) return;
    const fs = parseFloat(s.fontSize), fw = Number(s.fontWeight) || 400;
    const txt = el.textContent.trim().slice(0, 40);
    let fg = lum(s.color); const bg = bgOf(el);
    if (fg && bg !== null && op < 1) fg = { l: fg.l * op + bg * (1 - op), a: fg.a };   // تقريب: مزج الإضاءة مع الخلفية
    if (fg && bg !== null && !el.matches(':disabled') && !el.closest(':disabled,[disabled]')) {
      const ratio = (Math.max(fg.l, bg) + 0.05) / (Math.min(fg.l, bg) + 0.05);
      const large = fs >= 24 || (fs >= 18.6 && fw >= 700);
      if (ratio < (large ? 3 : 4.5)) { const k = 'c' + txt; if (!seen.has(k)) { seen.add(k); out.contrast.push(`${ratio.toFixed(2)} «${txt}» ${el.tagName}.${el.className}`.slice(0, 140)); } }
    }
    // النص المعزول بـ bdi أو dir أو unicode-bidi: plaintext يأخذ اتجاهه بنفسه فلا يُحسب على العنصر الأب
    const isolated = (n) => n.nodeType === 1 && (n.tagName === 'BDI' || n.hasAttribute('dir') || getComputedStyle(n).unicodeBidi === 'plaintext');
    const textOf = (n) => n.nodeType === 3 ? n.textContent : (isolated(n) ? ' ' : [...n.childNodes].map(textOf).join(''));
    const full = s.unicodeBidi === 'plaintext' ? '' : [...el.childNodes].map(textOf).join('').replace(/\s+/g, ' ').trim();
    const want = firstStrong(full);
    if (want && want !== s.direction && NEUTRAL.test(full) && (AR.test(full) && LA.test(full) || want === 'rtl' ? true : /^[^A-Za-z]|[^A-Za-z0-9]$/.test(full))
        && !el.closest('code,pre,kbd,[dir=ltr] [dir=ltr],input,textarea')) {
      const k = 'd' + full.slice(0, 40); if (!seen.has(k)) { seen.add(k); out.bidi.push(`${s.direction} «${full.slice(0, 50)}» ${el.tagName}.${el.className}`.slice(0, 140)); }
    }
    // تاريخ ووقت بلا حروف (2026-11-06 18:05) داخل عنصر من اليمين لليسار: يظهر الوقت قبل التاريخ
    const own2 = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' ').trim();
    if (s.direction === 'rtl' && /^\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}/.test(own2) && s.unicodeBidi !== 'plaintext')
      { const k = 't' + own2; if (!seen.has(k)) { seen.add(k); out.bidi.push(`rtl «${own2.slice(0, 40)}» ${el.tagName}.${el.className}`); } }
    if (fs < 13 && !el.closest('.dt-sort,.chip small,.words small,sup')) { const k = 's' + txt; if (!seen.has(k)) { seen.add(k); out.small.push(`${fs}px «${txt}» ${el.tagName}.${el.className}`.slice(0, 120)); } }
  });
  document.querySelectorAll('.card, .f-card, .kpi').forEach((card) => {
    const cr = card.getBoundingClientRect(); if (!cr.width) return;
    card.querySelectorAll('*').forEach((el) => {
      if (el.closest('.dt-wrap,.matrix-wrap,.chart-box,.tabbar,.pick-list,.check-list,.txt-list,.imp-preview,.palette,details:not([open]),[hidden],.menu,dialog')) return;
      const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
      if (r.left < cr.left - 2 || r.right > cr.right + 2) { const k = 'p' + el.tagName + el.className; if (!seen.has(k)) { seen.add(k); out.spill.push(`${el.tagName}.${el.className} «${(el.textContent || '').trim().slice(0, 30)}» in ${card.className}`.slice(0, 140)); } }
    });
  });
  out.overflow = document.documentElement.scrollWidth - innerWidth;
  return out;
}"""

# فحص لغة الواجهة: النصوص الظاهرة ونصوص الإرشاد (placeholder وtitle وalt وaria-label) — يُنسخ إلى tests/ui_audit.py في كل نظام.
# يرصد: نصاً يشبه الكود (أسماء متغيرات وملفات وقيم برمجية)، وكلمات عامية أو دخيلة في الواجهة العربية، ونص إرشاد بالإنجليزية
# في الواجهة العربية أو بالعربية في الإنجليزية، وصورة بلا نص بديل.
LANG_JS = r"""(args) => {
  const [ui, okWords, checkArabic, scopeSel] = args;   // checkArabic: الواجهة الإنجليزية ببيانات إنجليزية
  const out = []; const seen = new Set();
  const add = (k, m) => { if (!seen.has(k)) { seen.add(k); out.push(m.slice(0, 150)); } };
  const AR = /[؀-ۿ]/;
  const ok = new Set(['iOS', 'iPhone', 'iPad', 'macOS', 'iCloud', 'eSchool', 'YouTube', 'WhatsApp', 'PayPal', 'OneDrive',
                      'SharePoint', 'PowerPoint', 'GitHub', 'MenaPAY', 'MenaITech', 'ZKTeco', 'BellPlayer', 'JavaScript'].concat(okWords || []));
  // يُحذف البريد والروابط والنطاقات قبل الفحص: ليست كوداً
  const clean = (t) => t.replace(/\S+@\S+|https?:\/\/\S*|\b[\w.-]+\.(org|com|net|edu|jo|test|gov)\b\S*/gi, ' ');
  const CODE = [
    [/\b[a-z][a-z0-9]*_[a-z0-9_]+\b/, 'snake_case'],
    [/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/, 'variable name'],
    [/\b[a-z]+[A-Z][A-Za-z]+\b/, 'camelCase'],
    [/\{\{|\}\}|\{%|%\}|\$\{|<\/?[a-z]+>/, 'template code'],
    [/^(undefined|null|NaN)$|\b(undefined|NaN|Traceback|TypeError|KeyError|ValueError)\b|\[object /, 'program value'],
    [/\b[\w-]+\.(py|bat|env|db|sqlite|json|js|css|html|ps1|sql|log|ini|cfg)\b/i, 'file name'],
    [/\b(HTTP|Error|errno|status)\s*\d{3}\b|\bSQLITE_|\bOperationalError\b/i, 'error code'],
  ];
  // None/True/False كلمات إنجليزية سليمة في الواجهة الإنجليزية؛ وفي العربية تعني قيمة برمجية تسرّبت
  if (ui === 'ar') CODE.push([/^(None|True|False)$/, 'program value']);
  const codeLike = (t) => { t = clean(t); for (const [re, name] of CODE) { const m = t.match(re); if (m && !ok.has(m[0])) return `${name} «${m[0]}»`; } return null; };
  // عامي أو دخيل (القاعدة: «إذا/إن» لا «لو»، «فقط» لا «بس»، «الخادم» لا «السيرفر»، «الهاتف» لا «الموبايل»...)
  const COLLOQ = /(?:^|[\s،؛.؟!«(\/])(لو|بس|اللي|إللي|فاضي|فاضية|هيك|شو|مش|كمان|هلق|هلأ|منيح|ليش|وين|هاي|هاد|هادا|السيرفر|سيرفر|الموبايل|موبايل|تيمز|الباسورد|باسورد|يوزر|اليوزر|اللوجو|لوجو|الداتا|داتا|لينك|اللينك|فايل|الفايل|ايميل|إيميل|الإيميل|الايميل|اوكي|أوكي|نزّل|نزّلها|حمّلها|سيستم|السيستم|أبديت|ابديت)(?=$|[\s،؛.؟!»):\/])/;
  const LATIN_WORD = /\b[A-Za-z]{3,}\b/g;
  const check = (el, where, t) => {
    if (!t || !t.trim()) return;
    t = t.replace(/\s+/g, ' ').trim();
    const tag = `${el.tagName}.${(el.className && el.className.baseVal === undefined ? el.className : '')}`.slice(0, 40);
    const c = codeLike(t); if (c) add('c' + where + t, `code-like ${c} in ${where} «${t.slice(0, 60)}» ${tag}`);
    if (ui === 'ar') {
      const m = t.match(COLLOQ); if (m) add('q' + t, `colloquial «${m[1]}» in ${where} «${t.slice(0, 60)}» ${tag}`);
      if (where !== 'text' && !AR.test(t)) {   // نص إرشاد كله بالإنجليزية (الرموز والأسماء بجانب العربية مقبولة)
        const latin = (clean(t).match(LATIN_WORD) || []).filter((w) => !ok.has(w) && !/^x+$/i.test(w) && !/^(PDF|Excel|Word|CSV|QR|Microsoft|Google|Outlook|Teams|Android|Windows|Chrome|Edge|Wi|Fi|USB|SMS|API|URL|IP|PIN|OTP|ID|Cloudflare|Dahua|Render|Drive|Gmail|Zoom|Forms|Office|Apple|Huawei|Samsung)$/i.test(w));
        if (latin.length) add('l' + where + t, `English «${latin.slice(0, 3).join(' ')}» in ${where} of the Arabic interface «${t.slice(0, 60)}» ${tag}`);
      }
    } else if (checkArabic && where !== 'text' && AR.test(t) && !el.closest('[data-content]') && !(okWords || []).includes(t)) {
      add('a' + where + t, `Arabic in ${where} of the English interface «${t.slice(0, 60)}» ${tag}`);
    }
  };
  const scope = (scopeSel && document.querySelector(scopeSel)) || document.body;
  scope.querySelectorAll('*').forEach((el) => {
    if (el.closest('script,style,code,pre,kbd,noscript,template,textarea,[data-content],[data-raw]')) return;   // textarea: نص يكتبه المستخدم أو رمز تضمين للنسخ
    const s = getComputedStyle(el); if (s.display === 'none' && !el.closest('select')) return;
    [...el.childNodes].forEach((n) => { if (n.nodeType === 3) check(el, 'text', n.textContent); });
    for (const a of ['placeholder', 'title', 'alt', 'aria-label']) if (el.hasAttribute(a)) check(el, a, el.getAttribute(a));
    if (el.matches('input[type=submit],input[type=button]')) check(el, 'button', el.value);
    if (el.tagName === 'IMG' && !el.hasAttribute('alt')) add('i' + el.src, `image without alt text ${el.src.split('/').pop().slice(0, 50)}`);
  });
  check(document.documentElement, 'title', document.title);
  return out;
}"""


report = []
try:
    with sync_playwright() as p:
        kw = {'executable_path': os.environ['PW_EXE']} if os.environ.get('PW_EXE') else {'channel': os.environ.get('E2E_CHANNEL', 'chrome')}
        browser = p.chromium.launch(**kw)
        for vp_name, vp in (('desktop', {'viewport': {'width': 1366, 'height': 900}}), ('phone', dict(p.devices['iPhone 13']))):
            for lang in ('ar', 'en'):
                ctx = browser.new_context(**vp)
                page = ctx.new_page()
                errs = []
                page.on('pageerror', lambda e: errs.append(str(e)))
                page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
                page.goto(BASE + f'/lang/{lang}?next=/admin/login')
                for u in PUBLIC[1:]:
                    page.goto(BASE + u, wait_until='networkidle')
                    res = page.evaluate(AUDIT_JS)
                    res['lang'] = page.evaluate(LANG_JS, [lang, [], False, 'body'])
                    report.append((vp_name, lang, u, res, list(errs)))
                    errs.clear()
                page.goto(BASE + '/admin/login')
                page.fill('#username', 'admin')
                page.fill('#password', 'admin')
                page.click('button[type=submit]')
                page.wait_for_url('**/admin/')
                for u in PAGES + PUBLIC[:1]:
                    page.goto(BASE + u, wait_until='networkidle')
                    page.wait_for_timeout(300)
                    res = page.evaluate(AUDIT_JS)
                    res['lang'] = page.evaluate(LANG_JS, [lang, [], False, 'body'])
                    report.append((vp_name, lang, u, res, list(errs)))
                    errs.clear()
                    if os.environ.get('SHOTS') and lang == 'ar':
                        name = f"{vp_name}-{u.strip('/').replace('/', '_').replace('?', '_').replace('#', '_')[:50] or 'root'}.jpg"
                        try:
                            page.screenshot(path=os.path.join(OUT, name), type='jpeg', quality=45, full_page=True)
                        except Exception:  # صفحة أطول من حد لقطة المتصفح: لقطة الجزء الظاهر فقط
                            page.screenshot(path=os.path.join(OUT, name), type='jpeg', quality=45)
                ctx.close()
        browser.close()
finally:
    srv.terminate()

bad = 0
for vp_name, lang, u, res, errs in report:
    issues = []
    if res['overflow'] > 2:
        issues.append(f"horizontal overflow {res['overflow']}px")
    issues += ['contrast ' + x for x in res['contrast']] + ['small ' + x for x in res['small']] + ['spill ' + x for x in res['spill']] + ['direction ' + x for x in res['bidi']]
    issues += ['language ' + x for x in res.get('lang', [])] + ['JS ' + e for e in errs]
    if issues:
        bad += len(issues)
        print(f'[{vp_name} {lang}] {u}')
        for i in issues[:12]:
            print('   ', i)
print(f'\n{len(report)} page views, {bad} issue(s). Output: {OUT}')
sys.exit(1 if bad else 0)
