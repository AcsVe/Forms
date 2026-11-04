"""محرّك النموذج: أنواع الأسئلة، وتنظيف البنية، والصفحات، ومنطق الإظهار والتفرّع، والتحقق من الإجابات، والتصحيح.

الملف static/js/fill.js يطبّق المنطق نفسه في المتصفح؛ والخادم يعيد حسابه عند الإرسال فلا يُقبل إلا ما يُظهره المنطق.

شكل السؤال (dict):
    id, type, title, title_en, help, help_en, required,
    choices: [{id, label, label_en, image, goto}], other: bool, shuffle: bool,
    rows: [{id, label, label_en}], cols: [{id, label, label_en}],
    min, max, step, min_label, max_label, icon, total,
    validation: {kind: email|phone|url|regex|length|number, min, max, pattern},
    min_select, max_select, param (للحقل المخفي), accept, max_files,
    logic: {show_if: {mode: all|any, rules: [{q, op, value}]}},
    next (للقسم: إلى أين بعد هذا القسم), media: {image, video},
    quiz: {points, correct: [...], tolerance, feedback_ok, feedback_bad}
"""
import re
import secrets
import unicodedata

# type → (ar, en, group, icon)
TYPES = {
    'short_text':   ('نص قصير', 'Short answer', 'text', 'fa-font'),
    'long_text':    ('فقرة', 'Paragraph', 'text', 'fa-align-right'),
    'email':        ('بريد إلكتروني', 'Email', 'text', 'fa-at'),
    'phone':        ('رقم هاتف', 'Phone number', 'text', 'fa-phone'),
    'url':          ('رابط موقع', 'Website link', 'text', 'fa-link'),
    'number':       ('رقم', 'Number', 'text', 'fa-hashtag'),
    'single':       ('اختيار من متعدد', 'Multiple choice', 'choice', 'fa-circle-dot'),
    'multi':        ('مربعات اختيار', 'Checkboxes', 'choice', 'fa-square-check'),
    'dropdown':     ('قائمة منسدلة', 'Dropdown', 'choice', 'fa-caret-down'),
    'yesno':        ('نعم / لا', 'Yes / No', 'choice', 'fa-toggle-on'),
    'image_choice': ('اختيار بالصور', 'Image choice', 'choice', 'fa-images'),
    'scale':        ('مقياس خطي', 'Linear scale', 'scale', 'fa-ruler-horizontal'),
    'rating':       ('تقييم', 'Rating', 'scale', 'fa-star'),
    'nps':          ('مؤشر صافي الترويج (NPS)', 'Net Promoter Score', 'scale', 'fa-gauge-high'),
    'slider':       ('شريط تمرير', 'Slider', 'scale', 'fa-sliders'),
    'likert':       ('مقياس ليكرت', 'Likert scale', 'matrix', 'fa-table-list'),
    'matrix':       ('شبكة اختيار واحد', 'Multiple-choice grid', 'matrix', 'fa-table-cells'),
    'matrix_multi': ('شبكة مربعات اختيار', 'Checkbox grid', 'matrix', 'fa-table-cells-large'),
    'ranking':      ('ترتيب', 'Ranking', 'other', 'fa-arrow-down-1-9'),
    'constant_sum': ('توزيع النقاط', 'Constant sum', 'other', 'fa-chart-pie'),
    'date':         ('تاريخ', 'Date', 'datetime', 'fa-calendar-day'),
    'time':         ('وقت', 'Time', 'datetime', 'fa-clock'),
    'datetime':     ('تاريخ ووقت', 'Date and time', 'datetime', 'fa-calendar-check'),
    'file':         ('رفع ملف', 'File upload', 'other', 'fa-paperclip'),
    'signature':    ('توقيع', 'Signature', 'other', 'fa-signature'),
    'hidden':       ('حقل مخفي من الرابط', 'Hidden field (from the link)', 'other', 'fa-eye-slash'),
    'section':      ('قسم جديد (صفحة)', 'Section (new page)', 'layout', 'fa-layer-group'),
    'statement':    ('نص أو صورة أو فيديو', 'Text, image or video', 'layout', 'fa-photo-film'),
}
GROUPS = [('text', 'النصوص', 'Text'), ('choice', 'الاختيارات', 'Choices'), ('scale', 'المقاييس', 'Scales'),
          ('matrix', 'الشبكات', 'Grids'), ('datetime', 'التاريخ والوقت', 'Date and time'),
          ('other', 'أخرى', 'More'), ('layout', 'التخطيط', 'Layout')]

