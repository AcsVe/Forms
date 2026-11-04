"""تحويل نص ملصوق إلى نموذج: قائمة أسئلة مكتوبة، أو JSON، أو سكربت Google Apps Script.

    parse(text) → {'title', 'description', 'questions': [...], 'format': 'text'|'json'|'script', 'warnings': [...]}

صيغة النص (تظهر للمستخدم في صفحة اللصق):
    # عنوان النموذج
    > وصف النموذج
    ## اسم القسم                     (أو ---) قسم وصفحة جديدة
    1. نص السؤال *                   النجمة في النهاية = سؤال مطلوب
    - خيار                           خيارات اختيار واحد   ( ) خيار
    [ ] خيار                         مربعات اختيار
    - خيار ✓                         الإجابة الصحيحة في الاختبار
    | ممتاز | جيد | ضعيف |           أعمدة الشبكة (والصفوف بخيارات -)
    نوع السؤال بين قوسين معقوفين: [فقرة] [تاريخ] [رقم] [تقييم] [1-10] [NPS] [ملف] [قائمة] [ترتيب] [شبكة] [ليكرت] [3 درجات]
"""
import json
import re

from schema import LIKERT_AR, normalize_schema

ALIASES = {
    # عربي
    'نص': 'short_text', 'نص قصير': 'short_text', 'قصير': 'short_text', 'فقرة': 'long_text', 'نص طويل': 'long_text',
    'بريد': 'email', 'بريد إلكتروني': 'email', 'هاتف': 'phone', 'جوال': 'phone', 'رابط': 'url', 'رقم': 'number',
    'اختيار': 'single', 'اختيار واحد': 'single', 'متعدد': 'multi', 'اختيار متعدد': 'multi', 'مربعات': 'multi',
    'قائمة': 'dropdown', 'قائمة منسدلة': 'dropdown', 'نعم لا': 'yesno', 'نعم/لا': 'yesno', 'صور': 'image_choice',
    'تقييم': 'rating', 'نجوم': 'rating', 'مقياس': 'scale', 'شريط': 'slider', 'ليكرت': 'likert', 'شبكة': 'matrix',
    'مصفوفة': 'matrix', 'شبكة متعددة': 'matrix_multi', 'ترتيب': 'ranking', 'توزيع': 'constant_sum',
    'توزيع النقاط': 'constant_sum', 'تاريخ': 'date', 'وقت': 'time', 'تاريخ ووقت': 'datetime', 'ملف': 'file',
    'رفع ملف': 'file', 'توقيع': 'signature', 'مخفي': 'hidden', 'قسم': 'section', 'نص عرض': 'statement',
    # English and other products' names
    'text': 'short_text', 'short': 'short_text', 'short_text': 'short_text', 'shortanswer': 'short_text',
    'paragraph': 'long_text', 'paragraph_text': 'long_text', 'long': 'long_text', 'long_text': 'long_text',
    'textarea': 'long_text', 'comment': 'long_text', 'essay': 'long_text', 'email': 'email', 'phone': 'phone',
    'url': 'url', 'website': 'url', 'number': 'number', 'numeric': 'number', 'choice': 'single', 'radio': 'single',
    'single': 'single', 'multiple_choice': 'single', 'multiplechoice': 'single', 'mcq': 'single',
    'checkbox': 'multi', 'checkboxes': 'multi', 'multi': 'multi', 'multiple': 'multi', 'list': 'dropdown',
    'dropdown': 'dropdown', 'select': 'dropdown', 'yesno': 'yesno', 'yes/no': 'yesno', 'boolean': 'yesno',
    'image_choice': 'image_choice', 'rating': 'rating', 'stars': 'rating', 'star': 'rating', 'scale': 'scale',
    'linear_scale': 'scale', 'nps': 'nps', 'net_promoter': 'nps', 'slider': 'slider', 'likert': 'likert',
    'grid': 'matrix', 'matrix': 'matrix', 'checkbox_grid': 'matrix_multi', 'matrix_multi': 'matrix_multi',
    'ranking': 'ranking', 'rank': 'ranking', 'constant_sum': 'constant_sum', 'date': 'date', 'time': 'time',
    'datetime': 'datetime', 'date_time': 'datetime', 'file': 'file', 'file_upload': 'file', 'upload': 'file',
    'signature': 'signature', 'hidden': 'hidden', 'section': 'section', 'page_break': 'section',
    'pagebreak': 'section', 'section_header': 'statement', 'statement': 'statement', 'description': 'statement',
    'image': 'statement', 'video': 'statement',
}


