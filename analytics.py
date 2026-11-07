"""التحليل والإحصاءات: لكل سؤال، والجداول المتقاطعة، وملخص الإجابات، والمقارنة بين النماذج، ولوحة الإحصاءات العامة."""
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from schema import (CHOICE_TYPES, MATRIX_TYPES, NO_ANSWER, OTHER, TEXT_TYPES, is_empty, norm_text,
                    qtitle, walk)
from uaparse import DEVICE_LABELS


def _lab(o, lang):
    return (o.get('label_en') or o['label']) if lang == 'en' else o['label']


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


STOP = set('في من على إلى عن مع هذا هذه ذلك التي الذي أن إن كان كانت لا ما هو هي و أو ثم قد كل بعض جدا جداً '
           'the a an and or of to in on for is are was were it this that with be as at by not no yes very'.split())


def top_words(texts, n=20):
    c = Counter()
    for t in texts:
        for w in re.findall(r'[\w؀-ۿ]{3,}', norm_text(t)):
            if w not in STOP and not w.isdigit():
                c[w] += 1
    return [{'word': w, 'n': k} for w, k in c.most_common(n)]


def answerable(form):
    return [q for q in form.questions if q['type'] not in NO_ANSWER]


def question_stats(form, responses, lang='ar'):
    """قائمة إحصاءات لكل سؤال قابل للإجابة. responses: قائمة كائنات Response."""
    qs = answerable(form)
    out = []
    quiz = bool(form.s('quiz'))
    shown_count = Counter()
    for r in responses:
        _, shown, _ = walk(form.questions, r.answers or {})
        for q in shown:
            shown_count[q['id']] += 1
    for q in qs:
        vals = [(r, (r.answers or {}).get(q['id'])) for r in responses]
        vals = [(r, v) for r, v in vals if not is_empty(v)]
        st = {'q': q, 'id': q['id'], 'type': q['type'], 'title': qtitle(q, lang), 'n': len(vals),
              'shown': shown_count[q['id']], 'total': len(responses),
              'skipped': max(0, shown_count[q['id']] - len(vals))}
        t = q['type']
        if t in CHOICE_TYPES:
            c = Counter()
            others = []
            for r, v in vals:
                for x in (v if isinstance(v, list) else [v]):
                    c[x] += 1
                if (v == OTHER or (isinstance(v, list) and OTHER in v)) and (r.answers or {}).get(q['id'] + ':other'):
                    others.append(r.answers[q['id'] + ':other'])
            items = [{'id': o['id'], 'label': _lab(o, lang), 'n': c[o['id']], 'pct': _pct(c[o['id']], len(vals))}
                     for o in q.get('choices') or []]
            if q.get('other'):
                items.append({'id': OTHER, 'label': 'أخرى' if lang != 'en' else 'Other', 'n': c[OTHER], 'pct': _pct(c[OTHER], len(vals))})
            st.update(kind='choice', items=items, others=others[-100:], multi=(t == 'multi'))
            if items:
                top = max(items, key=lambda i: i['n'])
                st['top'] = top if top['n'] else None
        elif t in ('number', 'scale', 'rating', 'nps', 'slider'):
            nums = [float(v) for _, v in vals if isinstance(v, (int, float))]
            st['kind'] = 'numeric'
            if nums:
                st.update(mean=round(statistics.fmean(nums), 2), median=statistics.median(nums), min=min(nums),
                          max=max(nums), sd=round(statistics.pstdev(nums), 2) if len(nums) > 1 else 0)
            dist = Counter(nums)
            if t in ('scale', 'rating', 'nps'):
                lo = q.get('min', 1 if t == 'rating' else 0)
                hi = q.get('max', 5)
                keys = list(range(int(lo if t != 'rating' else 1), int(hi) + 1))
            else:
                keys = sorted(dist)[:60]
            st['dist'] = [{'label': f'{k:g}' if isinstance(k, float) else str(k), 'n': dist[float(k)], 'pct': _pct(dist[float(k)], len(nums))} for k in keys]
            if t == 'nps' and nums:
                p = sum(1 for x in nums if x >= 9)
                d = sum(1 for x in nums if x <= 6)
                st['nps'] = {'promoters': _pct(p, len(nums)), 'passives': _pct(len(nums) - p - d, len(nums)),
                             'detractors': _pct(d, len(nums)), 'score': round(_pct(p, len(nums)) - _pct(d, len(nums)), 1)}
            if t in ('scale', 'rating') and nums:
                hi = q.get('max', 5)
                st['satisfaction'] = _pct(sum(1 for x in nums if x >= hi - (1 if hi <= 5 else 2)), len(nums))   # top-2-box
        elif t in MATRIX_TYPES:
            cols = q.get('cols') or []
            rows = []
            for row in q.get('rows') or []:
                c = Counter()
                answered = 0
                for _, v in vals:
                    x = v.get(row['id']) if isinstance(v, dict) else None
                    if is_empty(x):
                        continue
                    answered += 1
                    for y in (x if isinstance(x, list) else [x]):
                        c[y] += 1
                idx = {col['id']: i + 1 for i, col in enumerate(cols)}
                score_vals = [idx[y] for _, v in vals if isinstance(v, dict) and isinstance(v.get(row['id']), str)
                              for y in [v.get(row['id'])] if y in idx]
                rows.append({'label': _lab(row, lang), 'n': answered,
                             'counts': [c[col['id']] for col in cols],
                             'pcts': [_pct(c[col['id']], answered) for col in cols],
                             'mean': round(statistics.fmean(score_vals), 2) if score_vals and t != 'matrix_multi' else None})
            st.update(kind='matrix', cols=[_lab(c, lang) for c in cols], rows=rows)
        elif t == 'ranking':
            ranks = defaultdict(list)
            first = Counter()
            for _, v in vals:
                for i, x in enumerate(v):
                    ranks[x].append(i + 1)
                if v:
                    first[v[0]] += 1
            items = [{'label': _lab(o, lang), 'avg': round(statistics.fmean(ranks[o['id']]), 2) if ranks[o['id']] else None,
                      'first': first[o['id']]} for o in q.get('choices') or []]
            items.sort(key=lambda i: i['avg'] if i['avg'] is not None else 1e9)
            st.update(kind='ranking', items=items)
        elif t == 'constant_sum':
            sums = defaultdict(list)
            for _, v in vals:
                for o in q.get('choices') or []:
                    sums[o['id']].append(float(v.get(o['id'], 0)))
            st.update(kind='sum', items=[{'label': _lab(o, lang), 'avg': round(statistics.fmean(sums[o['id']]), 2) if sums[o['id']] else 0}
                                         for o in q.get('choices') or []])
        elif t in ('date', 'time', 'datetime'):
            c = Counter(str(v)[:10] if t != 'time' else str(v)[:2] + ':00' for _, v in vals)
            st.update(kind='dates', items=[{'label': k, 'n': n} for k, n in sorted(c.items())][:60])
        elif t in ('file', 'signature'):
            files = [(r, f) for r, v in vals for f in (v if isinstance(v, list) else []) if isinstance(f, dict)]
            st.update(kind='files', files=files[-60:], count=len(files))
        else:   # النصوص والحقول المخفية
            texts = [str(v) for _, v in vals]
            c = Counter(norm_text(x) for x in texts)
            st.update(kind='text', samples=[(r, str(v)) for r, v in vals][-60:][::-1], words=top_words(texts),
                      repeated=[{'text': next(x for x in texts if norm_text(x) == k), 'n': n} for k, n in c.most_common(8) if n > 1])
        if quiz and (q.get('quiz') or {}).get('correct'):
            from schema import grade_question
            ok = sum(1 for _, v in vals if grade_question(q, v)[2])
            st['correct_pct'] = _pct(ok, st['shown'] or len(vals))
            st['correct_n'] = ok
        out.append(st)
    return out


