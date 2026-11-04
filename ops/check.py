"""forms_check.bat — one click: checks the forms system on this PC, fixes what it can, and says in plain words what is wrong.

    1. the website on this PC (http://localhost:8009)  → starts it if it is not running
    2. the public address (https://9.iajaward.org)      → is Cloudflare reaching this PC?
    3. the hourly backup                                 → when was the last one?
"""
import glob
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import backup_root, load_env  # noqa: E402

IS_WIN = os.name == 'nt'


def get(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'forms-check'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(20).decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def line(ok, text):
    print(('  [OK] ' if ok else '  [X]  ') + text)


def main():
    load_env()
    port = os.environ.get('PORT') or '8009'
    site = (os.environ.get('BASE_URL') or 'https://9.iajaward.org').rstrip('/')
    print('\n  FORMS - system check\n')
    code, body = get(f'http://127.0.0.1:{port}/healthz')
    if code != 200 and IS_WIN:
        print('  The website is not answering - starting it...')
        run(['schtasks', '/change', '/tn', 'FORMS Website', '/enable'])
        run(['schtasks', '/end', '/tn', 'FORMS Website'])
        time.sleep(2)
        run(['schtasks', '/run', '/tn', 'FORMS Website'])
        for _ in range(20):
            time.sleep(2)
            code, body = get(f'http://127.0.0.1:{port}/healthz')
            if code == 200:
                break
    line(code == 200, f'Website on this PC (port {port})' + ('' if code == 200 else ' - NOT running: see logs\\server.log'))
    code, body = get(f'{site}/healthz', timeout=15)
    line(code == 200 and body.strip() == 'ok', f'Public address {site}' + ('' if code == 200 else f' - not reachable ({body[:80]}) - run site_where.bat'))
    files = sorted(glob.glob(os.path.join(backup_root(), 'db', 'forms-*.db.gz')), key=os.path.getmtime)
    if files:
        age = (time.time() - os.path.getmtime(files[-1])) / 3600
        line(age < 3, f'Last backup {age:.1f} hours ago: {files[-1]}')
    else:
        line(False, f'No backup yet in {backup_root()} - run backup_now.bat')
    print()


if __name__ == '__main__':
    main()
