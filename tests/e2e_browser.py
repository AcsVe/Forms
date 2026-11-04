"""فحص في متصفح حقيقي (Chrome المثبّت، عبر Playwright): كل الصفحات بلا أخطاء JavaScript، واتجاه RTL، وعرض الهاتف
بلا تمرير أفقي، ثم تجارب فعلية: التصميم والحفظ التلقائي، والتعبئة بكل أنواع الأسئلة، والتفرّع، والدخول بالبريد، واللصق.

    venv\\Scripts\\python tests\\e2e_browser.py          (E2E_OUT=مجلد للصور، E2E_CHANNEL=chrome|msedge)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get('E2E_OUT') or tempfile.mkdtemp(prefix='forms-e2e-')
os.makedirs(OUT, exist_ok=True)
DB = os.path.join(OUT, 'e2e.db')
for ext in ('', '-wal', '-shm'):
    if os.path.exists(DB + ext):
        os.remove(DB + ext)
PORT = 5099
BASE = f'http://127.0.0.1:{PORT}'
os.environ.update(FORMS_DB_PATH=DB, DATA_DIR=OUT, PYTHONUTF8='1', FORMS_NO_DOTENV='1')
for _k in ('MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'MS_SENDER_EMAIL'):
    os.environ.pop(_k, None)
os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, ROOT)

# ── بيانات التجربة عبر مسارات الإدارة الحقيقية ─────────────────────────────
from app import create_app  # noqa: E402
from models import Form, Response, db  # noqa: E402

app = create_app()
c = app.test_client()
c.post('/admin/login', data={'username': 'admin', 'password': 'admin'})
RICH = [
    {'id': 'name', 'type': 'short_text', 'title': 'الاسم الكامل', 'required': True},
    {'id': 'grade', 'type': 'dropdown', 'title': 'الصف', 'required': True, 'choices': [{'id': 'g7', 'label': 'السابع'}, {'id': 'g8', 'label': 'الثامن'}]},
    {'id': 'like', 'type': 'single', 'title': 'هل أعجبتك الفعالية؟', 'required': True, 'other': True,
     'choices': [{'id': 'y', 'label': 'نعم'}, {'id': 'n', 'label': 'لا'}]},
    {'id': 'why', 'type': 'long_text', 'title': 'لماذا لم تعجبك؟', 'required': True,
     'logic': {'show_if': {'mode': 'all', 'rules': [{'q': 'like', 'op': 'eq', 'value': 'n'}]}}},
    {'id': 'days', 'type': 'multi', 'title': 'الأيام المناسبة', 'choices': [{'id': 'd1', 'label': 'الأحد'}, {'id': 'd2', 'label': 'الإثنين'}]},
    {'id': 'p2', 'type': 'section', 'title': 'التقييم'},
    {'id': 'rate', 'type': 'rating', 'title': 'تقييمك العام', 'max': 5, 'required': True},
    {'id': 'nps', 'type': 'nps', 'title': 'هل تنصح بها؟', 'min_label': 'لا', 'max_label': 'بالتأكيد'},
    {'id': 'scale', 'type': 'scale', 'title': 'مدى الفائدة', 'min': 1, 'max': 5},
    {'id': 'lik', 'type': 'likert', 'title': 'العبارات', 'required': True, 'rows': [{'id': 'r1', 'label': 'التنظيم جيد'}, {'id': 'r2', 'label': 'المدة مناسبة'}]},
    {'id': 'slide', 'type': 'slider', 'title': 'كم ساعة؟', 'min': 0, 'max': 10},
    {'id': 'p3', 'type': 'section', 'title': 'تفاصيل أخرى'},
    {'id': 'rank', 'type': 'ranking', 'title': 'رتّب الأنشطة', 'choices': [{'id': 'a', 'label': 'الرياضة'}, {'id': 'b', 'label': 'الفنون'}, {'id': 'c', 'label': 'العلوم'}]},
    {'id': 'sum', 'type': 'constant_sum', 'title': 'وزّع 10 نقاط', 'total': 10, 'choices': [{'id': 'x', 'label': 'المحتوى'}, {'id': 'z', 'label': 'المكان'}]},
    {'id': 'when', 'type': 'date', 'title': 'تاريخ الحضور'},
    {'id': 'doc', 'type': 'file', 'title': 'أرفق صورة', 'accept': 'any'},
    {'id': 'sig', 'type': 'signature', 'title': 'التوقيع'},
    {'id': 'src', 'type': 'hidden', 'title': 'المصدر', 'param': 'src'},
]


def mk(title, questions, settings, status='open'):
    r = c.post('/admin/forms/new', data={'title': title})
    fid = int(r.headers['Location'].split('/')[-2])
    c.post(f'/admin/api/forms/{fid}', json={'schema': {'questions': questions}, 'status': status,
                                             'settings': dict({'lang': 'ar', 'progress': True, 'question_numbers': True}, **settings)})
    with app.app_context():
        return fid, db.session.get(Form, fid).slug


RICH_ID, RICH_SLUG = mk('استبيان الفعالية الشامل', RICH, {'accent': '#7c3aed', 'autosave': True, 'bilingual': True})
GATE_ID, GATE_SLUG = mk('نموذج بالدخول', [{'id': 'a', 'type': 'short_text', 'title': 'ملاحظتك', 'required': True}],
                        {'require_email': True, 'filler_fields': [{'key': 'name', 'label': 'الاسم', 'required': True}, {'key': 'grade', 'label': 'الصف', 'type': 'select', 'options': 'السابع، الثامن', 'required': True}]})
with app.app_context():
    tpl = Form.query.filter(Form.title.like('استطلاع آراء الطلبة%')).one().id
r = c.post('/admin/forms/new', data={'template_id': tpl})
BR_ID = int(r.headers['Location'].split('/')[-2])
c.post(f'/admin/api/forms/{BR_ID}', json={'status': 'open'})
with app.app_context():
    BR_SLUG = db.session.get(Form, BR_ID).slug
    BR_Q = db.session.get(Form, BR_ID).questions
for i, (g, like) in enumerate([('g7', 'y'), ('g8', 'n'), ('g7', 'y')]):
    tc = app.test_client()
    tc.get(f'/f/{RICH_SLUG}')
    ans = {'name': f'طالب {i}', 'grade': g, 'like': like, 'rate': 3 + i % 3, 'nps': 6 + i, 'lik': {}, 'why': 'طويلة'}
    with app.app_context():
        cols = db.session.get(Form, RICH_ID).questions[9]['cols']
    ans['lik'] = {'r1': cols[i]['id'], 'r2': cols[4]['id']}
    rr = tc.post(f'/f/{RICH_SLUG}/submit', data={'payload': json.dumps({'answers': ans})}, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36'})
    assert rr.json['ok'], rr.data
with app.app_context():
    RID = Response.query.first().id
    TIDS = [f.id for f in Form.query.filter_by(is_template=True)]

# ── الخادم الحقيقي (Waitress) ────────────────────────────────────────────────
# قيم Microsoft وهمية: تُظهر زر الدخول بالحساب، وطلب صفحة Microsoft يُعترض في المتصفح ولا يخرج
env = dict(os.environ, PORT=str(PORT), FORMS_MAIL_DEV='1', HOST='127.0.0.1', MS_TENANT_ID='e2e-tenant', MS_CLIENT_ID='e2e-client', MS_CLIENT_SECRET='e2e')
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, 'serve.py')], env=env, cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(60):
    try:
        if urllib.request.urlopen(BASE + '/healthz', timeout=1).read() == b'ok':
            break
    except Exception:
        time.sleep(0.5)

problems = []


def note(msg):
    print('  ✗', msg)
    problems.append(msg)


def saved(page):
    """ينتظر انتهاء الحفظ التلقائي (المؤقت 700 ملّي ثانية ثم الطلب)."""
    page.wait_for_timeout(1000)
    page.wait_for_function("document.getElementById('saveState').classList.contains('ok')", timeout=8000)


def watch(page):
    errs = []
    page.on('pageerror', lambda e: errs.append(f'JS: {e}'))
    page.on('console', lambda m: errs.append(f'console: {m.text}') if m.type == 'error' else None)
    return errs


def check(page, errs, url, lang='ar', shot=None):
    errs.clear()
    page.goto(BASE + url, wait_until='networkidle')
    page.wait_for_timeout(250)
    d = page.evaluate('document.documentElement.dir')
    if d != ('ltr' if lang == 'en' else 'rtl'):
        note(f'{url}: dir={d}')
    over = page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
    if over > 2:
        wide = page.evaluate('''() => [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > innerWidth + 2 || e.getBoundingClientRect().left < -2)
            .slice(0, 4).map(e => e.tagName + '.' + e.className).join(' | ')''')
        note(f'{url} @{page.viewport_size["width"]}px: horizontal overflow {over}px ({wide})')
    for e in errs:
        note(f'{url}: {e}')
    if shot:
        page.screenshot(path=os.path.join(OUT, shot), type='jpeg', quality=55, full_page=False)


ADMIN_URLS = ['/admin/', '/admin/forms', '/admin/templates', '/admin/forms/new', '/admin/forms/import', '/admin/responses',
              f'/admin/compare?ids={RICH_ID}&ids={BR_ID}', '/admin/users', '/admin/settings', '/admin/help', '/admin/account',
              f'/admin/forms/{RICH_ID}/edit', f'/admin/forms/{RICH_ID}/responses', f'/admin/forms/{RICH_ID}/analysis?a=grade&b=like',
              f'/admin/responses/{RID}', f'/admin/forms/{BR_ID}/edit', f'/admin/forms/{TIDS[2]}/analysis']

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get('E2E_CHANNEL', 'chrome'), headless=True)
        # ── سطح المكتب ──
        ctx = browser.new_context(viewport={'width': 1280, 'height': 860}, locale='ar')
        page = ctx.new_page()
        errs = watch(page)
        check(page, errs, '/admin/login', shot='01-login.jpg')
        page.fill('#username', 'admin')
        page.fill('#password', 'admin')
        page.click('button[type=submit]')
        page.wait_for_url('**/admin/')
        print('desktop pages (ar)')
        for i, u in enumerate(ADMIN_URLS):
            check(page, errs, u, shot=f'd{i:02d}.jpg' if u in ('/admin/', f'/admin/forms/{RICH_ID}/edit', f'/admin/forms/{RICH_ID}/analysis?a=grade&b=like') else None)
        page.goto(BASE + '/lang/en?next=/admin/')
        print('desktop pages (en)')
        for u in ADMIN_URLS[:6] + [f'/admin/forms/{RICH_ID}/edit', f'/admin/forms/{RICH_ID}/analysis']:
            check(page, errs, u, lang='en')
        page.goto(BASE + '/lang/ar?next=/admin/')

        print('builder: add, edit, autosave, reload')
        check(page, errs, f'/admin/forms/{RICH_ID}/edit')
        n0 = page.locator('.qcard').count()
        page.click('.palette [data-add="matrix"]')
        page.fill('.qcard.open .q-title-in', 'سؤال من المتصفح')
        saved(page)
        page.click('.qcard.open .opts .row-actions button >> nth=0')         # إضافة صف
        page.click('.tabbar [data-tab="quiz"]')
        page.click('[data-pane="quiz"] .switch')
        saved(page)
        page.reload(wait_until='networkidle')
        if page.locator('.qcard').count() != n0 + 1 or 'سؤال من المتصفح' not in page.inner_text('#qlist'):
            note('builder: the new question was not saved')
        with app.app_context():
            f = db.session.get(Form, RICH_ID)
            q = next((x for x in f.questions if x.get('title') == 'سؤال من المتصفح'), None)
            if not q or len(q.get('rows', [])) != 3 or not f.s('quiz'):
                note(f'builder: saved data wrong: rows={q and len(q.get("rows", []))} quiz={f.s("quiz")}')
            # أعد النموذج كما كان للتجربة التالية
            f.schema = {'questions': [x for x in f.questions if x.get('title') != 'سؤال من المتصفح']}
            f.settings = dict(f.settings, quiz=False)
            db.session.commit()
        for e in errs:
            note('builder: ' + e)

        print('paste import preview')
        check(page, errs, '/admin/forms/import')
        page.click('[data-example="script"]')
        page.wait_for_selector('#preview .imp-q', timeout=5000)
        if page.locator('#preview .imp-q').count() != 4:
            note('import preview: expected 4 questions')
        page.click('#imp button[type=submit]')
        page.wait_for_url('**/edit', timeout=8000)
        if page.locator('.qcard').count() != 4:
            note('import: created form does not have 4 questions')

        print('people: add, import, invite a group, personal link')
        check(page, errs, '/admin/people')
        page.fill('#p_name', 'هند سامي')
        page.fill('#p_email', 'hind@school.jo')
        page.click('#personForm button[type=submit]')
        page.wait_for_load_state('networkidle')
        if 'hind@school.jo' not in page.inner_text('table[data-table]'):
            note('people: the new person is not in the list')
        csvf = os.path.join(OUT, 'people.csv')
        with open(csvf, 'w', encoding='utf-8-sig') as fh:
            fh.write('الاسم,البريد,المجموعات\nمعلم أول,t1@school.jo,معلمو العلوم\nمعلم ثانٍ,t2@school.jo,معلمو العلوم\n')
        check(page, errs, '/admin/people/import')
        with page.expect_download() as dl:
            page.click('a[href$="template.xlsx"]')
        if os.path.getsize(dl.value.path()) < 3000:
            note('people: template file too small')
        page.set_input_files('#file', csvf)
        page.click('form[enctype] button[type=submit]')
        page.wait_for_selector('.result-card')
        if '2' not in page.inner_text('.result-card .stat-row'):
            note('people import: result not shown')
        check(page, errs, f'/admin/forms/{RICH_ID}/audience')
        page.check('input[name=mode][value=groups]')
        page.check('.pick-box[data-for=groups] label:has-text("معلمو العلوم") input')
        page.click('form.side-form:has(input[name=mode]) button[type=submit]')
        page.wait_for_load_state('networkidle')
        rows = page.locator('table[data-table] tbody tr').count()
        if rows != 2:
            note(f'audience: expected 2 invited people, got {rows}')
        with app.app_context():
            from models import Invitation
            inv_token = Invitation.query.filter_by(form_id=RICH_ID).first().token
        for e in errs:
            note('people: ' + e)

        print('tables: search and export')
        check(page, errs, f'/admin/forms/{RICH_ID}/responses')
        page.fill('.dt-tools input[type=search]', 'طالب 1')
        if page.locator('table[data-table] tbody tr:not([hidden])').count() != 1:
            note('table search: expected one row')
        with page.expect_download() as dl:
            page.click('.dt-export')
        data = open(dl.value.path(), encoding='utf-8-sig').read()
        if 'طالب 1' not in data or 'طالب 2' in data:
            note('table export: wrong rows')

        print('QR code: image, PNG download, print page')
        check(page, errs, f'/admin/forms/{RICH_ID}/edit#share')
        page.wait_for_function("document.getElementById('qrImg').naturalWidth > 0")
        with page.expect_download() as dl:
            page.click('#qrPng')
        png = open(dl.value.path(), 'rb').read()
        if not png[1:4] == b'PNG' or len(png) < 5000:
            note(f'QR PNG download: {len(png)} bytes')
        else:
            with open(os.path.join(OUT, 'qr.png'), 'wb') as fh:
                fh.write(png)
        check(page, errs, f'/admin/forms/{RICH_ID}/qr/print', shot='qr-print.jpg')
        if not page.evaluate("document.querySelector('img.qr').naturalWidth > 0"):
            note('QR print page: image did not load')
        ctx.close()

        # ── الهاتف ──
        iphone = dict(p.devices['iPhone 13'])
        ctx = browser.new_context(**iphone, locale='ar')
        page = ctx.new_page()
        errs = watch(page)
        page.goto(BASE + '/admin/login')
        page.fill('#username', 'admin')
        page.fill('#password', 'admin')
        page.click('button[type=submit]')
        page.wait_for_url('**/admin/')
        print('phone pages')
        for i, u in enumerate(ADMIN_URLS):
            check(page, errs, u, shot=f'm{i:02d}.jpg' if i in (0, 11, 13) else None)
        check(page, errs, f'/admin/forms/{RICH_ID}/edit')
        page.click('#addBtn')
        page.click('#dlgItems [data-add="nps"]')
        saved(page)
        page.click('.qcard.open .q-tools .danger-ico')     # حذف (يطلب تأكيداً)
        page.on('dialog', lambda d: d.accept())
        page.click('.qcard.open .q-tools .danger-ico')
        saved(page)

        print('fill the rich form on a phone (anonymous)')
        anon = browser.new_context(**iphone, locale='ar')
        fp = anon.new_page()
        ferrs = watch(fp)
        check(fp, ferrs, f'/f/{RICH_SLUG}?src=qr', shot='f1-fill.jpg')
        fp.click('#nextBtn')                               # فارغ: يجب أن تظهر أخطاء
        if not fp.locator('.q.has-err').count():
            note('fill: required errors did not appear')
        fp.fill('#q_name', 'ليلى أحمد')
        fp.select_option('#q_grade', 'g8')
        fp.click('[data-qid="like"] .opt >> text=لا')
        if not fp.is_visible('[data-qid="why"]'):
            note('fill: display logic did not show the follow-up question')
        fp.fill('[data-qid="why"] textarea', 'الوقت قصير')
        fp.click('[data-qid="like"] .opt >> text=نعم')
        if fp.is_visible('[data-qid="why"]'):
            note('fill: display logic did not hide the follow-up question')
        fp.click('[data-qid="days"] .opt >> text=الإثنين')
        fp.click('#nextBtn')
        fp.wait_for_selector('[data-qid="rate"]:visible')
        fp.click('[data-qid="rate"] .rating label >> nth=3')
        fp.click('[data-qid="nps"] .sc >> text=10')
        fp.click('[data-qid="scale"] .sc >> text=4')
        fp.click('[data-qid="lik"] tbody tr:nth-child(1) .mx >> nth=4')
        fp.click('[data-qid="lik"] tbody tr:nth-child(2) .mx >> nth=3')
        fp.locator('#q_slide').fill('7')
        fp.screenshot(path=os.path.join(OUT, 'f2-page2.jpg'), type='jpeg', quality=55, full_page=True)
        fp.click('#nextBtn')
        fp.wait_for_selector('[data-qid="rank"]:visible')
        fp.click('[data-qid="rank"] li:nth-child(3) .rk-btn >> nth=0')      # العلوم إلى الأعلى
        fp.fill('[data-qid="sum"] .cs-row:nth-child(1) input', '6')
        fp.fill('[data-qid="sum"] .cs-row:nth-child(2) input', '4')
        fp.fill('#q_when', '2026-12-31')
        img = os.path.join(OUT, 'up.png')
        with open(img, 'wb') as fh:
            fh.write(b'\x89PNG\r\n\x1a\n' + b'\0' * 64)
        fp.set_input_files('#q_doc', img)
        fp.locator('canvas.sig').scroll_into_view_if_needed()
        box = fp.locator('canvas.sig').bounding_box()
        fp.mouse.move(box['x'] + 20, box['y'] + 20)
        fp.mouse.down()
        fp.mouse.move(box['x'] + 120, box['y'] + 60, steps=6)
        fp.mouse.up()
        if not fp.is_visible('#submitBtn'):
            note('fill: submit button not shown on the last page')
        fp.click('#submitBtn')
        fp.wait_for_url('**/done?t=*', timeout=10000)
        check_txt = fp.inner_text('body')
        if 'شكراً' not in check_txt:
            note('fill: thank-you page missing')
        fp.screenshot(path=os.path.join(OUT, 'f3-done.jpg'), type='jpeg', quality=55)
        for e in ferrs:
            note('fill: ' + e)
        with app.app_context():
            r = Response.query.filter_by(form_id=RICH_ID).order_by(Response.id.desc()).first()
            a = r.answers
            expect = {'name': 'ليلى أحمد', 'grade': 'g8', 'like': 'y', 'days': ['d2'], 'rate': 4, 'nps': 10, 'scale': 4,
                      'slide': 7, 'rank': ['a', 'c', 'b'], 'sum': {'x': 6, 'z': 4}, 'when': '2026-12-31', 'src': 'qr'}
            for k, v in expect.items():
                if a.get(k) != v:
                    note(f'fill: answer {k} = {a.get(k)!r}, expected {v!r}')
            if 'why' in a:
                note('fill: hidden question answer was saved')
            if len(a.get('lik', {})) != 2 or not a.get('doc') or not a.get('sig'):
                note(f'fill: grid/file/signature missing: {a.get("lik")}, {a.get("doc")}, {a.get("sig")}')
            if r.device != 'mobile' or r.os != 'iOS' or not (r.meta or {}).get('screen'):
                note(f'fill: device info {r.device} {r.os} {r.meta}')

        print('opening a personal invitation link is recorded')
        check(fp, ferrs, f'/f/{RICH_SLUG}?inv={inv_token}')
        with app.app_context():
            from models import Invitation
            if not Invitation.query.filter_by(token=inv_token).one().opened_at:
                note('invitation: opening the link was not recorded')

        print('english switch on a bilingual form')
        check(fp, ferrs, f'/f/{RICH_SLUG}?lang=en', lang='en')
        if 'Next' not in fp.inner_text('#nextBtn') and 'Submit' not in fp.inner_text('#fillForm'):
            note('english: buttons not in English')

        print('branching')
        check(fp, ferrs, f'/f/{BR_SLUG}')
        fp.click('.opt >> text=لا')
        fp.click('#nextBtn')
        if 'الأسباب' not in fp.inner_text('.page:not([hidden])'):
            note('branching: "no" did not jump to the reasons section')
        fp.click('#backBtn')
        fp.click('.opt >> text=نعم')
        fp.click('#nextBtn')
        txt = fp.inner_text('.page:not([hidden])')
        if 'الأنشطة' not in txt or not fp.is_visible('#submitBtn'):
            note('branching: "yes" did not go to activities then submit')

        print('email sign-in gate with respondent details')
        check(fp, ferrs, f'/f/{GATE_SLUG}', shot='g1-login.jpg')
        if not fp.is_visible('#msBtn'):
            note('gate: Microsoft sign-in button missing')
        fp.route('https://login.microsoftonline.com/**', lambda route: route.fulfill(status=200, body='microsoft'))
        fp.click('#msBtn')
        fp.wait_for_url('https://login.microsoftonline.com/e2e-tenant/oauth2/v2.0/authorize*')
        if 'auth%2Fms%2Fcallback' not in fp.url:
            note('gate: Microsoft redirect URI missing')
        fp.goto(BASE + f'/f/{GATE_SLUG}/login', wait_until='networkidle')
        fp.fill('#email', 'student@school.jo')
        fp.click('.gate-form button[type=submit]')
        code = fp.inner_text('#devCode')
        fp.fill('#code', code)
        fp.click('.gate-form button[type=submit]')
        fp.wait_for_url('**/details*')
        fp.fill('#f_name', 'سامي')
        fp.select_option('#f_grade', label='الثامن')
        fp.click('.gate-form button[type=submit]')
        fp.wait_for_url(f'**/f/{GATE_SLUG}*')
        fp.fill('[data-qid="a"] input', 'ممتاز')
        fp.click('#submitBtn')
        fp.wait_for_url('**/done?t=*', timeout=10000)
        with app.app_context():
            r = Response.query.filter_by(form_id=GATE_ID).one()
            if r.email != 'student@school.jo' or r.filler != {'name': 'سامي', 'grade': 'الثامن'}:
                note(f'gate: saved {r.email} {r.filler}')
        for e in ferrs:
            note('gate: ' + e)
        browser.close()
finally:
    srv.terminate()

print()
print(f'screenshots: {OUT}')
if problems:
    print(f'{len(problems)} problem(s)')
    sys.exit(1)
print('E2E OK')