def _alias(name):
    k = str(name or '').strip().lower().replace('-', '_').replace(' ', '_')
    return ALIASES.get(k) or ALIASES.get(k.replace('_', ' ')) or ALIASES.get(str(name or '').strip()) or None


def parse(text):
    text = (text or '').strip().lstrip('﻿')
    if not text:
        return {'title': '', 'description': '', 'questions': [], 'format': 'text', 'warnings': []}
    if text[:1] in '{[':
        try:
            return _from_json(json.loads(text))
        except ValueError:
            pass
    if re.search(r'\.add\w+Item\s*\(', text) or 'FormApp' in text:
        return _from_script(text)
    return _from_text(text)


# ── JSON ─────────────────────────────────────────────────────────────────────

def _from_json(data):
    warnings = []
    if isinstance(data, list):
        data = {'questions': data}
    if not isinstance(data, dict):
        return {'title': '', 'description': '', 'questions': [], 'format': 'json', 'warnings': ['صيغة JSON غير معروفة.']}
    form = data.get('form') if isinstance(data.get('form'), dict) else data
    items = form.get('questions') or form.get('items') or form.get('fields') or form.get('elements') or []
    if not items and isinstance(form.get('schema'), dict):
        items = form['schema'].get('questions') or []
    qs = []
    for it in items:
        if isinstance(it, str):
            qs.append({'type': 'short_text', 'title': it})
            continue
        if not isinstance(it, dict):
            continue
        t = it.get('type') if it.get('type') in _types() else _alias(it.get('type') or it.get('kind') or 'text')
        if not t:
            warnings.append(f'نوع السؤال «{it.get("type")}» غير معروف، فحُوِّل إلى نص قصير.')
            t = 'short_text'
        q = dict(it)
        q['type'] = t
        q['title'] = it.get('title') or it.get('question') or it.get('text') or it.get('label') or it.get('name') or ''
        if 'help' not in q:
            q['help'] = it.get('description') or it.get('helpText') or it.get('hint') or ''
        ch = it.get('choices') or it.get('options') or it.get('answers')
        if ch:
            q['choices'] = [c if isinstance(c, dict) else {'label': str(c)} for c in ch]
            corr = [c.get('id') or c.get('label') for c in q['choices'] if isinstance(c, dict) and c.get('correct')]
            if corr and not q.get('quiz'):
                q['_correct_labels'] = corr
        if it.get('columns') and not it.get('cols'):
            q['cols'] = it['columns']
        if q.get('rows'):
            q['rows'] = [r if isinstance(r, dict) else {'label': str(r)} for r in q['rows']]
        if q.get('cols'):
            q['cols'] = [c if isinstance(c, dict) else {'label': str(c)} for c in q['cols']]
        qs.append(q)
    schema = normalize_schema({'questions': qs})
    _apply_correct_labels(schema, qs)
    return {'title': form.get('title') or '', 'title_en': form.get('title_en') or '',
            'description': form.get('description') or '', 'questions': schema['questions'],
            'settings': form.get('settings') if isinstance(form.get('settings'), dict) else None,
            'format': 'json', 'warnings': warnings}


def _types():
    from schema import TYPES
    return TYPES


def _apply_correct_labels(schema, raw_qs):
    """خيار عليه correct: true في JSON أو ✓ في النص ← الإجابة الصحيحة بمعرّف الخيار."""
    for q, raw in zip(schema['questions'], raw_qs):
        labels = raw.get('_correct_labels')
        if not labels:
            continue
        ids = [c['id'] for c in q.get('choices') or [] if c['label'] in labels or c['id'] in labels]
        if q['type'] in ('short_text', 'number'):
            ids = labels
        if ids:
            q['quiz'] = {'points': raw.get('_points') or (q.get('quiz') or {}).get('points') or 1, 'correct': ids}


