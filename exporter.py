"""تصدير الإجابات والتحليل إلى Excel وCSV (CSV بترميز UTF-8 مع BOM حتى يفتحه Excel بالعربية سليماً)."""
import csv
import io

from analytics import question_stats, summary
from schema import MATRIX_TYPES, NO_ANSWER, answer_text, qtitle


def local(dt):
    from zoneinfo import ZoneInfo
    if not dt:
        return ''
    return dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Amman')).strftime('%Y-%m-%d %H:%M')


def columns(form, lang='ar'):
    """[(عنوان العمود، دالة القيمة)] — الشبكة عمود لكل صف."""
    L = (lambda a, e: e) if lang == 'en' else (lambda a, e: a)
    cols = [(L('الرقم', 'No.'), lambda r: r.id),
            (L('وقت الإرسال', 'Submitted'), lambda r: local(r.submitted_at)),
            (L('البريد', 'Email'), lambda r: r.email or '')]
    filler_keys = [f['key'] for f in form.s('filler_fields') or []]
    for f in form.s('filler_fields') or []:
        cols.append((f.get('label') or f['key'], lambda r, k=f['key']: (r.filler or {}).get(k, '')))
    if not filler_keys:
        cols.append((L('الاسم', 'Name'), lambda r: (r.filler or {}).get('name', '')))
    for q in form.questions:
        if q['type'] in NO_ANSWER:
            continue
        if q['type'] in MATRIX_TYPES:
            for row in q.get('rows') or []:
                def cell(r, q=q, row=row):
                    v = (r.answers or {}).get(q['id']) or {}
                    x = v.get(row['id']) if isinstance(v, dict) else None
                    labels = {c['id']: ((c.get('label_en') or c['label']) if lang == 'en' else c['label']) for c in q.get('cols') or []}
                    if isinstance(x, list):
                        return '، '.join(labels.get(i, i) for i in x)
                    return labels.get(x, '') if x else ''
                cols.append((f'{qtitle(q, lang)} [{row["label"]}]', cell))
        else:
            cols.append((qtitle(q, lang), lambda r, q=q: answer_text(q, r.answers or {}, lang)))
    if form.s('quiz'):
        cols += [(L('الدرجة', 'Score'), lambda r: r.score if r.score is not None else ''),
                 (L('من', 'Out of'), lambda r: r.max_score if r.max_score is not None else ''),
                 (L('النسبة %', 'Percent'), lambda r: r.percent if r.percent is not None else '')]
    cols += [(L('المدة (ثانية)', 'Duration (s)'), lambda r: r.duration_sec or ''),
             (L('الجهاز', 'Device'), lambda r: r.device or ''),
             (L('المتصفح', 'Browser'), lambda r: r.browser or ''),
             (L('النظام', 'OS'), lambda r: r.os or ''),
             (L('عنوان IP', 'IP address'), lambda r: r.ip or ''),
             (L('اللغة', 'Language'), lambda r: r.lang or ''),
             (L('الشاشة', 'Screen'), lambda r: (r.meta or {}).get('screen', '')),
             (L('المنطقة الزمنية', 'Time zone'), lambda r: (r.meta or {}).get('tz', '')),
             (L('تكرار محتمل', 'Possible duplicate'), lambda r: L('نعم', 'Yes') if r.flagged else ''),
             (L('رقم الإجابة الأم', 'Parent response'), lambda r: r.parent_response_id or '')]
    return cols


def to_csv(form, responses, lang='ar'):
    cols = columns(form, lang)
    buf = io.StringIO()
    buf.write('﻿')
    w = csv.writer(buf)
    w.writerow([c[0] for c in cols])
    for r in responses:
        w.writerow([c[1](r) for c in cols])
    return buf.getvalue().encode('utf-8')


def to_xlsx(form, responses, lang='ar'):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    L = (lambda a, e: e) if lang == 'en' else (lambda a, e: a)
    wb = Workbook()
    ws = wb.active
    ws.title = L('الإجابات', 'Responses')
    ws.sheet_view.rightToLeft = lang != 'en'
    cols = columns(form, lang)
    ws.append([c[0] for c in cols])
    head = PatternFill('solid', fgColor='0C67EC')
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = head
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    for r in responses:
        ws.append([c[1](r) for c in cols])
    for i, (title, _) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, min(45, len(str(title)) + 4))
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = ws.dimensions

    s = wb.create_sheet(L('التحليل', 'Analysis'))
    s.sheet_view.rightToLeft = lang != 'en'
    sm = summary(responses, lang=lang)
    s.append([form.title_for(lang)])
    s['A1'].font = Font(bold=True, size=14)
    s.append([L('عدد الإجابات', 'Responses'), sm['n']])
    s.append([L('متوسط المدة (ثانية)', 'Average duration (s)'), sm['avg_duration'] or ''])
    if sm['avg_score'] is not None:
        s.append([L('متوسط الدرجة %', 'Average score %'), sm['avg_score']])
    s.append([])
    for st in question_stats(form, responses, lang):
        s.append([st['title']])
        s.cell(s.max_row, 1).font = Font(bold=True, color='0C67EC')
        s.append([L('أجاب', 'Answered'), st['n'], L('تخطّى', 'Skipped'), st['skipped']])
        if st.get('kind') == 'choice':
            s.append([L('الخيار', 'Option'), L('العدد', 'Count'), '%'])
            for it in st['items']:
                s.append([it['label'], it['n'], it['pct']])
        elif st.get('kind') == 'numeric':
            s.append([L('المتوسط', 'Mean'), st.get('mean', ''), L('الوسيط', 'Median'), st.get('median', ''),
                      L('الانحراف المعياري', 'Std. dev.'), st.get('sd', '')])
            if st.get('nps'):
                s.append(['NPS', st['nps']['score'], L('المروّجون %', 'Promoters %'), st['nps']['promoters'],
                          L('المنتقدون %', 'Detractors %'), st['nps']['detractors']])
            for it in st.get('dist') or []:
                s.append([it['label'], it['n'], it['pct']])
        elif st.get('kind') == 'matrix':
            s.append([''] + st['cols'] + [L('المتوسط', 'Mean')])
            for row in st['rows']:
                s.append([row['label']] + row['counts'] + [row['mean'] if row['mean'] is not None else ''])
        elif st.get('kind') in ('ranking', 'sum'):
            for it in st['items']:
                s.append([it['label'], it.get('avg')])
        elif st.get('kind') == 'text':
            for w in st['words'][:10]:
                s.append([w['word'], w['n']])
        if st.get('correct_pct') is not None:
            s.append([L('نسبة الإجابات الصحيحة %', 'Correct %'), st['correct_pct']])
        s.append([])
    s.column_dimensions['A'].width = 48
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def table_csv(headers, rows):
    buf = io.StringIO()
    buf.write('﻿')
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode('utf-8')