CHOICE_TYPES = {'single', 'multi', 'dropdown', 'yesno', 'image_choice'}
ONE_CHOICE = {'single', 'dropdown', 'yesno', 'image_choice'}
MATRIX_TYPES = {'likert', 'matrix', 'matrix_multi'}
NUMERIC_TYPES = {'number', 'scale', 'rating', 'nps', 'slider'}
TEXT_TYPES = {'short_text', 'long_text', 'email', 'phone', 'url'}
NO_ANSWER = {'section', 'statement'}
GOTO_TYPES = ONE_CHOICE
SUBMIT = '__submit__'
OTHER = '__other__'

LIKERT_AR = ['أعارض بشدة', 'أعارض', 'محايد', 'أوافق', 'أوافق بشدة']
LIKERT_EN = ['Strongly disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly agree']

_ID = re.compile(r'^[A-Za-z0-9_\-]{1,40}$')


def uid(prefix='q'):
    return f'{prefix}_{secrets.token_hex(4)}'


def _s(v, n=2000):
    return str(v if v is not None else '').strip()[:n]


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return int(f) if f == int(f) else f


def _options(items, prefix, keep_extra=False):
    out, seen = [], set()
    for it in items or []:
        if isinstance(it, str):
            it = {'label': it}
        if not isinstance(it, dict):
            continue
        oid = _s(it.get('id'), 40)
        if not _ID.match(oid) or oid in seen:
            oid = uid(prefix)
        seen.add(oid)
        o = {'id': oid, 'label': _s(it.get('label'), 500) or '—'}
        if it.get('label_en'):
            o['label_en'] = _s(it.get('label_en'), 500)
        if keep_extra:
            if it.get('image'):
                o['image'] = _s(it.get('image'), 500)
            if it.get('goto'):
                o['goto'] = _s(it.get('goto'), 40)
            if it.get('points') not in (None, ''):
                o['points'] = _num(it.get('points'), 0)
        out.append(o)
    return out


