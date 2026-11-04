"""محرّك النموذج والاستيراد من نص ملصوق — بلا خادم."""
from importer import parse
from schema import grade, normalize_schema, validate, walk

QS = normalize_schema({'questions': [
    {'id': 'q1', 'type': 'yesno', 'title': 'تشارك؟', 'required': True},
    {'id': 's1', 'type': 'section', 'title': 'الأنشطة'},
    {'id': 'q2', 'type': 'multi', 'title': 'ما الأنشطة؟', 'required': True, 'choices': [{'id': 'a', 'label': 'رياضة'}, {'id': 'b', 'label': 'فنون'}]},
    {'id': 'q3', 'type': 'short_text', 'title': 'أي رياضة؟', 'required': True,
     'logic': {'show_if': {'mode': 'all', 'rules': [{'q': 'q2', 'op': 'contains', 'value': 'a'}]}}},
    {'id': 's2', 'type': 'section', 'title': 'الأسباب'},
    {'id': 'q4', 'type': 'long_text', 'title': 'لماذا لا؟', 'required': True},
]})['questions']
QS[0]['choices'][0]['goto'] = 's1'
QS[0]['choices'][1]['goto'] = 's2'
QS[1]['next'] = '__submit__'


def test_branching_and_display_logic():
    visited, shown, _ = walk(QS, {'q1': 'no'})
    assert [q['id'] for q in shown] == ['q1', 'q4']
    visited, shown, _ = walk(QS, {'q1': 'yes', 'q2': ['b']})
    assert [q['id'] for q in shown] == ['q1', 'q2']          # q3 مخفي، والقسم الثاني يُتخطّى بالإرسال
    _, shown, _ = walk(QS, {'q1': 'yes', 'q2': ['a', 'b']})
    assert 'q3' in [q['id'] for q in shown] and 'q4' not in [q['id'] for q in shown]


def test_validation_drops_hidden_answers_and_requires_visible():
    clean, errors, _ = validate(QS, {'q1': 'yes', 'q2': ['a'], 'q4': 'لا يُحفظ'})
    assert errors == {'q3': ('هذا السؤال مطلوب.', 'This question is required.')}
    clean, errors, _ = validate(QS, {'q1': 'yes', 'q2': ['a'], 'q3': 'كرة القدم', 'q4': 'لا يُحفظ'})
    assert not errors and 'q4' not in clean and clean['q3'] == 'كرة القدم'
    clean, errors, _ = validate(QS, {'q1': 'maybe'})
    assert 'q1' in errors


def test_answer_types_are_checked():
    qs = normalize_schema({'questions': [
        {'id': 'e', 'type': 'email', 'title': 'بريد'},
        {'id': 'n', 'type': 'nps', 'title': 'NPS'},
        {'id': 'm', 'type': 'likert', 'title': 'ليكرت', 'required': True, 'rows': [{'id': 'r1', 'label': 'أ'}, {'id': 'r2', 'label': 'ب'}]},
        {'id': 'c', 'type': 'constant_sum', 'title': 'توزيع', 'total': 10, 'choices': [{'id': 'x', 'label': 'x'}, {'id': 'y', 'label': 'y'}]},
        {'id': 'd', 'type': 'date', 'title': 'تاريخ'},
        {'id': 'r', 'type': 'ranking', 'title': 'ترتيب', 'choices': [{'id': 'x', 'label': 'x'}, {'id': 'y', 'label': 'y'}]},
    ]})['questions']
    cols = [c['id'] for c in qs[2]['cols']]
    assert len(cols) == 5                       # ليكرت بخمسة أعمدة افتراضياً
    _, errors, _ = validate(qs, {'e': 'not-mail', 'n': 11, 'm': {'r1': cols[0]}, 'c': {'x': 3, 'y': 3}, 'd': '31/12/2026', 'r': ['x']})
    assert set(errors) == {'e', 'n', 'm', 'c', 'd', 'r'}
    clean, errors, _ = validate(qs, {'e': 'a@b.jo', 'n': 9, 'm': {'r1': cols[0], 'r2': cols[4]}, 'c': {'x': 4, 'y': 6}, 'd': '2026-12-31', 'r': ['y', 'x']})
    assert not errors and clean['n'] == 9 and clean['r'] == ['y', 'x']


