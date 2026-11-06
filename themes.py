"""معرض الخلفيات الجاهزة: لكل خلفية لون الصفحة واللون الرئيسي المناسب لها (الأزرار وشريط العنوان).

الصور في static/themes/<المفتاح>.svg ويولّدها tools_themes.py. اختيار خلفية من المحرّر يضبط
bg_image وbg_color وaccent ويجعل التعتيم صفراً؛ ويمكن بعدها تعديل أي منها يدوياً.
"""
THEMES = {
    'classroom':   {'ar': 'الصف الدراسي',     'en': 'Classroom',     'bg': '#2b59c3', 'accent': '#1d4ed8'},
    'science':     {'ar': 'العلوم',            'en': 'Science',       'bg': '#0f766e', 'accent': '#0f766e'},
    'technology':  {'ar': 'التقنية',           'en': 'Technology',    'bg': '#4351b0', 'accent': '#4338ca'},
    'nature':      {'ar': 'الطبيعة',           'en': 'Nature',        'bg': '#65a30d', 'accent': '#3f6212'},
    'celebration': {'ar': 'الاحتفال',          'en': 'Celebration',   'bg': '#db2777', 'accent': '#be185d'},
    'arts':        {'ar': 'الفنون',            'en': 'Arts',          'bg': '#ea7a2b', 'accent': '#c2410c'},
    'sports':      {'ar': 'الرياضة',           'en': 'Sports',        'bg': '#15803d', 'accent': '#166534'},
    'graduation':  {'ar': 'التخرّج',           'en': 'Graduation',    'bg': '#1e3a8a', 'accent': '#1e3a8a'},
    'feedback':    {'ar': 'الآراء والتقييم',   'en': 'Feedback',      'bg': '#7c3aed', 'accent': '#6d28d9'},
    'heritage':    {'ar': 'الزخرفة العربية',   'en': 'Arabic pattern', 'bg': '#efe2c8', 'accent': '#92400e'},
    'calm':        {'ar': 'الهدوء',            'en': 'Calm',          'bg': '#dbeafe', 'accent': '#2563eb'},
    'community':   {'ar': 'الأسرة والمجتمع',   'en': 'Community',     'bg': '#0e7490', 'accent': '#0e7490'},
}


def gallery(lang='ar'):
    """قائمة المعرض للمحرّر."""
    return [{'key': k, 'name': v['en'] if lang == 'en' else v['ar'], 'url': f'/static/themes/{k}.svg',
             'bg': v['bg'], 'accent': v['accent']} for k, v in THEMES.items()]


DEFAULT = 'classroom'          # خلفية النماذج الجديدة حتى لا تظهر صفحة فارغة
LIGHT = {'heritage', 'calm'}   # خلفيات فاتحة: نص التذييل داكن عليها


def settings_for(key=DEFAULT):
    """إعدادات المظهر التي يضبطها اختيار خلفية من المعرض."""
    t = THEMES.get(key) or THEMES[DEFAULT]
    key = key if key in THEMES else DEFAULT
    return {'bg_image': f'/static/themes/{key}.svg', 'bg_color': t['bg'], 'accent': t['accent'], 'bg_overlay': 0, 'bg_video': ''}


def is_light(url):
    return any((url or '') == f'/static/themes/{k}.svg' for k in LIGHT)