# ── النص ─────────────────────────────────────────────────────────────────────

_BULLET = re.compile(r'^\s*(?:[-*•▪◦–]\s+|\[\s?[xX✓]?\s?\]\s*|\(\s?[xX✓]?\s?\)\s*|[a-hA-H][).]\s+|[أابتثجحخدهوز][)\-]\s+|\d+[)]\s+(?=\D))')
_QNUM = re.compile(r'^\s*(?:\d+\s*[.\-)]|[سQq]\s*\d*\s*[:.\-])\s*')
_HINT = re.compile(r'\[([^\[\]]{1,40})\]|\(([^()]{1,30})\)\s*$')
_RANGE = re.compile(r'^(\d+)\s*[-–إلى to]+\s*(\d+)$')
_POINTS = re.compile(r'^(\d+(?:\.\d+)?)\s*(?:درجة|درجات|نقطة|نقاط|علامة|علامات|points?|pts?|marks?)$', re.I)
_CORRECT = re.compile(r'\s*(?:✓|✔|\(صحيح\)|\(صح\)|\(correct\))\s*$', re.I)


def _hint_type(hints, q):
    for h in hints:
        hl = h.strip().lower()
        m = _RANGE.match(hl.replace('مقياس', '').replace('scale', '').strip())
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            q.setdefault('type', 'scale')
            q['min'], q['max'] = lo, hi
            continue
        m = _POINTS.match(hl)
        if m:
            q['_points'] = float(m.group(1))
            continue
        t = _alias(hl)
        if t:
            q['type'] = t
            continue
        q.setdefault('_unknown', []).append(h)
    return q


def _guess_type(title):
    tl = title.lower()
    if re.search(r'البريد|e-?mail', tl):
        return 'email'
    if re.search(r'هاتف|جوال|موبايل|phone|mobile', tl):
        return 'phone'
    if re.search(r'تاريخ الميلاد|^تاريخ|date of|\bdate\b', tl):
        return 'date'
    if re.search(r'اشرح|صف |ملاحظات|اقتراح|تعليق|comments?|describe|explain|suggest', tl):
        return 'long_text'
    if re.search(r'كم عدد|how many|العمر|age\b', tl):
        return 'number'
    return 'short_text'