def normalize_question(q):
    """سؤال من المحرّر أو الاستيراد ← شكل نظيف آمن (يُستدعى قبل كل حفظ)."""
    if not isinstance(q, dict):
        return None
    t = q.get('type') if q.get('type') in TYPES else 'short_text'
    qid = _s(q.get('id'), 40)
    out = {'id': qid if _ID.match(qid) else uid('s' if t == 'section' else 'q'), 'type': t,
           'title': _s(q.get('title'), 1000)}
    for k in ('title_en', 'help', 'help_en'):
        if q.get(k):
            out[k] = _s(q.get(k), 4000)
    if t not in NO_ANSWER and t != 'hidden':
        out['required'] = bool(q.get('required'))
    if t in CHOICE_TYPES or t in ('ranking', 'constant_sum'):
        ch = q.get('choices')
        if t == 'yesno':
            ch = ch or [{'id': 'yes', 'label': 'نعم', 'label_en': 'Yes'}, {'id': 'no', 'label': 'لا', 'label_en': 'No'}]
        out['choices'] = _options(ch or [{'label': 'الخيار 1'}, {'label': 'الخيار 2'}], 'c', keep_extra=True)
        if t in ('single', 'multi', 'dropdown') and q.get('other'):
            out['other'] = True
        if t in ('single', 'multi', 'dropdown', 'image_choice', 'ranking') and q.get('shuffle'):
            out['shuffle'] = True
    if t == 'multi':
        for k in ('min_select', 'max_select'):
            if _num(q.get(k)):
                out[k] = int(_num(q.get(k)))
    if t == 'constant_sum':
        out['total'] = _num(q.get('total'), 100) or 100
    if t in MATRIX_TYPES:
        out['rows'] = _options(q.get('rows') or [{'label': 'العبارة 1'}, {'label': 'العبارة 2'}], 'r')
        cols = q.get('cols')
        if t == 'likert' and not cols:
            cols = [{'label': a, 'label_en': e} for a, e in zip(LIKERT_AR, LIKERT_EN)]
        out['cols'] = _options(cols or [{'label': 'العمود 1'}, {'label': 'العمود 2'}], 'k')
    if t == 'scale':
        lo, hi = _num(q.get('min'), 1), _num(q.get('max'), 5)
        lo = 0 if lo not in (0, 1) else lo
        hi = max(2, min(10, int(hi or 5)))
        out.update(min=lo, max=hi)
    if t == 'rating':
        out['max'] = max(3, min(10, int(_num(q.get('max'), 5) or 5)))
        out['icon'] = q.get('icon') if q.get('icon') in ('star', 'heart', 'smile', 'thumb') else 'star'
    if t == 'nps':
        out.update(min=0, max=10)
    if t in ('slider', 'number'):
        for k in ('min', 'max', 'step'):
            if _num(q.get(k)) is not None:
                out[k] = _num(q.get(k))
        if t == 'slider':
            out.setdefault('min', 0)
            out.setdefault('max', 100)
            out.setdefault('step', 1)
            if out['max'] <= out['min']:
                out['max'] = out['min'] + 100
    if t in ('scale', 'nps', 'slider', 'rating'):
        for k in ('min_label', 'max_label', 'min_label_en', 'max_label_en'):
            if q.get(k):
                out[k] = _s(q.get(k), 200)
    if t in TEXT_TYPES:
        v = q.get('validation') or {}
        if isinstance(v, dict) and v.get('kind') in ('length', 'regex'):
            out['validation'] = {'kind': v['kind'], 'min': _num(v.get('min')), 'max': _num(v.get('max')),
                                 'pattern': _s(v.get('pattern'), 300), 'message': _s(v.get('message'), 300)}
        if q.get('placeholder'):
            out['placeholder'] = _s(q.get('placeholder'), 200)
    if t == 'file':
        out['max_files'] = max(1, min(10, int(_num(q.get('max_files'), 1) or 1)))
        out['max_mb'] = max(1, min(25, int(_num(q.get('max_mb'), 10) or 10)))
        out['accept'] = q.get('accept') if q.get('accept') in ('any', 'image', 'pdf', 'doc', 'media') else 'any'
    if t == 'hidden':
        p = re.sub(r'[^A-Za-z0-9_]', '', _s(q.get('param'), 40))
        out['param'] = p or 'ref'
    if t == 'section':
        if q.get('next'):
            out['next'] = _s(q.get('next'), 40)
    media = q.get('media') or {}
    if isinstance(media, dict) and (media.get('image') or media.get('video')):
        out['media'] = {k: _s(media.get(k), 500) for k in ('image', 'video') if media.get(k)}
    logic = (q.get('logic') or {}).get('show_if') if isinstance(q.get('logic'), dict) else None
    if isinstance(logic, dict) and logic.get('rules'):
        rules = [{'q': _s(r.get('q'), 40), 'op': r.get('op') if r.get('op') in OPS else 'eq', 'value': _s(r.get('value'), 500)}
                 for r in logic['rules'] if isinstance(r, dict) and r.get('q')]
        if rules:
            out['logic'] = {'show_if': {'mode': 'any' if logic.get('mode') == 'any' else 'all', 'rules': rules}}
    quiz = q.get('quiz')
    if isinstance(quiz, dict) and t not in NO_ANSWER:
        qz = {'points': _num(quiz.get('points'), 0) or 0}
        corr = quiz.get('correct')
        if isinstance(corr, str):
            corr = [c.strip() for c in corr.split('|') if c.strip()]
        qz['correct'] = [_s(c, 500) for c in (corr or [])][:50]
        if _num(quiz.get('tolerance')):
            qz['tolerance'] = _num(quiz.get('tolerance'))
        if quiz.get('partial'):
            qz['partial'] = True
        for k in ('feedback_ok', 'feedback_bad'):
            if quiz.get(k):
                qz[k] = _s(quiz.get(k), 1000)
        if qz['points'] or qz['correct']:
            out['quiz'] = qz
    return out


OPS = {'eq', 'neq', 'contains', 'not_contains', 'gt', 'lt', 'gte', 'lte', 'answered', 'empty'}


def normalize_schema(schema):
    qs = [normalize_question(q) for q in (schema or {}).get('questions') or []]
    qs = [q for q in qs if q][:500]
    seen = set()
    for q in qs:                          # معرّفات فريدة داخل النموذج
        while q['id'] in seen:
            q['id'] = uid('s' if q['type'] == 'section' else 'q')
        seen.add(q['id'])
    return {'questions': qs}