# ── الجداول المتقاطعة ────────────────────────────────────────────────────────

def categories(q, lang='ar'):
    """[(مفتاح، عنوان)] لسؤال يصلح للتقاطع، أو None."""
    t = q['type']
    if t in CHOICE_TYPES:
        cats = [(o['id'], _lab(o, lang)) for o in q.get('choices') or []]
        if q.get('other'):
            cats.append((OTHER, 'أخرى' if lang != 'en' else 'Other'))
        return cats
    if t in ('scale', 'rating', 'nps'):
        lo = 1 if t == 'rating' else q.get('min', 0)
        return [(str(k), str(k)) for k in range(int(lo), int(q.get('max', 5)) + 1)]
    if t in ('number', 'slider', 'short_text', 'hidden', 'date'):
        return []          # تُستخرج من القيم نفسها
    return None


def keys_of(q, value):
    if is_empty(value):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, float) and value == int(value):
        value = int(value)
    if q['type'] in ('short_text', 'hidden'):
        return [norm_text(value)]
    return [str(value)]


def crossable(form):
    return [q for q in answerable(form) if categories(q) is not None]


def crosstab(form, responses, qa_id, qb_id, lang='ar'):
    qmap = {q['id']: q for q in form.questions}
    qa, qb = qmap.get(qa_id), qmap.get(qb_id)
    if not qa or not qb:
        return None

    def cats(q):
        c = categories(q, lang)
        if c:
            return c
        seen = {}
        for r in responses:
            for k in keys_of(q, (r.answers or {}).get(q['id'])):
                seen.setdefault(k, str((r.answers or {}).get(q['id'])))
        return sorted(seen.items(), key=lambda kv: (len(kv[0]), kv[0]))[:40]
    ca, cb = cats(qa), cats(qb)
    ia = {k: i for i, (k, _) in enumerate(ca)}
    ib = {k: i for i, (k, _) in enumerate(cb)}
    m = [[0] * len(cb) for _ in ca]
    for r in responses:
        a = keys_of(qa, (r.answers or {}).get(qa_id))
        b = keys_of(qb, (r.answers or {}).get(qb_id))
        for x in a:
            for y in b:
                if x in ia and y in ib:
                    m[ia[x]][ib[y]] += 1
    rows = []
    for (k, label), counts in zip(ca, m):
        tot = sum(counts)
        rows.append({'label': label, 'counts': counts, 'total': tot, 'pcts': [_pct(c, tot) for c in counts]})
    col_tot = [sum(m[i][j] for i in range(len(ca))) for j in range(len(cb))]
    grand = sum(col_tot)
    # كاي تربيع لاستقلال السؤالين (اختبار تقريبي يُعرض للإرشاد فقط)
    chi = None
    if grand and len(ca) > 1 and len(cb) > 1:
        x2 = 0.0
        for i in range(len(ca)):
            for j in range(len(cb)):
                e = rows[i]['total'] * col_tot[j] / grand
                if e:
                    x2 += (m[i][j] - e) ** 2 / e
        dof = (len([r for r in rows if r['total']]) - 1) * (len([c for c in col_tot if c]) - 1)
        if dof > 0:
            chi = {'x2': round(x2, 2), 'dof': dof, 'p': round(_chi_p(x2, dof), 4)}
    return {'qa': qa, 'qb': qb, 'a_title': qtitle(qa, lang), 'b_title': qtitle(qb, lang),
            'cols': [lab for _, lab in cb], 'rows': rows, 'col_totals': col_tot, 'grand': grand, 'chi': chi}


