# FORMS — النماذج والاستبيانات (9.iajaward.org)

نظام نماذج واستبيانات واختبارات للمدرسة: 28 نوع سؤال، منطق وتفرّع، وضع الاختبار، خلفيات فيديو وصورة وموسيقى، لغتان، دخول بالبريد، نماذج فرعية، لصق نص أو سكربت، تحليل ومقارنة وتصدير.

- الدليل: [`docs/Forms.md`](docs/Forms.md) — وقواعد الوكيل: [`CLAUDE.md`](CLAUDE.md)
- التثبيت على كمبيوتر المدرسة: `1_setup.bat` ثم `3_autostart.bat` (كمسؤول)، والتحديث `update.bat`.
- التجربة المحلية: `venv\Scripts\python serve.py` ثم `http://localhost:8009/admin`
- الاختبارات: `python -m pip install -r requirements-dev.txt` ثم `python -m pytest -q tests/` و`python tests/e2e_browser.py`