def renew_ids(schema):
    """نسخة بمعرّفات جديدة لكل الأسئلة مع تحديث المنطق والتفرّع (لدمج أسئلة نموذج في آخر)."""
    import copy
    s = copy.deepcopy(schema)
    m = {}
    for q in s['questions']:
        old = q['id']
        q['id'] = uid('s' if q['type'] == 'section' else 'q')
        m[old] = q['id']
    for q in s['questions']:
        for c in q.get('choices') or []:
            if c.get('goto') in m:
                c['goto'] = m[c['goto']]
        if q.get('next') in m:
            q['next'] = m[q['next']]
        for r in ((q.get('logic') or {}).get('show_if') or {}).get('rules') or []:
            if r.get('q') in m:
                r['q'] = m[r['q']]
    return s


# ── الصفحات والمنطق ──────────────────────────────────────────────────────────

def pages(questions):
    ps = [{'section': None, 'items': []}]
    for q in questions:
        if q['type'] == 'section':
            ps.append({'section': q, 'items': []})
        else:
            ps[-1]['items'].append(q)
    if len(ps) > 1 and not ps[0]['items']:
        ps.pop(0)
    return ps


def is_empty(v):
    return v is None or v == '' or v == [] or v == {}


def norm_text(v):
    s = unicodedata.normalize('NFKC', str(v or '')).lower()
    s = re.sub('[ً-ْـ⁦-⁩]', '', s)
    s = re.sub('[أإآ]', 'ا', s).replace('ة', 'ه').replace('ى', 'ي')
    return re.sub(r'\s+', ' ', s).strip()


def check_rule(rule, answers):
    v = answers.get(rule.get('q'))
    op, target = rule.get('op', 'eq'), rule.get('value', '')
    if op == 'answered':
        return not is_empty(v)
    if op == 'empty':
        return is_empty(v)
    if is_empty(v):
        return op in ('neq', 'not_contains')
    if isinstance(v, dict):
        v = [x for val in v.values() for x in (val if isinstance(val, list) else [val])]
    if isinstance(v, list):
        has = str(target) in [str(x) for x in v]
        return has if op in ('eq', 'contains') else (not has if op in ('neq', 'not_contains') else False)
    if op in ('gt', 'lt', 'gte', 'lte'):
        a, b = _num(v), _num(target)
        if a is None or b is None:
            return False
        return {'gt': a > b, 'lt': a < b, 'gte': a >= b, 'lte': a <= b}[op]
    a, b = norm_text(v), norm_text(target)
    if op == 'eq':
        return a == b
    if op == 'neq':
        return a != b
    if op == 'contains':
        return b in a
    if op == 'not_contains':
        return b not in a
    return False


def is_visible(item, answers):
    cond = ((item or {}).get('logic') or {}).get('show_if')
    if not cond or not cond.get('rules'):
        return True
    res = [check_rule(r, answers) for r in cond['rules']]
    return any(res) if cond.get('mode') == 'any' else all(res)


def walk(questions, answers):
    """يمشي الصفحات كما يمشيها المستجيب: (الصفحات التي زارها، الأسئلة الظاهرة، الإجابات المقبولة).
    القفز إلى الأمام فقط، فلا تنشأ حلقة."""
    ps = pages(questions)
    index = {p['section']['id']: i for i, p in enumerate(ps) if p['section']}
    eff, visited, shown = {}, [], []
    i = 0
    while 0 <= i < len(ps):
        p = ps[i]
        if p['section'] and not is_visible(p['section'], eff):
            i += 1
            continue
        visited.append(i)
        jump = None
        for q in p['items']:
            if not is_visible(q, eff):
                continue
            shown.append(q)
            if q['type'] in NO_ANSWER:
                continue
            if q['id'] in answers and not is_empty(answers[q['id']]):
                eff[q['id']] = answers[q['id']]
                if q['type'] == 'single' and q.get('other') and answers.get(q['id']) == OTHER:
                    eff[q['id'] + ':other'] = answers.get(q['id'] + ':other', '')
            if q['type'] in GOTO_TYPES and q['id'] in eff:
                ch = next((c for c in q.get('choices') or [] if c['id'] == eff[q['id']]), None)
                if ch and ch.get('goto'):
                    jump = ch['goto']
        if jump is None and p['section'] and p['section'].get('next'):
            jump = p['section']['next']
        if jump == SUBMIT:
            break
        if jump and jump in index and index[jump] > i:
            i = index[jump]
        else:
            i += 1
    return visited, shown, eff