def _chi_p(x2, k):
    """القيمة الاحتمالية لتوزيع كاي تربيع (تكامل غاما المنتظم الأعلى)."""
    import math
    if x2 <= 0:
        return 1.0
    a, x = k / 2.0, x2 / 2.0
    if x < a + 1:      # متسلسلة
        s = term = 1.0 / a
        n = a
        for _ in range(500):
            n += 1
            term *= x / n
            s += term
            if abs(term) < abs(s) * 1e-12:
                break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    b = x + 1 - a     # كسر مستمر
    c, d = 1 / 1e-300, 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - math.lgamma(a)) * h)


# ── ملخص الإجابات ────────────────────────────────────────────────────────────

def local_day(dt):
    from zoneinfo import ZoneInfo
    if not dt:
        return ''
    return dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Amman')).strftime('%Y-%m-%d')


def summary(responses, days=30, lang='ar'):
    n = len(responses)
    durs = [r.duration_sec for r in responses if r.duration_sec]
    scores = [r.percent for r in responses if r.percent is not None]
    dev = Counter(r.device or 'desktop' for r in responses)
    today = datetime.utcnow()
    by_day = Counter(local_day(r.submitted_at) for r in responses)
    trend = []
    for i in range(days - 1, -1, -1):
        d = local_day(today - timedelta(days=i))
        trend.append({'label': d, 'n': by_day.get(d, 0)})
    hours = Counter()
    from zoneinfo import ZoneInfo
    for r in responses:
        if r.submitted_at:
            hours[r.submitted_at.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Amman')).hour] += 1
    return {
        'n': n,
        'avg_duration': round(statistics.fmean(durs)) if durs else None,
        'median_duration': round(statistics.median(durs)) if durs else None,
        'avg_score': round(statistics.fmean(scores), 1) if scores else None,
        'pass_rate': None,
        'devices': [{'key': k, 'label': DEVICE_LABELS.get(k, (k, k))[1 if lang == 'en' else 0], 'n': v, 'pct': _pct(v, n)}
                    for k, v in dev.most_common()],
        'browsers': [{'label': k, 'title': ({'أخرى': 'Other', 'غير معروف': 'Unknown'}.get(k, k) if lang == 'en' else k), 'n': v, 'pct': _pct(v, n)}
                     for k, v in Counter(r.browser or '—' for r in responses).most_common(8)],
        'oses': [{'label': k, 'n': v, 'pct': _pct(v, n)} for k, v in Counter(r.os or '—' for r in responses).most_common(8)],
        'trend': trend,
        'hours': [{'label': f'{h:02d}', 'n': hours.get(h, 0)} for h in range(24)],
        'flagged': sum(1 for r in responses if r.flagged),
        'last': max((r.submitted_at for r in responses if r.submitted_at), default=None),
    }


# ── المقارنة بين النماذج ─────────────────────────────────────────────────────

def form_metrics(form, responses):
    n = len(responses)
    durs = [r.duration_sec for r in responses if r.duration_sec]
    scores = [r.percent for r in responses if r.percent is not None]
    first = min((r.submitted_at for r in responses), default=None)
    last = max((r.submitted_at for r in responses), default=None)
    span = max(1, ((last - first).days + 1)) if first and last else 1
    dev = Counter(r.device or 'desktop' for r in responses)
    return {'form': form, 'n': n, 'views': form.views or 0, 'starts': form.starts or 0,
            'completion': _pct(n, form.views) if form.views else None,
            'avg_duration': round(statistics.fmean(durs)) if durs else None,
            'avg_score': round(statistics.fmean(scores), 1) if scores else None,
            'per_day': round(n / span, 2) if n else 0, 'first': first, 'last': last,
            'mobile_pct': _pct(dev.get('mobile', 0) + dev.get('tablet', 0), n),
            'questions': len(answerable(form))}


def _match_key(q):
    return (q['type'] if q['type'] not in ('single', 'dropdown', 'yesno') else 'one', norm_text(q.get('title')))


def shared_questions(forms, lang='ar'):
    """الأسئلة المشتركة بين نموذجين أو أكثر: بالمعرّف نفسه (نماذج منسوخة) أو بالعنوان والنوع نفسيهما."""
    groups = defaultdict(list)
    for f in forms:
        for q in answerable(f):
            key = ('id', q['id'])
            groups[key].append((f, q))
    by_title = defaultdict(list)
    for f in forms:
        for q in answerable(f):
            by_title[_match_key(q)].append((f, q))
    out, used = [], set()
    for key, items in list(groups.items()) + list(by_title.items()):
        fids = {f.id for f, _ in items}
        if len(fids) < 2:
            continue
        sig = tuple(sorted((f.id, q['id']) for f, q in items))
        if sig in used or any(set(sig) <= set(u) for u in used):
            continue
        used.add(sig)
        # نموذج واحد = سؤال واحد (الأول)
        seen, uniq = set(), []
        for f, q in items:
            if f.id not in seen:
                seen.add(f.id)
                uniq.append((f, q))
        out.append({'title': qtitle(uniq[0][1], lang), 'type': uniq[0][1]['type'], 'items': uniq})
    return out


def compare_question(group, responses_by_form, lang='ar'):
    """توزيع سؤال مشترك في كل نموذج: الخيارات بالعنوان (لا بالمعرّف) حتى تتطابق بين النماذج."""
    labels, series = [], []
    t = group['type']
    numeric = t in ('number', 'scale', 'rating', 'nps', 'slider')
    for f, q in group['items']:
        rs = responses_by_form.get(f.id, [])
        vals = [(r.answers or {}).get(q['id']) for r in rs]
        vals = [v for v in vals if not is_empty(v)]
        row = {'form': f, 'n': len(vals)}
        if numeric:
            nums = [float(v) for v in vals if isinstance(v, (int, float))]
            row['mean'] = round(statistics.fmean(nums), 2) if nums else None
            row['median'] = statistics.median(nums) if nums else None
        elif t in CHOICE_TYPES:
            idx = {o['id']: _lab(o, lang) for o in q.get('choices') or []}
            c = Counter()
            for v in vals:
                for x in (v if isinstance(v, list) else [v]):
                    lab = idx.get(x, 'أخرى' if lang != 'en' else 'Other')
                    c[lab] += 1
                    if lab not in labels:
                        labels.append(lab)
            row['counts'] = c
        elif t in MATRIX_TYPES:
            cols = q.get('cols') or []
            pos = {col['id']: i + 1 for i, col in enumerate(cols)}
            sc = [pos[x] for v in vals if isinstance(v, dict) for x in v.values() if isinstance(x, str) and x in pos]
            row['mean'] = round(statistics.fmean(sc), 2) if sc else None
            numeric = True
        series.append(row)
    for row in series:
        if 'counts' in row:
            row['pcts'] = [_pct(row['counts'].get(lab, 0), row['n']) for lab in labels]
            row['ns'] = [row['counts'].get(lab, 0) for lab in labels]
    return {'title': group['title'], 'type': t, 'numeric': numeric, 'labels': labels, 'series': series}


def group_metrics(forms, responses_by_form, by, lang='ar'):
    """تجميع حسب معيار: category | owner | status | month | device | browser | os."""
    g = defaultdict(lambda: {'forms': set(), 'n': 0, 'durs': [], 'scores': []})
    for f in forms:
        for r in responses_by_form.get(f.id, []):
            if by == 'category':
                key = f.category or ('بلا تصنيف' if lang != 'en' else 'Uncategorized')
            elif by == 'owner':
                key = f.owner.display if f.owner else '—'
            elif by == 'status':
                key = f.status
            elif by == 'month':
                key = local_day(r.submitted_at)[:7]
            elif by == 'device':
                key = DEVICE_LABELS.get(r.device or 'desktop', (r.device, r.device))[1 if lang == 'en' else 0]
            elif by == 'browser':
                key = r.browser or '—'
            elif by == 'os':
                key = r.os or '—'
            else:
                key = f.title_for(lang)
            row = g[key]
            row['forms'].add(f.id)
            row['n'] += 1
            if r.duration_sec:
                row['durs'].append(r.duration_sec)
            if r.percent is not None:
                row['scores'].append(r.percent)
    total = sum(v['n'] for v in g.values())
    out = [{'key': k, 'forms': len(v['forms']), 'n': v['n'], 'pct': _pct(v['n'], total),
            'avg_duration': round(statistics.fmean(v['durs'])) if v['durs'] else None,
            'avg_score': round(statistics.fmean(v['scores']), 1) if v['scores'] else None} for k, v in g.items()]
    out.sort(key=lambda x: x['key'] if by == 'month' else -x['n'])
    return out


def monthly_series(forms, responses_by_form, lang='ar'):
    months = sorted({local_day(r.submitted_at)[:7] for rs in responses_by_form.values() for r in rs if r.submitted_at})[-18:]
    series = []
    for f in forms:
        c = Counter(local_day(r.submitted_at)[:7] for r in responses_by_form.get(f.id, []))
        series.append({'label': f.title_for(lang), 'data': [c.get(m, 0) for m in months]})
    return {'labels': months, 'series': series}
