"""إعدادات حساب Microsoft للمدرسة (Microsoft Entra) من لوحة الإدارة.

تُحفظ القيم في ملف .env على الخادم (خارج المستودع)، بالأسماء نفسها في الأنظمة الأخرى (MS_TENANT_ID، MS_CLIENT_ID،
MS_CLIENT_SECRET، MS_SENDER_EMAIL)، وتُطبَّق فوراً دون إعادة تشغيل. السر لا يُعرض بعد حفظه أبداً.
"""
import os

from flask import current_app

KEYS = ('MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'MS_SENDER_EMAIL')
BASE = os.path.dirname(os.path.abspath(__file__))


def env_path():
    return current_app.config.get('ENV_FILE') or os.path.join(BASE, '.env')


def save(values):
    """يكتب القيم المعطاة في .env (ويُبقي بقية الأسطر كما هي) ويطبّقها على التطبيق."""
    path = env_path()
    lines = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8-sig') as fh:
            lines = fh.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        k = line.split('=', 1)[0].strip()
        if k in values:
            lines[i] = f'{k}={values[k]}'
            done.add(k)
    lines += [f'{k}={v}' for k, v in values.items() if k not in done]
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    for k, v in values.items():
        current_app.config[k] = v
        os.environ[k] = v
    import mail
    mail._token_cache.update(token=None, expires_at=0, key=None)


def status():
    c = current_app.config
    return {'tenant': c.get('MS_TENANT_ID') or '', 'client': c.get('MS_CLIENT_ID') or '',
            'has_secret': bool(c.get('MS_CLIENT_SECRET')), 'sender': c.get('MS_SENDER_EMAIL') or '',
            'complete': all(c.get(k) for k in KEYS[:3])}


def test():
    """فحوص الاتصال بعبارات واضحة: [(نجح؟, نص عربي, نص إنجليزي)]."""
    import mail
    out = []
    if not status()['complete']:
        return [(False, 'أكمل معرّف الجهة ومعرّف التطبيق والسر أولاً.', 'Complete the tenant ID, application ID and secret first.')]
    try:
        mail._token_cache.update(token=None, expires_at=0, key=None)
        mail._graph_token()
        out.append((True, 'الاتصال بحساب Microsoft للمدرسة يعمل.', 'The connection to the school Microsoft account works.'))
    except Exception as e:  # noqa: BLE001
        current_app.logger.warning('[tenant] token: %s', e)
        return [(False, 'تعذّر الاتصال: تأكد من معرّف الجهة ومعرّف التطبيق والسر، ومن أن السر لم تنتهِ صلاحيته.',
                 'Could not connect: check the tenant ID, application ID and secret, and that the secret has not expired.')]
    for path, ok_ar, ok_en, bad_ar, bad_en in (
            ('/users?$top=1&$select=id', 'قراءة أسماء الموظفين والطلبة من الدليل متاحة.', 'Reading people from the directory works.',
             'قراءة الدليل غير مسموحة بعد: أضف صلاحية User.Read.All من نوع Application وامنح موافقة المسؤول.',
             'Reading the directory is not allowed yet: add the Application permission User.Read.All and grant admin consent.'),
            ('/groups?$top=1&$select=id', 'قراءة المجموعات متاحة.', 'Reading groups works.',
             'قراءة المجموعات غير مسموحة بعد: أضف صلاحيتي Group.Read.All وGroupMember.Read.All من نوع Application.',
             'Reading groups is not allowed yet: add the Application permissions Group.Read.All and GroupMember.Read.All.')):
        try:
            mail.graph_get(path, limit=1)
            out.append((True, ok_ar, ok_en))
        except Exception as e:  # noqa: BLE001
            current_app.logger.warning('[tenant] %s: %s', path, e)
            out.append((False, bad_ar, bad_en))
    if not status()['sender']:
        out.append((False, 'لم يُحدَّد بريد المرسل، فلن تُرسل الدعوات والرموز.', 'No sender mailbox is set, so invitations and codes will not be sent.'))
    return out