def _from_text(text):
    title, desc, qs, warnings = '', [], [], []
    cur = None

    def finish():
        nonlocal cur
        if cur is None:
            return
        if not cur.get('type'):
            if cur.get('cols'):
                cur['type'] = 'matrix'
            elif cur.get('choices'):
                cur['type'] = 'multi' if cur.pop('_checkbox', False) else 'single'
            else:
                cur['type'] = _guess_type(cur['title'])
        if cur['type'] in ('matrix', 'matrix_multi', 'likert'):
            cur['rows'] = [{'label': c['label']} for c in cur.pop('choices', [])]
            if cur['type'] == 'likert' and not cur.get('cols'):
                cur['cols'] = [{'label': x} for x in LIKERT_AR]
        if cur.get('_unknown'):
            warnings.append(f'لم يُفهم التلميح {"، ".join(cur["_unknown"])} في السؤال «{cur["title"][:40]}».')
        qs.append(cur)
        cur = None

    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        if s.startswith('## ') or s in ('---', '***', '___'):
            finish()
            qs.append({'type': 'section', 'title': s[3:].strip() if s.startswith('## ') else ''})
            continue
        if s.startswith('# ') and not title:
            finish()
            title = s[2:].strip()
            continue
        if s.startswith('>'):
            if cur is None and not qs:
                desc.append(s[1:].strip())
            elif cur is not None:
                cur['help'] = ((cur.get('help') or '') + '\n' + s[1:].strip()).strip()
            elif qs and qs[-1]['type'] == 'section':
                qs[-1]['help'] = ((qs[-1].get('help') or '') + '\n' + s[1:].strip()).strip()
            continue
        if s.startswith('|') and cur is not None:
            cur['cols'] = [{'label': c.strip()} for c in s.strip('|').split('|') if c.strip()]
            continue
        m = re.match(r'^(?:أعمدة|الأعمدة|columns?)\s*[:：]\s*(.+)$', s, re.I)
        if m and cur is not None:
            cur['cols'] = [{'label': c.strip()} for c in re.split(r'[،,;|]', m.group(1)) if c.strip()]
            continue
        bm = _BULLET.match(line) if cur is not None else None
        if bm:
            label = line[bm.end():].strip()
            correct = bool(_CORRECT.search(label)) or bool(re.match(r'^\s*[\[(]\s?[xX✓]\s?[\])]', line))
            label = _CORRECT.sub('', label).strip()
            if re.match(r'^\s*\[', line):
                cur['_checkbox'] = True
            if label.lower() in ('أخرى', 'غير ذلك', 'other', 'other:', 'أخرى:'):
                cur['other'] = True
                continue
            cur.setdefault('choices', []).append({'label': label})
            if correct:
                cur.setdefault('_correct_labels', []).append(label)
            continue
        # سطر سؤال جديد
        finish()
        body = _QNUM.sub('', s)
        hints = []
        while True:
            hm = _HINT.search(body)
            if not hm:
                break
            hints.append(hm.group(1) or hm.group(2))
            body = (body[:hm.start()] + body[hm.end():]).strip()
            if hm.group(2) and not (_POINTS.match(hm.group(2).strip()) or _alias(hm.group(2))):
                body = (body + ' (' + hm.group(2) + ')').strip()   # قوسان عاديان في نص السؤال
                hints.pop()
                break
        required = body.endswith('*')
        body = body.rstrip('*').strip()
        cur = _hint_type(hints, {'title': body, 'required': required})
        if cur.get('type') and cur['type'] not in _types():
            cur.pop('type')
    finish()
    raw_qs = list(qs)
    schema = normalize_schema({'questions': qs})
    _apply_correct_labels(schema, raw_qs)
    for q, raw in zip(schema['questions'], raw_qs):
        if raw.get('_points') and not q.get('quiz'):
            q['quiz'] = {'points': raw['_points'], 'correct': []}
    return {'title': title, 'description': '\n'.join(desc), 'questions': schema['questions'],
            'format': 'text', 'warnings': warnings}


# ── Google Apps Script ───────────────────────────────────────────────────────

_STR = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")
SCRIPT_TYPES = {'Text': 'short_text', 'ParagraphText': 'long_text', 'MultipleChoice': 'single', 'Checkbox': 'multi',
                'List': 'dropdown', 'Scale': 'scale', 'Rating': 'rating', 'Grid': 'matrix', 'CheckboxGrid': 'matrix_multi',
                'Date': 'date', 'Time': 'time', 'DateTime': 'datetime', 'Duration': 'time', 'PageBreak': 'section',
                'SectionHeader': 'statement', 'Image': 'statement', 'Video': 'statement'}


def _strings(s):
    out = []
    for m in _STR.finditer(s):
        v = next(g for g in m.groups() if g is not None)
        out.append(re.sub(r'\\(.)', lambda e: {'n': '\n', 't': '\t'}.get(e.group(1), e.group(1)), v))
    return out


def _args(call, stmt):
    """نص الوسائط داخل .call( … ) مع مراعاة الأقواس المتداخلة."""
    i = stmt.find('.' + call + '(')
    if i < 0:
        return None
    j = i + len(call) + 2
    depth, k = 1, j
    while k < len(stmt) and depth:
        ch = stmt[k]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch in '\'"`':
            m = _STR.match(stmt, k)
            if m:
                k = m.end()
                continue
        k += 1
    return stmt[j:k - 1]


def _split_statements(text):
    out, buf, k = [], [], 0
    while k < len(text):
        ch = text[k]
        if ch in '\'"`':
            m = _STR.match(text, k)
            if m:
                buf.append(m.group(0))
                k = m.end()
                continue
        if ch == '/' and text[k:k + 2] == '//':
            nl = text.find('\n', k)
            k = len(text) if nl < 0 else nl
            continue
        if ch in ';\n' and buf and ''.join(buf).strip() and _balanced(''.join(buf)):
            out.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        k += 1
    if ''.join(buf).strip():
        out.append(''.join(buf).strip())
    return out