# ── التحقق من الإجابة ────────────────────────────────────────────────────────

_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE = re.compile(r'^\+?[0-9\s\-()]{6,20}$')
_URL = re.compile(r'^(https?://)?[\w\-]+(\.[\w\-]+)+(/\S*)?$', re.I)
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_TIME = re.compile(r'^\d{2}:\d{2}$')
_DT = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$')


class AnswerError(ValueError):
    def __init__(self, qid, ar, en):
        super().__init__(ar)
        self.qid, self.ar, self.en = qid, ar, en


def _ids(items):
    return [o['id'] for o in items or []]


def clean_answer(q, raw, answers):
    """القيمة المقبولة للسؤال، أو None إن كانت فارغة؛ يرفع AnswerError إن كانت غير صالحة."""
    t, qid = q['type'], q['id']

    def bad(ar, en):
        raise AnswerError(qid, ar, en)
    if is_empty(raw):
        return None
    if t in TEXT_TYPES or t == 'hidden':
        v = _s(raw, 10000 if t == 'long_text' else 1000)
        if not v:
            return None
        if t == 'email' and not _EMAIL.match(v):
            bad('اكتب بريداً إلكترونياً صحيحاً.', 'Enter a valid email address.')
        if t == 'phone' and not _PHONE.match(v):
            bad('اكتب رقم هاتف صحيحاً.', 'Enter a valid phone number.')
        if t == 'url' and not _URL.match(v):
            bad('اكتب رابطاً صحيحاً.', 'Enter a valid link.')
        val = q.get('validation') or {}
        if val.get('kind') == 'length':
            if val.get('min') and len(v) < val['min']:
                bad(val.get('message') or f'الحد الأدنى {val["min"]} حرفاً.', val.get('message') or f'At least {val["min"]} characters.')
            if val.get('max') and len(v) > val['max']:
                bad(val.get('message') or f'الحد الأعلى {val["max"]} حرفاً.', val.get('message') or f'At most {val["max"]} characters.')
        if val.get('kind') == 'regex' and val.get('pattern'):
            try:
                ok = re.fullmatch(val['pattern'], v)
            except re.error:
                ok = True
            if not ok:
                bad(val.get('message') or 'الإجابة لا تطابق الصيغة المطلوبة.', val.get('message') or 'The answer does not match the required format.')
        return v
    if t in ('number', 'slider', 'scale', 'rating', 'nps'):
        n = _num(raw)
        if n is None:
            bad('اكتب رقماً.', 'Enter a number.')
        lo = q.get('min', 1 if t == 'rating' else None)
        hi = q.get('max')
        if lo is not None and n < lo or hi is not None and n > hi:
            bad(f'القيمة يجب أن تكون بين {lo if lo is not None else "…"} و{hi if hi is not None else "…"}.',
                f'The value must be between {lo if lo is not None else "…"} and {hi if hi is not None else "…"}.')
        if t in ('scale', 'rating', 'nps') and n != int(n):
            bad('اختر قيمة من المقياس.', 'Choose a value on the scale.')
        return n
    if t in ONE_CHOICE:
        v = _s(raw, 40)
        if v == OTHER and q.get('other'):
            return v
        if v not in _ids(q.get('choices')):
            bad('اختر أحد الخيارات.', 'Choose one of the options.')
        return v
    if t == 'multi':
        vals = raw if isinstance(raw, list) else [raw]
        allowed = set(_ids(q.get('choices'))) | ({OTHER} if q.get('other') else set())
        vals = [str(v) for v in vals if str(v) in allowed]
        vals = list(dict.fromkeys(vals))
        if not vals:
            return None
        if q.get('min_select') and len(vals) < q['min_select']:
            bad(f'اختر {q["min_select"]} على الأقل.', f'Choose at least {q["min_select"]}.')
        if q.get('max_select') and len(vals) > q['max_select']:
            bad(f'اختر {q["max_select"]} على الأكثر.', f'Choose at most {q["max_select"]}.')
        return vals
    if t in ('likert', 'matrix', 'matrix_multi'):
        if not isinstance(raw, dict):
            bad('إجابة الشبكة غير صالحة.', 'Invalid grid answer.')
        rows, cols = set(_ids(q.get('rows'))), set(_ids(q.get('cols')))
        out = {}
        for r, v in raw.items():
            if r not in rows:
                continue
            if t == 'matrix_multi':
                vs = [str(x) for x in (v if isinstance(v, list) else [v]) if str(x) in cols]
                if vs:
                    out[r] = list(dict.fromkeys(vs))
            elif str(v) in cols:
                out[r] = str(v)
        if not out:
            return None
        if q.get('required') and len(out) < len(rows):
            bad('أجب عن كل صفوف الشبكة.', 'Answer every row of the grid.')
        return out
    if t == 'ranking':
        ids = _ids(q.get('choices'))
        vals = [str(v) for v in (raw if isinstance(raw, list) else []) if str(v) in ids]
        vals = list(dict.fromkeys(vals))
        if len(vals) != len(ids):
            bad('رتّب كل العناصر.', 'Rank every item.')
        return vals
    if t == 'constant_sum':
        if not isinstance(raw, dict):
            bad('إجابة غير صالحة.', 'Invalid answer.')
        ids = set(_ids(q.get('choices')))
        out = {}
        for k, v in raw.items():
            n = _num(v)
            if k in ids and n is not None:
                if n < 0:
                    bad('لا تُقبل القيم السالبة.', 'Negative values are not allowed.')
                out[k] = n
        if not out or not any(out.values()):
            return None
        total = q.get('total', 100)
        if abs(sum(out.values()) - total) > 1e-6:
            bad(f'يجب أن يكون المجموع {total} (الحالي {sum(out.values()):g}).', f'The total must be {total} (now {sum(out.values()):g}).')
        return out
    if t == 'date':
        v = _s(raw, 10)
        if not _DATE.match(v):
            bad('اكتب التاريخ بالصيغة 2026-12-31.', 'Use the date format 2026-12-31.')
        return v
    if t == 'time':
        v = _s(raw, 5)
        if not _TIME.match(v):
            bad('اكتب الوقت بالصيغة 14:30.', 'Use the time format 14:30.')
        return v
    if t == 'datetime':
        v = _s(raw, 16)
        if not _DT.match(v):
            bad('اختر التاريخ والوقت.', 'Choose a date and time.')
        return v
    if t in ('file', 'signature'):
        return raw if isinstance(raw, list) and raw else None
    return None


