"""إعادة تعيين كلمة مرور مستخدم من الخادم نفسه (عند نسيان كلمة المرور).

    python ops/reset_password.py     # يعرض المستخدمين ثم يسأل عن اسم المستخدم وكلمة المرور الجديدة

رسائل هذا الأمر بالإنجليزية لأن الطرفية لا تعرض العربية سليمة.
"""
import getpass
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ops'))
from common import load_env  # noqa: E402

load_env()
from app import create_app  # noqa: E402
from models import User, db  # noqa: E402

app = create_app()
with app.app_context():
    users = User.query.order_by(User.id).all()
    print('Users: ' + ', '.join(f"{u.username} ({u.role}{'' if u.active else ', disabled'})" for u in users))
    name = input('User name: ').strip()
    user = next((u for u in users if u.username.lower() == name.lower()), None)
    if not user:
        sys.exit('No user with this name')
    pw = getpass.getpass('New password (at least 8 characters, hidden while typing): ')
    if len(pw) < 8 or pw != getpass.getpass('Type it again: '):
        sys.exit('Too short or not matching')
    user.set_password(pw)                      # يزيد session_ver فتخرج الجلسات المفتوحة
    db.session.commit()
    print(f'Done. Password of "{user.username}" changed - sign in with it now.')