def _balanced(s):
    s = _STR.sub('', s)
    return s.count('(') == s.count(')') and s.count('[') == s.count(']')


def _from_script(text):
    title, desc, qs, warnings = '', '', [], []
    by_var, last = {}, None
    for stmt in _split_statements(text):
        m = re.search(r'FormApp\.create\(\s*', stmt)
        if m:
            a = _args('create', stmt)
            title = (_strings(a or '') or [title])[0]
        am = re.search(r'\.add(\w+?)Item\s*\(', stmt)
        if am:
            kind = am.group(1)
            t = SCRIPT_TYPES.get(kind)
            if not t:
                warnings.append('في السكربت نوع سؤال غير مدعوم، فحُوِّل إلى نص قصير.')
                t = 'short_text'
            last = {'type': t, 'title': ''}
            qs.append(last)
            vm = re.match(r'^\s*(?:var|let|const)?\s*([A-Za-z_$][\w$]*)\s*=', stmt)
            if vm:
                by_var[vm.group(1)] = last
            target = last
        else:
            vm = re.match(r'^\s*([A-Za-z_$][\w$]*)\s*\.', stmt)
            target = by_var.get(vm.group(1)) if vm else None
            if target is None:
                if '.setDescription(' in stmt and not re.search(r'\.add\w+Item', stmt):
                    desc = (_strings(_args('setDescription', stmt) or '') or [desc])[0]
                elif '.setTitle(' in stmt and vm and vm.group(1) not in by_var:
                    title = (_strings(_args('setTitle', stmt) or '') or [title])[0]
                continue
        _apply_setters(target, stmt)
    raw_qs = list(qs)
    schema = normalize_schema({'questions': qs})
    _apply_correct_labels(schema, raw_qs)
    return {'title': title, 'description': desc, 'questions': schema['questions'], 'format': 'script', 'warnings': warnings}


def _apply_setters(q, stmt):
    a = _args('setTitle', stmt)
    if a is not None:
        q['title'] = (_strings(a) or [''])[0]
    a = _args('setHelpText', stmt)
    if a is not None:
        q['help'] = (_strings(a) or [''])[0]
    a = _args('setRequired', stmt)
    if a is not None:
        q['required'] = 'true' in a
    for name in ('setChoiceValues', 'setChoices'):
        a = _args(name, stmt)
        if a is not None:
            if name == 'setChoices':
                q['choices'] = []
                for cm in re.finditer(r'createChoice\(\s*(' + _STR.pattern + r')\s*(?:,\s*(true|false))?', a):
                    label = _strings(cm.group(1))[0]
                    q['choices'].append({'label': label})
                    if cm.group(5) == 'true':
                        q.setdefault('_correct_labels', []).append(label)
            else:
                q['choices'] = [{'label': s} for s in _strings(a)]
    a = _args('setRows', stmt)
    if a is not None:
        q['rows'] = [{'label': s} for s in _strings(a)]
    a = _args('setColumns', stmt)
    if a is not None:
        q['cols'] = [{'label': s} for s in _strings(a)]
    a = _args('setBounds', stmt)
    if a is not None:
        nums = re.findall(r'-?\d+', a)
        if len(nums) >= 2:
            q['min'], q['max'] = int(nums[0]), int(nums[1])
    a = _args('setLabels', stmt)
    if a is not None:
        ss = _strings(a)
        if ss:
            q['min_label'] = ss[0]
        if len(ss) > 1:
            q['max_label'] = ss[1]
    a = _args('setRatingScaleLevel', stmt)
    if a is not None and re.search(r'\d+', a):
        q['max'] = int(re.search(r'\d+', a).group())
    a = _args('setPoints', stmt)
    if a is not None and re.search(r'\d+', a):
        q['_points'] = float(re.search(r'\d+(?:\.\d+)?', a).group())
        q['quiz'] = {'points': q['_points'], 'correct': []}
    if re.search(r'\.showOtherOption\(\s*true', stmt):
        q['other'] = True