def validate(questions, raw_answers):
    """(الإجابات النظيفة، الأخطاء {qid: (ar, en)}، الأسئلة الظاهرة). الأسئلة المخفية بالمنطق لا تُحفظ ولا تُلزم."""
    raw = dict(raw_answers or {})
    _, shown, _ = walk(questions, raw)
    clean, errors = {}, {}
    # أعد المشي بالإجابات النظيفة: قيمة غير صالحة لا تفتح فرعاً
    for q in shown:
        if q['type'] in NO_ANSWER:
            continue
        try:
            v = clean_answer(q, raw.get(q['id']), raw)
        except AnswerError as e:
            errors[q['id']] = (e.ar, e.en)
            continue
        if v is None:
            if q.get('required'):
                errors[q['id']] = ('هذا السؤال مطلوب.', 'This question is required.')
            continue
        clean[q['id']] = v
        if v == OTHER or (isinstance(v, list) and OTHER in v):
            other = _s(raw.get(q['id'] + ':other'), 500)
            if not other and q.get('required'):
                errors[q['id']] = ('اكتب الإجابة الأخرى.', 'Write your other answer.')
            clean[q['id'] + ':other'] = other
    _, shown2, eff = walk(questions, clean)
    ids2 = {q['id'] for q in shown2}
    clean = {k: v for k, v in clean.items() if k.split(':')[0] in ids2}
    errors = {k: v for k, v in errors.items() if k in ids2}
    for q in shown2:                  # سؤال مطلوب ظهر بعد تنظيف الإجابات
        if q.get('required') and q['id'] not in clean and q['id'] not in errors and q['type'] not in NO_ANSWER:
            errors[q['id']] = ('هذا السؤال مطلوب.', 'This question is required.')
    return clean, errors, shown2