def test_quiz_grading_auto_partial_and_manual():
    qs = normalize_schema({'questions': [
        {'id': 'a', 'type': 'single', 'title': '1', 'choices': [{'id': 'x', 'label': 'x'}, {'id': 'y', 'label': 'y'}], 'quiz': {'points': 2, 'correct': ['y']}},
        {'id': 'b', 'type': 'multi', 'title': '2', 'choices': [{'id': 'x', 'label': 'x'}, {'id': 'y', 'label': 'y'}, {'id': 'z', 'label': 'z'}], 'quiz': {'points': 4, 'correct': ['x', 'y'], 'partial': True}},
        {'id': 'c', 'type': 'short_text', 'title': '3', 'quiz': {'points': 1, 'correct': ['عمّان', 'Amman']}},
        {'id': 'd', 'type': 'long_text', 'title': '4', 'quiz': {'points': 3}},
    ]})['questions']
    score, total, detail = grade(qs, {'a': 'y', 'b': ['x'], 'c': ' عمان ', 'd': 'نص'})
    assert (score, total) == (5.0, 10.0)          # 2 + 2 (جزئي) + 1 + 0 (يدوي)
    assert detail['d'][2] is None
    score, _, _ = grade(qs, {'a': 'y', 'b': ['x'], 'c': 'عمان', 'd': 'نص'}, {'d': 2.5})
    assert score == 7.5


def test_import_text_with_types_sections_and_correct_answers():
    p = parse('''# عنوان الاختبار
> وصف قصير
1. ما اسمك؟ *
2. ما صفك؟ [قائمة]
- السابع
- الثامن
## القسم الثاني
3. عاصمة الأردن؟ [2 درجات]
- إربد
- عمّان ✓
4. قيّم الخدمات [شبكة]
| ممتاز | جيد |
- الإعارة
- الهدوء
5. رضاك [1-10]
6. اقتراحاتك [فقرة]
7. اختر ما ينطبق
[ ] أ
[ ] ب
''')
    assert p['title'] == 'عنوان الاختبار' and p['description'] == 'وصف قصير'
    types = [q['type'] for q in p['questions']]
    assert types == ['short_text', 'dropdown', 'section', 'single', 'matrix', 'scale', 'long_text', 'multi']
    assert p['questions'][0]['required'] is True
    q3 = p['questions'][3]
    assert q3['quiz']['points'] == 2 and q3['quiz']['correct'] == [q3['choices'][1]['id']]
    assert [c['label'] for c in p['questions'][4]['cols']] == ['ممتاز', 'جيد'] and len(p['questions'][4]['rows']) == 2
    assert p['questions'][5]['max'] == 10


def test_import_json_and_apps_script():
    p = parse('{"title": "T", "questions": [{"type": "MULTIPLE_CHOICE", "title": "A", "choices": ["x", {"label": "y", "correct": true}]}, {"type": "PARAGRAPH_TEXT", "title": "B"}, "C"]}')
    assert p['format'] == 'json' and [q['type'] for q in p['questions']] == ['single', 'long_text', 'short_text']
    assert p['questions'][0]['quiz']['correct'] == [p['questions'][0]['choices'][1]['id']]
    s = parse('''function f() {
  var form = FormApp.create('اختبار');
  form.addMultipleChoiceItem().setTitle('ما عاصمة الأردن؟').setChoiceValues(['عمّان', 'إربد']).setRequired(true);
  var item = form.addCheckboxItem();
  item.setTitle("أي هذه بحار؟");
  item.setChoices([item.createChoice('الأحمر', true), item.createChoice('الميت', false)]);
  form.addScaleItem().setTitle('الصعوبة').setBounds(1, 5).setLabels('سهل', 'صعب');
  form.addGridItem().setTitle('قيّم').setRows(['أ', 'ب']).setColumns(['جيد', 'ضعيف']);
  form.addPageBreakItem().setTitle('الجزء الثاني');
}''')
    assert s['format'] == 'script' and s['title'] == 'اختبار'
    assert [q['type'] for q in s['questions']] == ['single', 'multi', 'scale', 'matrix', 'section']
    assert s['questions'][0]['required'] and [c['label'] for c in s['questions'][0]['choices']] == ['عمّان', 'إربد']
    assert s['questions'][1]['title'] == 'أي هذه بحار؟' and s['questions'][1]['quiz']['correct'] == [s['questions'][1]['choices'][0]['id']]
    assert s['questions'][2]['min_label'] == 'سهل' and s['questions'][2]['max'] == 5
    assert len(s['questions'][3]['rows']) == 2