# ── التصحيح (وضع الاختبار) ───────────────────────────────────────────────────

def grade_question(q, value):
    """(الدرجة، الدرجة الكاملة، صحيح؟) — None للصحيح إن كان السؤال يحتاج تصحيحاً يدوياً."""
    qz = q.get('quiz') or {}
    pts = float(qz.get('points') or 0)
    corr = qz.get('correct') or []
    if not pts:
        return 0.0, 0.0, None
    if not corr:
        return 0.0, pts, None          # يدوي (فقرة مثلاً)
    if is_empty(value):
        return 0.0, pts, False
    t = q['type']
    if t in ONE_CHOICE:
        ok = str(value) in corr
        return (pts if ok else 0.0), pts, ok
    if t == 'multi':
        sel, good = set(value), set(corr)
        if sel == good:
            return pts, pts, True
        if qz.get('partial') and good:
            frac = max(0.0, (len(sel & good) - len(sel - good)) / len(good))
            return round(pts * frac, 2), pts, False
        return 0.0, pts, False
    if t in ('number', 'slider', 'scale', 'rating', 'nps'):
        tol = float(qz.get('tolerance') or 0)
        ok = any(_num(c) is not None and abs(float(value) - float(_num(c))) <= tol for c in corr)
        return (pts if ok else 0.0), pts, ok
    if t == 'ranking':
        ok = list(value) == list(corr)
        return (pts if ok else 0.0), pts, ok
    ok = norm_text(value) in {norm_text(c) for c in corr}
    return (pts if ok else 0.0), pts, ok


def grade(questions, answers, manual=None):
    """(الدرجة، الدرجة الكاملة، تفاصيل {qid: (درجة، كاملة، صحيح)}) للأسئلة الظاهرة فقط."""
    _, shown, _ = walk(questions, answers)
    manual = manual or {}
    score = total = 0.0
    detail = {}
    for q in shown:
        if q['type'] in NO_ANSWER or not (q.get('quiz') or {}).get('points'):
            continue
        s, m, ok = grade_question(q, answers.get(q['id']))
        if q['id'] in manual and _num(manual[q['id']]) is not None:
            s = max(0.0, min(m, float(_num(manual[q['id']]))))
            ok = s >= m
        score += s
        total += m
        detail[q['id']] = (s, m, ok)
    return round(score, 2), round(total, 2), detail


# ── عرض الإجابة نصاً (للجداول والتصدير) ─────────────────────────────────────

def _label(items, oid, lang='ar'):
    for o in items or []:
        if o['id'] == oid:
            return (o.get('label_en') or o['label']) if lang == 'en' else o['label']
    return str(oid)


def answer_text(q, answers, lang='ar'):
    v = answers.get(q['id'])
    if is_empty(v):
        return ''
    t = q['type']
    other = answers.get(q['id'] + ':other', '')
    oth = ('أخرى' if lang != 'en' else 'Other') + (f': {other}' if other else '')
    if t in ONE_CHOICE:
        return oth if v == OTHER else _label(q.get('choices'), v, lang)
    if t == 'multi':
        return '، '.join(oth if x == OTHER else _label(q.get('choices'), x, lang) for x in v)
    if t == 'ranking':
        return ' ← '.join(f'{i + 1}. {_label(q.get("choices"), x, lang)}' for i, x in enumerate(v))
    if t == 'constant_sum':
        return '، '.join(f'{_label(q.get("choices"), k, lang)}: {n:g}' for k, n in v.items())
    if t in MATRIX_TYPES:
        parts = []
        for r in q.get('rows') or []:
            if r['id'] in v:
                c = v[r['id']]
                cs = '، '.join(_label(q.get('cols'), x, lang) for x in c) if isinstance(c, list) else _label(q.get('cols'), c, lang)
                parts.append(f'{_label(q.get("rows"), r["id"], lang)}: {cs}')
        return ' | '.join(parts)
    if t in ('file', 'signature'):
        return '، '.join(f.get('name', 'ملف') for f in v if isinstance(f, dict))
    if isinstance(v, float):
        return f'{v:g}'
    return str(v)


def qtitle(q, lang='ar'):
    return (q.get('title_en') or q.get('title') or '') if lang == 'en' else (q.get('title') or q.get('title_en') or '')
