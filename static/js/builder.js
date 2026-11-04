/* محرّر النماذج: الأسئلة والخيارات والمنطق والاختبار والإعدادات، مع حفظ تلقائي إلى /admin/api/forms/<id>. */
(function () {
  'use strict';
  const F = window.FORM, B = window.B, AR = window.LANG !== 'en';
  const T = (ar, en) => (AR ? ar : en);
  const S = F.settings = F.settings || {};
  const Q = F.schema.questions;
  const TYPES = B.types;
  let open = null;            // معرّف السؤال المفتوح للتعديل
  const uid = (p) => p + '_' + Math.random().toString(16).slice(2, 10);

  // ── أدوات DOM ──────────────────────────────────────────────────────────
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (k === 'value') el.value = v;
      else if (k === 'checked') el.checked = !!v;
      else el.setAttribute(k, v === true ? '' : v);
    }
    kids.flat().forEach((c) => { if (c !== null && c !== undefined && c !== false) el.append(c.nodeType ? c : String(c)); });
    return el;
  }
  const icon = (n) => h('i', { class: 'fa-solid ' + n, 'aria-hidden': 'true' });
  const typeName = (t) => (TYPES[t] ? (AR ? TYPES[t][0] : TYPES[t][1]) : t);
  const isChoice = (t) => ['single', 'multi', 'dropdown', 'yesno', 'image_choice'].includes(t);
  const oneChoice = (t) => ['single', 'dropdown', 'yesno', 'image_choice'].includes(t);
  const isMatrix = (t) => ['likert', 'matrix', 'matrix_multi'].includes(t);
  const noAnswer = (t) => t === 'section' || t === 'statement';

  // ── الحفظ التلقائي ─────────────────────────────────────────────────────
  const state = document.getElementById('saveState');
  let timer = null, saving = false, again = false;
  function setState(cls, text) { state.className = 'save-state ' + cls; state.textContent = text; }
  function dirty() { setState('wait', T('تغييرات غير محفوظة…', 'Unsaved changes…')); clearTimeout(timer); timer = setTimeout(save, 700); }
  async function save() {
    if (saving) { again = true; return; }
    saving = true; setState('wait', T('جارٍ الحفظ…', 'Saving…'));
    try {
      const r = await fetch(B.saveUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: F.title, title_en: F.title_en, description: F.description, category: F.category,
          parent_id: F.parent_id, status: F.status, schema: { questions: Q }, settings: S }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error || r.status);
      // الخادم ينظّف البنية ويعطي معرّفات ثابتة؛ نأخذها دون إعادة رسم ما يُكتب الآن
      const srv = d.form.schema.questions;
      if (srv.length === Q.length) srv.forEach((q, i) => { if (Q[i].id !== q.id) Q[i].id = q.id; });
      setState('ok', T('محفوظ ✓', 'Saved ✓'));
    } catch (e) {
      setState('bad', T('تعذّر الحفظ — ', 'Could not save — ') + (e.message || ''));
    } finally {
      saving = false;
      if (again) { again = false; save(); }
    }
  }
  window.addEventListener('beforeunload', (e) => { if (timer && state.classList.contains('wait')) { e.preventDefault(); e.returnValue = ''; } });

  // ── ربط حقول النموذج والإعدادات (data-f / data-s) ──────────────────────
  function bindField(el, get, set) {
    const v = get();
    if (el.type === 'checkbox') el.checked = !!v;
    else if (el.type === 'color') el.value = v || (el.dataset.s === 'bg_color' ? '#f0f4fa' : '#0C67EC');
    else if (el.type === 'range') el.value = v === undefined || v === null ? (el.dataset.s === 'music_volume' ? 40 : 35) : v;
    else el.value = v === undefined || v === null ? '' : v;
    el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input', () => {
      let val = el.type === 'checkbox' ? el.checked : el.value;
      if (el.type === 'number' || el.type === 'range') val = el.value === '' ? null : Number(el.value);
      set(val); dirty(); onSettingChange(el.dataset.s || el.dataset.f);
    });
  }
  document.querySelectorAll('[data-f]').forEach((el) => bindField(el, () => F[el.dataset.f], (v) => { F[el.dataset.f] = v; }));
  document.querySelectorAll('[data-s]').forEach((el) => bindField(el, () => S[el.dataset.s], (v) => { S[el.dataset.s] = v; }));
  const statusSel = document.getElementById('statusSel');
  statusSel.value = F.status;
  statusSel.addEventListener('change', () => {
    F.status = statusSel.value; dirty();
    const w = document.getElementById('shareWarn'); if (w) w.hidden = F.status === 'open';
  });
  function onSettingChange(key) {
    if (key === 'bilingual' || key === 'quiz') renderList();
    if (key === 'bilingual') document.body.classList.toggle('bi', !!S.bilingual);
    if (key === 'bg_overlay') document.getElementById('ovOut').textContent = S.bg_overlay ?? 35;
    if (key && key.startsWith('bg_') || key === 'header_image') mediaPreviews();
    if (key === 'title') document.title = F.title;
  }
  document.body.classList.toggle('bi', !!S.bilingual);
  document.getElementById('ovOut').textContent = S.bg_overlay ?? 35;

  // ── رفع الملفات (الخلفية، الموسيقى، الفيديو، صور الأسئلة والخيارات) ─────
  async function upload(file, kind) {
    const fd = new FormData();
    fd.append('file', file); fd.append('kind', kind); fd.append('form_id', F.id);
    setState('wait', T('جارٍ رفع الملف…', 'Uploading…'));
    const r = await fetch(B.mediaUrl, { method: 'POST', body: fd });
    const d = await r.json().catch(() => ({ ok: false, error: r.status === 413 ? T('الملف كبير جداً.', 'The file is too large.') : r.status }));
    if (!d.ok) { setState('bad', d.error || T('تعذّر الرفع', 'Upload failed')); alert(d.error || T('تعذّر الرفع', 'Upload failed')); return null; }
    setState('ok', T('رُفع الملف ✓', 'Uploaded ✓'));
    return d.url;
  }
  function mediaPreviews() {
    document.querySelectorAll('.media-field').forEach((box) => {
      const key = box.dataset.media, url = S[key], prev = box.querySelector('.media-prev');
      prev.innerHTML = '';
      if (!url) return;
      if (box.dataset.kind === 'image') prev.append(h('img', { src: url, alt: '' }));
      else if (box.dataset.kind === 'video') prev.append(h('video', { src: url, muted: true, controls: true, preload: 'metadata' }));
      else prev.append(h('audio', { src: url, controls: true, preload: 'none' }));
    });
  }
  document.querySelectorAll('.media-field').forEach((box) => {
    const key = box.dataset.media, inp = box.querySelector('[data-s]');
    box.querySelector('input[type=file]').addEventListener('change', async (e) => {
      const f = e.target.files[0]; if (!f) return;
      const url = await upload(f, box.dataset.kind);
      e.target.value = '';
      if (url) { S[key] = url; inp.value = url; mediaPreviews(); dirty(); }
    });
    box.querySelector('[data-clear]').addEventListener('click', () => { S[key] = ''; inp.value = ''; mediaPreviews(); dirty(); });
  });
  mediaPreviews();

  // ── بيانات المستجيب ────────────────────────────────────────────────────
  const PRESETS = {
    name: { key: 'name', label: 'الاسم الكامل', label_en: 'Full name', type: 'text', required: true },
    phone: { key: 'phone', label: 'رقم الهاتف', label_en: 'Phone number', type: 'phone', required: true },
    grade: { key: 'grade', label: 'الصف والشعبة', label_en: 'Grade and section', type: 'text', required: true },
    idno: { key: 'national_id', label: 'الرقم الوطني', label_en: 'National number', type: 'text', required: false },
  };
  function renderFiller() {
    const box = document.getElementById('fillerList');
    const list = S.filler_fields = S.filler_fields || [];
    box.innerHTML = '';
    if (!list.length) box.append(h('p', { class: 'muted small' }, T('لا توجد حقول؛ لن تظهر هذه الخطوة.', 'No fields; this step will not appear.')));
    list.forEach((fd, i) => {
      const upd = (k) => (e) => { fd[k] = e.target.type === 'checkbox' ? e.target.checked : e.target.value; dirty(); };
      box.append(h('div', { class: 'filler-row' },
        h('input', { type: 'text', value: fd.label, placeholder: T('العنوان', 'Label'), 'aria-label': T('العنوان', 'Label'), oninput: upd('label') }),
        h('input', { type: 'text', value: fd.label_en || '', class: 'bi-only', dir: 'ltr', placeholder: 'English', 'aria-label': 'English', oninput: upd('label_en') }),
        h('select', { 'aria-label': T('النوع', 'Type'), onchange: (e) => { upd('type')(e); renderFiller(); } },
          ...[['text', T('نص', 'Text')], ['email', T('بريد', 'Email')], ['phone', T('هاتف', 'Phone')], ['number', T('رقم', 'Number')], ['date', T('تاريخ', 'Date')], ['select', T('قائمة', 'List')]]
            .map(([v, l]) => h('option', { value: v, selected: fd.type === v }, l))),
        fd.type === 'select' ? h('input', { type: 'text', value: fd.options || '', placeholder: T('الخيارات مفصولة بفاصلة', 'Options separated by commas'), oninput: upd('options') }) : null,
        h('label', { class: 'check mini' }, h('input', { type: 'checkbox', checked: fd.required, onchange: upd('required') }), T('مطلوب', 'Required')),
        h('button', { type: 'button', class: 'sm danger', title: T('حذف', 'Delete'), 'aria-label': T('حذف', 'Delete'), onclick: () => { list.splice(i, 1); renderFiller(); dirty(); } }, icon('fa-trash'))));
    });
  }
  document.getElementById('addFiller').addEventListener('click', () => {
    (S.filler_fields = S.filler_fields || []).push({ key: 'f' + Date.now().toString(36), label: T('حقل جديد', 'New field'), type: 'text', required: false });
    renderFiller(); dirty();
  });
  document.querySelectorAll('[data-preset]').forEach((b) => b.addEventListener('click', () => {
    const p = PRESETS[b.dataset.preset];
    S.filler_fields = S.filler_fields || [];
    if (S.filler_fields.some((x) => x.key === p.key)) return;
    S.filler_fields.push(Object.assign({}, p)); renderFiller(); dirty();
  }));
  renderFiller();

  // ── إضافة سؤال ─────────────────────────────────────────────────────────
  function newQuestion(type) {
    const q = { id: uid(type === 'section' ? 's' : 'q'), type, title: type === 'section' ? T('قسم جديد', 'New section') : (type === 'statement' ? '' : T('سؤال بلا عنوان', 'Untitled question')) };
    if (isChoice(type) && type !== 'yesno') q.choices = [1, 2, 3].map((n) => ({ id: uid('c'), label: T('الخيار ', 'Option ') + n }));
    if (type === 'yesno') q.choices = [{ id: 'yes', label: 'نعم', label_en: 'Yes' }, { id: 'no', label: 'لا', label_en: 'No' }];
    if (type === 'ranking' || type === 'constant_sum') q.choices = [1, 2, 3].map((n) => ({ id: uid('c'), label: T('العنصر ', 'Item ') + n }));
    if (type === 'constant_sum') q.total = 100;
    if (isMatrix(type)) {
      q.rows = [1, 2].map((n) => ({ id: uid('r'), label: T('العبارة ', 'Statement ') + n }));
      q.cols = type === 'likert'
        ? [['أعارض بشدة', 'Strongly disagree'], ['أعارض', 'Disagree'], ['محايد', 'Neutral'], ['أوافق', 'Agree'], ['أوافق بشدة', 'Strongly agree']].map(([a, e]) => ({ id: uid('k'), label: a, label_en: e }))
        : [1, 2, 3].map((n) => ({ id: uid('k'), label: T('العمود ', 'Column ') + n }));
    }
    if (type === 'scale') Object.assign(q, { min: 1, max: 5 });
    if (type === 'rating') Object.assign(q, { max: 5, icon: 'star' });
    if (type === 'nps') Object.assign(q, { min: 0, max: 10, min_label: 'غير محتمل إطلاقاً', max_label: 'محتمل جداً' });
    if (type === 'slider') Object.assign(q, { min: 0, max: 100, step: 1 });
    if (type === 'file') Object.assign(q, { max_files: 1, max_mb: 10, accept: 'any' });
    if (type === 'hidden') Object.assign(q, { title: T('المصدر', 'Source'), param: 'ref' });
    if (S.quiz && !noAnswer(type)) q.quiz = { points: 1, correct: [] };
    return q;
  }
  function addQuestion(type) {
    const q = newQuestion(type);
    let at = Q.length;
    if (open) { const i = Q.findIndex((x) => x.id === open); if (i >= 0) at = i + 1; }
    Q.splice(at, 0, q);
    open = q.id; renderList(); dirty();
    const el = document.querySelector(`[data-qid="${q.id}"]`);
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); const t = el.querySelector('.q-title-in'); if (t) setTimeout(() => t.select(), 250); }
  }
  document.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => addQuestion(b.dataset.add)));
  const dlg = document.getElementById('typeDlg');
  const dlgItems = document.getElementById('dlgItems');
  document.querySelectorAll('.palette .pal-btn').forEach((b) => {
    const c = b.cloneNode(true);
    c.addEventListener('click', () => { dlg.close(); addQuestion(c.dataset.add); });
    dlgItems.append(c);
  });
  document.getElementById('addBtn').addEventListener('click', () => (dlg.showModal ? dlg.showModal() : addQuestion('single')));

  // ── قائمة الأسئلة ──────────────────────────────────────────────────────
  const list = document.getElementById('qlist');
  function numbers() {
    const m = {}; let n = 0, page = 1;
    Q.forEach((q, i) => {
      if (q.type === 'section') { if (i > 0) page++; m[q.id] = { page }; return; }
      if (q.type === 'statement' || q.type === 'hidden') { m[q.id] = { page }; return; }
      m[q.id] = { n: ++n, page };
    });
    return m;
  }
  function renderList() {
    const nums = numbers();
    list.innerHTML = '';
    if (!Q.length) list.append(h('div', { class: 'card empty' }, h('p', {}, T('لا توجد أسئلة. أضف أول سؤال من القائمة.', 'No questions. Add the first one from the list.'))));
    Q.forEach((q, i) => list.append(card(q, i, nums)));
    quizTotal();
  }
  function quizTotal() {
    const el = document.getElementById('quizTotal'); if (!el) return;
    const tot = Q.reduce((s, q) => s + (q.quiz && Number(q.quiz.points) || 0), 0);
    el.textContent = S.quiz ? T(`مجموع الدرجات: ${tot}`, `Total points: ${tot}`) : '';
  }
  function summary(q) {
    if (q.type === 'section') return q.help || '';
    if (isChoice(q.type) || q.type === 'ranking' || q.type === 'constant_sum') return (q.choices || []).map((c) => c.label).join(' · ');
    if (isMatrix(q.type)) return (q.rows || []).length + T(' صفوف × ', ' rows × ') + (q.cols || []).length + T(' أعمدة', ' columns');
    if (q.type === 'scale' || q.type === 'nps' || q.type === 'slider') return `${q.min ?? ''} — ${q.max ?? ''}`;
    if (q.type === 'hidden') return '?' + (q.param || 'ref') + '=…';
    return '';
  }
  function card(q, i, nums) {
    const isOpen = open === q.id;
    const sec = q.type === 'section';
    const head = h('div', { class: 'q-head', role: 'button', tabindex: 0, 'aria-expanded': isOpen ? 'true' : 'false',
      onclick: (e) => { if (e.target.closest('.q-tools')) return; open = isOpen ? null : q.id; renderList(); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) { open = isOpen ? null : q.id; renderList(); } } },
    h('span', { class: 'drag', title: T('اسحب لتغيير الترتيب', 'Drag to reorder'), 'aria-hidden': 'true' }, icon('fa-grip-vertical')),
    h('span', { class: 'q-ico' }, icon(TYPES[q.type] ? TYPES[q.type][3] : 'fa-question')),
    h('div', { class: 'q-sum' },
      h('div', { class: 'q-t' }, sec ? T(`الصفحة ${nums[q.id].page}: `, `Page ${nums[q.id].page}: `) : (nums[q.id] && nums[q.id].n ? nums[q.id].n + '. ' : ''),
        q.title || h('span', { class: 'muted' }, T('بلا عنوان', 'Untitled')), q.required ? h('span', { class: 'req' }, ' *') : null),
      h('div', { class: 'q-meta' }, h('span', { class: 'badge' }, typeName(q.type)),
        q.logic && q.logic.show_if ? h('span', { class: 'badge warn' }, icon('fa-code-branch'), ' ', T('شرط إظهار', 'Display rule')) : null,
        (q.choices || []).some((c) => c.goto) || q.next ? h('span', { class: 'badge warn' }, icon('fa-route'), ' ', T('تفرّع', 'Branching')) : null,
        S.quiz && q.quiz && q.quiz.points ? h('span', { class: 'badge violet' }, q.quiz.points + T(' درجة', ' pts')) : null,
        h('span', { class: 'muted small ellip' }, summary(q)))),
    h('div', { class: 'q-tools' },
      h('button', { type: 'button', class: 'icon-btn', title: T('أعلى', 'Up'), 'aria-label': T('تحريك للأعلى', 'Move up'), disabled: i === 0, onclick: () => move(i, -1) }, icon('fa-arrow-up')),
      h('button', { type: 'button', class: 'icon-btn', title: T('أسفل', 'Down'), 'aria-label': T('تحريك للأسفل', 'Move down'), disabled: i === Q.length - 1, onclick: () => move(i, 1) }, icon('fa-arrow-down')),
      h('button', { type: 'button', class: 'icon-btn', title: T('تكرار', 'Duplicate'), 'aria-label': T('تكرار السؤال', 'Duplicate question'), onclick: () => dup(i) }, icon('fa-clone')),
      h('button', { type: 'button', class: 'icon-btn danger-ico', title: T('حذف', 'Delete'), 'aria-label': T('حذف السؤال', 'Delete question'), onclick: () => del(i) }, icon('fa-trash'))));
    const el = h('div', { class: 'card qcard' + (isOpen ? ' open' : '') + (sec ? ' sec' : ''), 'data-qid': q.id, draggable: 'true' }, head);
    if (isOpen) el.append(editor(q, i));
    // السحب والإفلات
    el.addEventListener('dragstart', (e) => {
      if (e.target.closest('input,textarea,select,.q-body')) { e.preventDefault(); return; }
      e.dataTransfer.setData('text/plain', String(i)); el.classList.add('dragging');
    });
    el.addEventListener('dragend', () => el.classList.remove('dragging'));
    el.addEventListener('dragover', (e) => { e.preventDefault(); el.classList.add('drop'); });
    el.addEventListener('dragleave', () => el.classList.remove('drop'));
    el.addEventListener('drop', (e) => {
      e.preventDefault(); el.classList.remove('drop');
      const from = Number(e.dataTransfer.getData('text/plain'));
      if (Number.isNaN(from) || from === i) return;
      const [m] = Q.splice(from, 1); Q.splice(i, 0, m); renderList(); dirty();
    });
    return el;
  }
  function move(i, d) { const j = i + d; if (j < 0 || j >= Q.length) return; [Q[i], Q[j]] = [Q[j], Q[i]]; renderList(); dirty(); }
  function dup(i) {
    const c = JSON.parse(JSON.stringify(Q[i]));
    c.id = uid(c.type === 'section' ? 's' : 'q');
    (c.choices || []).forEach((o) => { if (c.type !== 'yesno') o.id = uid('c'); });
    (c.rows || []).forEach((o) => { o.id = uid('r'); }); (c.cols || []).forEach((o) => { o.id = uid('k'); });
    if (c.quiz) c.quiz.correct = [];
    Q.splice(i + 1, 0, c); open = c.id; renderList(); dirty();
  }
  function del(i) {
    const q = Q[i];
    const used = Q.some((x) => x.logic && x.logic.show_if && x.logic.show_if.rules.some((r) => r.q === q.id));
    const msg = (B.nResponses ? T('للنموذج إجابات؛ حذف السؤال يُخفي إجاباته من الجداول والتحليل. ', 'This form has responses; deleting the question hides its answers from tables and analysis. ') : '') +
      (used ? T('أسئلة أخرى تعتمد عليه في شروط الإظهار. ', 'Other questions use it in display rules. ') : '') + T('حذف السؤال؟', 'Delete the question?');
    if (!confirm(msg)) return;
    Q.splice(i, 1);
    Q.forEach((x) => { if (x.logic && x.logic.show_if) { x.logic.show_if.rules = x.logic.show_if.rules.filter((r) => r.q !== q.id); if (!x.logic.show_if.rules.length) delete x.logic; }
      (x.choices || []).forEach((c) => { if (c.goto === q.id) delete c.goto; }); if (x.next === q.id) delete x.next; });
    renderList(); dirty();
  }

  // ── محرّر السؤال ───────────────────────────────────────────────────────
  function field(label, input, cls) { return h('div', { class: 'fld ' + (cls || '') }, h('label', {}, label), input); }
  function txt(q, key, ph, opts) {
    opts = opts || {};
    const tag = opts.area ? 'textarea' : 'input';
    return h(tag, Object.assign({ type: opts.type || 'text', value: q[key] ?? '', placeholder: ph || '', rows: opts.area ? 2 : null, dir: opts.ltr ? 'ltr' : null,
      class: opts.cls || null,
      oninput: (e) => { const v = e.target.value; q[key] = opts.type === 'number' ? (v === '' ? undefined : Number(v)) : v; dirty(); if (opts.rerenderHead) updateHead(q); } }, opts.attrs || {}));
  }
  function updateHead(q) {
    const el = document.querySelector(`[data-qid="${q.id}"] .q-t`);
    if (el) { const n = numbers()[q.id]; el.textContent = (q.type === 'section' ? T(`الصفحة ${n.page}: `, `Page ${n.page}: `) : (n && n.n ? n.n + '. ' : '')) + (q.title || ''); if (q.required) el.append(h('span', { class: 'req' }, ' *')); }
  }
  function chk(q, key, label, after) {
    return h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: !!q[key], onchange: (e) => { q[key] = e.target.checked; dirty(); if (after) after(); } }), h('span', { class: 'sl' }), h('span', {}, label));
  }
  function editor(q, i) {
    const body = h('div', { class: 'q-body' });
    const sec = q.type === 'section';
    body.append(h('div', { class: 'q-row' },
      field(sec ? T('عنوان القسم', 'Section title') : (q.type === 'statement' ? T('العنوان (اختياري)', 'Title (optional)') : T('السؤال', 'Question')),
        txt(q, 'title', '', { cls: 'q-title-in', rerenderHead: true }), 'grow'),
      field(T('النوع', 'Type'), h('select', { onchange: (e) => changeType(q, e.target.value) },
        ...Object.keys(TYPES).map((t) => h('option', { value: t, selected: t === q.type }, typeName(t)))))));
    body.append(field(T('العنوان بالإنجليزية', 'Title in English'), txt(q, 'title_en', '', { ltr: true }), 'bi-only'));
    body.append(field(sec ? T('وصف القسم', 'Section description') : T('وصف أو تلميح (اختياري)', 'Description or hint (optional)'), txt(q, 'help', '', { area: true })));
    body.append(field(T('الوصف بالإنجليزية', 'Description in English'), txt(q, 'help_en', '', { area: true, ltr: true }), 'bi-only'));
    const t = q.type;
    if (isChoice(t) || t === 'ranking' || t === 'constant_sum') body.append(optionsEditor(q, 'choices', T('الخيارات', 'Options')));
    if (isMatrix(t)) { body.append(optionsEditor(q, 'rows', T('الصفوف (العبارات)', 'Rows (statements)'))); body.append(optionsEditor(q, 'cols', T('الأعمدة', 'Columns'))); }
    const extra = h('div', { class: 'form-grid' });
    if (t === 'scale') {
      extra.append(field(T('من', 'From'), h('select', { onchange: (e) => { q.min = Number(e.target.value); dirty(); } }, ...[0, 1].map((v) => h('option', { value: v, selected: q.min === v }, v)))));
      extra.append(field(T('إلى', 'To'), h('select', { onchange: (e) => { q.max = Number(e.target.value); dirty(); } }, ...[2, 3, 4, 5, 6, 7, 8, 9, 10].map((v) => h('option', { value: v, selected: q.max === v }, v)))));
    }
    if (t === 'rating') {
      extra.append(field(T('عدد الدرجات', 'Levels'), h('select', { onchange: (e) => { q.max = Number(e.target.value); dirty(); } }, ...[3, 4, 5, 6, 7, 8, 9, 10].map((v) => h('option', { value: v, selected: q.max === v }, v)))));
      extra.append(field(T('الشكل', 'Shape'), h('select', { onchange: (e) => { q.icon = e.target.value; dirty(); } },
        ...[['star', T('نجوم', 'Stars')], ['heart', T('قلوب', 'Hearts')], ['smile', T('وجوه', 'Faces')], ['thumb', T('إبهام', 'Thumbs')]].map(([v, l]) => h('option', { value: v, selected: q.icon === v }, l)))));
    }
    if (t === 'slider' || t === 'number') {
      extra.append(field(T('أقل قيمة', 'Minimum'), txt(q, 'min', '', { type: 'number' })));
      extra.append(field(T('أعلى قيمة', 'Maximum'), txt(q, 'max', '', { type: 'number' })));
      if (t === 'slider') extra.append(field(T('الخطوة', 'Step'), txt(q, 'step', '', { type: 'number' })));
    }
    if (['scale', 'nps', 'slider', 'rating'].includes(t)) {
      extra.append(field(T('عنوان الطرف الأدنى', 'Low end label'), txt(q, 'min_label', T('مثال: ضعيف', 'e.g. Poor'))));
      extra.append(field(T('عنوان الطرف الأعلى', 'High end label'), txt(q, 'max_label', T('مثال: ممتاز', 'e.g. Excellent'))));
    }
    if (t === 'multi') {
      extra.append(field(T('أقل عدد اختيارات', 'Minimum selections'), txt(q, 'min_select', '', { type: 'number', attrs: { min: 0 } })));
      extra.append(field(T('أكثر عدد اختيارات', 'Maximum selections'), txt(q, 'max_select', '', { type: 'number', attrs: { min: 0 } })));
    }
    if (t === 'constant_sum') extra.append(field(T('المجموع المطلوب', 'Required total'), txt(q, 'total', '100', { type: 'number' })));
    if (t === 'file') {
      extra.append(field(T('عدد الملفات', 'Number of files'), txt(q, 'max_files', '1', { type: 'number', attrs: { min: 1, max: 10 } })));
      extra.append(field(T('حجم الملف الأعلى (ميغابايت)', 'Max file size (MB)'), txt(q, 'max_mb', '10', { type: 'number', attrs: { min: 1, max: 25 } })));
      extra.append(field(T('الأنواع المقبولة', 'Accepted types'), h('select', { onchange: (e) => { q.accept = e.target.value; dirty(); } },
        ...[['any', T('أي ملف', 'Any file')], ['image', T('صور', 'Images')], ['pdf', 'PDF'], ['doc', T('مستندات', 'Documents')], ['media', T('صوت وفيديو', 'Audio and video')]].map(([v, l]) => h('option', { value: v, selected: q.accept === v }, l)))));
    }
    if (t === 'hidden') extra.append(field(T('اسم المتغيّر في الرابط', 'Parameter name in the link'), txt(q, 'param', 'ref', { ltr: true })));
    if (['short_text', 'long_text', 'email', 'phone', 'url'].includes(t)) {
      extra.append(field(T('نص داخل الحقل', 'Placeholder'), txt(q, 'placeholder', '')));
      const v = q.validation || {};
      extra.append(field(T('التحقق', 'Validation'), h('select', { onchange: (e) => { q.validation = e.target.value ? Object.assign({}, v, { kind: e.target.value }) : undefined; dirty(); renderList(); } },
        h('option', { value: '' }, T('بلا', 'None')), h('option', { value: 'length', selected: v.kind === 'length' }, T('طول النص', 'Text length')), h('option', { value: 'regex', selected: v.kind === 'regex' }, T('صيغة (تعبير نمطي)', 'Pattern (regex)')))));
      if (v.kind === 'length') {
        extra.append(field(T('أقل عدد أحرف', 'Min characters'), txt(v, 'min', '', { type: 'number' })));
        extra.append(field(T('أكثر عدد أحرف', 'Max characters'), txt(v, 'max', '', { type: 'number' })));
      }
      if (v.kind === 'regex') extra.append(field(T('الصيغة', 'Pattern'), txt(v, 'pattern', '^\\d{10}$', { ltr: true })));
      if (v.kind) extra.append(field(T('رسالة الخطأ', 'Error message'), txt(v, 'message', '')));
    }
    if (t === 'section') {
      extra.append(field(T('بعد هذا القسم انتقل إلى', 'After this section go to'), gotoSelect(q.next, (v) => { q.next = v || undefined; dirty(); }, q)));
    }
    if (extra.childNodes.length) body.append(extra);
    if (t === 'statement' || (!noAnswer(t) && t !== 'hidden')) body.append(mediaEditor(q));
    const flags = h('div', { class: 'q-flags' });
    if (!noAnswer(t) && t !== 'hidden') flags.append(chk(q, 'required', T('مطلوب', 'Required'), () => updateHead(q)));
    if (['single', 'multi', 'dropdown'].includes(t)) flags.append(chk(q, 'other', T('خيار «أخرى» مع خانة كتابة', '"Other" option with a text box'), renderList));
    if (['single', 'multi', 'dropdown', 'image_choice', 'ranking'].includes(t)) flags.append(chk(q, 'shuffle', T('ترتيب عشوائي للخيارات', 'Shuffle options')));
    body.append(flags);
    if (S.quiz && !noAnswer(t)) body.append(quizEditor(q));
    if (i > 0) body.append(logicEditor(q, i));
    return body;
  }
  function changeType(q, t) {
    const old = q.type; q.type = t;
    const fresh = newQuestion(t);
    if ((isChoice(t) || t === 'ranking' || t === 'constant_sum') && !(q.choices && q.choices.length && t !== 'yesno')) q.choices = fresh.choices;
    if (t === 'yesno') q.choices = fresh.choices;
    if (isMatrix(t) && (!q.rows || !q.cols || (t === 'likert' && old !== 'likert'))) { q.rows = q.rows || fresh.rows; q.cols = fresh.cols; }
    ['min', 'max', 'step', 'icon', 'max_files', 'max_mb', 'accept', 'param', 'total'].forEach((k) => { if (fresh[k] !== undefined) q[k] = fresh[k]; else delete q[k]; });
    if (q.quiz) q.quiz.correct = [];
    renderList(); dirty();
  }
  function optionsEditor(q, key, label) {
    const items = q[key] = q[key] || [];
    const wrap = h('div', { class: 'opts' }, h('label', {}, label));
    const multi = q.type === 'multi';
    const quiz = S.quiz && key === 'choices' && (isChoice(q.type));
    q.quiz = q.quiz || (S.quiz ? { points: 1, correct: [] } : q.quiz);
    items.forEach((o, j) => {
      const row = h('div', { class: 'opt-row' },
        h('span', { class: 'opt-mark' }, icon(key === 'rows' ? 'fa-grip-lines' : key === 'cols' ? 'fa-grip-lines-vertical' : multi ? 'fa-square' : q.type === 'ranking' ? 'fa-hashtag' : 'fa-circle')),
        h('input', { type: 'text', value: o.label, 'aria-label': label, oninput: (e) => { o.label = e.target.value; dirty(); },
          onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); addOpt(j + 1); } } }),
        h('input', { type: 'text', value: o.label_en || '', class: 'bi-only', dir: 'ltr', placeholder: 'English', 'aria-label': 'English', oninput: (e) => { o.label_en = e.target.value; dirty(); } }));
      if (q.type === 'image_choice' && key === 'choices') {
        const up = h('label', { class: 'btn sm ghost upl', title: T('صورة الخيار', 'Option image') }, o.image ? h('img', { src: o.image, alt: '', class: 'opt-img' }) : icon('fa-image'),
          h('input', { type: 'file', accept: 'image/*', hidden: true, onchange: async (e) => { const f = e.target.files[0]; if (!f) return; const u = await upload(f, 'image'); if (u) { o.image = u; renderList(); dirty(); } } }));
        row.append(up);
      }
      if (quiz) {
        const corr = q.quiz.correct = q.quiz.correct || [];
        row.append(h('label', { class: 'check mini corr', title: T('إجابة صحيحة', 'Correct answer') },
          h('input', { type: multi ? 'checkbox' : 'radio', name: 'corr_' + q.id, checked: corr.includes(o.id),
            onchange: (e) => { if (multi) { const k = corr.indexOf(o.id); if (e.target.checked && k < 0) corr.push(o.id); if (!e.target.checked && k >= 0) corr.splice(k, 1); } else { q.quiz.correct = [o.id]; } dirty(); } }),
          icon('fa-check')));
      }
      if (key === 'choices' && oneChoice(q.type)) row.append(gotoSelect(o.goto, (v) => { o.goto = v || undefined; dirty(); }, q, true));
      row.append(h('button', { type: 'button', class: 'icon-btn sm-ico', 'aria-label': T('حذف الخيار', 'Delete option'), title: T('حذف', 'Delete'), disabled: q.type === 'yesno' || items.length <= 1,
        onclick: () => { items.splice(j, 1); if (q.quiz && q.quiz.correct) q.quiz.correct = q.quiz.correct.filter((x) => x !== o.id); renderList(); dirty(); } }, icon('fa-xmark')));
      wrap.append(row);
    });
    function addOpt(at) {
      const p = key === 'rows' ? 'r' : key === 'cols' ? 'k' : 'c';
      items.splice(at ?? items.length, 0, { id: uid(p), label: (key === 'rows' ? T('العبارة ', 'Statement ') : key === 'cols' ? T('العمود ', 'Column ') : T('الخيار ', 'Option ')) + (items.length + 1) });
      renderList(); dirty();
      setTimeout(() => { const rows = document.querySelectorAll(`[data-qid="${q.id}"] .opts`); const el = [...rows].find((r) => r.firstChild.textContent === label); if (el) { const ins = el.querySelectorAll('.opt-row input[type=text]:not(.bi-only)'); const x = ins[at ?? ins.length - 1]; if (x) x.select(); } }, 30);
    }
    if (q.type !== 'yesno') {
      const bulkBox = h('textarea', { rows: 4, placeholder: T('خيار في كل سطر…', 'One option per line…'), hidden: true });
      wrap.append(h('div', { class: 'row-actions' },
        h('button', { type: 'button', class: 'sm ghost', onclick: () => addOpt() }, icon('fa-plus'), ' ', T('إضافة', 'Add')),
        h('button', { type: 'button', class: 'sm ghost', onclick: () => { bulkBox.hidden = !bulkBox.hidden; if (!bulkBox.hidden) bulkBox.focus(); } }, icon('fa-paste'), ' ', T('لصق قائمة', 'Paste a list')),
        bulkBox,
        h('button', { type: 'button', class: 'sm', hidden: true, 'data-apply': 1, onclick: () => {
          const lines = bulkBox.value.split(/\n|،|;/).map((s) => s.replace(/^\s*[-*•\d.)]+\s*/, '').trim()).filter(Boolean);
          const p = key === 'rows' ? 'r' : key === 'cols' ? 'k' : 'c';
          lines.forEach((l) => items.push({ id: uid(p), label: l })); renderList(); dirty();
        } }, T('أضف الأسطر', 'Add the lines'))));
      bulkBox.addEventListener('input', () => { wrap.querySelector('[data-apply]').hidden = !bulkBox.value.trim(); });
    }
    if (q.other && key === 'choices') wrap.append(h('div', { class: 'opt-row other' }, h('span', { class: 'opt-mark' }, icon('fa-pen')), h('span', { class: 'muted' }, T('أخرى: (يكتب المستجيب)', 'Other: (respondent writes)'))));
    return wrap;
  }
  function gotoSelect(value, set, q, compact) {
    const idx = Q.indexOf(q);
    const secs = Q.filter((x, k) => x.type === 'section' && k > idx);
    const sel = h('select', { class: compact ? 'goto' : '', title: T('الانتقال بعد هذا الاختيار', 'Go to after this choice'), 'aria-label': T('الانتقال', 'Go to'), onchange: (e) => set(e.target.value) },
      h('option', { value: '' }, compact ? T('← التالي', '→ next') : T('القسم التالي', 'The next section')),
      ...secs.map((s) => h('option', { value: s.id, selected: value === s.id }, T('← ', '→ ') + (s.title || T('قسم', 'Section')))),
      h('option', { value: '__submit__', selected: value === '__submit__' }, T('← إرسال النموذج', '→ submit the form')));
    if (compact && !secs.length && value !== '__submit__') sel.title = T('أضف أقساماً بعد هذا السؤال للتفرّع', 'Add sections after this question to branch');
    return sel;
  }
  function mediaEditor(q) {
    const m = q.media = q.media || {};
    const prev = h('div', { class: 'media-prev' }, m.image ? h('img', { src: m.image, alt: '' }) : null);
    const box = h('details', { class: 'q-media', open: q.type === 'statement' || m.image || m.video ? true : null },
      h('summary', {}, icon('fa-photo-film'), ' ', T('صورة أو فيديو مع السؤال', 'Image or video with the question')),
      h('div', { class: 'row' },
        h('label', { class: 'btn sm ghost shrink upl' }, icon('fa-image'), ' ', T('صورة', 'Image'),
          h('input', { type: 'file', accept: 'image/*', hidden: true, onchange: async (e) => { const f = e.target.files[0]; if (!f) return; const u = await upload(f, 'image'); if (u) { m.image = u; renderList(); dirty(); } } })),
        h('input', { type: 'url', dir: 'ltr', value: m.video || '', placeholder: T('رابط فيديو YouTube أو ملف MP4', 'YouTube or MP4 link'), oninput: (e) => { m.video = e.target.value; dirty(); } }),
        m.image ? h('button', { type: 'button', class: 'sm danger shrink', onclick: () => { delete m.image; renderList(); dirty(); } }, T('إزالة الصورة', 'Remove image')) : null),
      prev);
    return box;
  }
  function quizEditor(q) {
    const qz = q.quiz = q.quiz || { points: 1, correct: [] };
    const box = h('div', { class: 'quiz-box' }, h('div', { class: 'quiz-h' }, icon('fa-graduation-cap'), ' ', T('الاختبار', 'Quiz')));
    const g = h('div', { class: 'form-grid' });
    g.append(field(T('الدرجة', 'Points'), h('input', { type: 'number', min: 0, step: 0.5, value: qz.points ?? 0, oninput: (e) => { qz.points = Number(e.target.value) || 0; dirty(); quizTotal(); } })));
    if (['short_text', 'number', 'email', 'phone', 'url', 'scale', 'rating', 'nps', 'slider'].includes(q.type)) {
      g.append(field(T('الإجابات المقبولة (افصل بينها بـ |)', 'Accepted answers (separate with |)'), h('input', { type: 'text', value: (qz.correct || []).join(' | '),
        oninput: (e) => { qz.correct = e.target.value.split('|').map((s) => s.trim()).filter(Boolean); dirty(); } })));
      if (['number', 'slider'].includes(q.type)) g.append(field(T('السماحية ±', 'Tolerance ±'), h('input', { type: 'number', min: 0, step: 'any', value: qz.tolerance ?? '', oninput: (e) => { qz.tolerance = Number(e.target.value) || 0; dirty(); } })));
    } else if (q.type === 'ranking') {
      g.append(h('p', { class: 'note' }, T('الترتيب الصحيح هو ترتيب العناصر كما في القائمة أعلاه.', 'The correct order is the order of the items in the list above.')));
      qz.correct = (q.choices || []).map((c) => c.id);
    } else if (!isChoice(q.type)) {
      g.append(h('p', { class: 'note' }, T('يُصحَّح هذا السؤال يدوياً من صفحة الإجابة.', 'This question is marked by hand on the response page.')));
    } else {
      g.append(h('p', { class: 'note' }, T('علّم الإجابة الصحيحة بزر ✓ بجانب الخيار.', 'Mark the correct answer with the ✓ next to the option.')));
      if (q.type === 'multi') g.append(h('label', { class: 'check mini' }, h('input', { type: 'checkbox', checked: !!qz.partial, onchange: (e) => { qz.partial = e.target.checked; dirty(); } }), T('درجة جزئية', 'Partial credit')));
    }
    box.append(g);
    box.append(h('div', { class: 'form-grid' },
      field(T('ملاحظة عند الإجابة الصحيحة', 'Feedback when right'), txt(qz, 'feedback_ok', '')),
      field(T('ملاحظة عند الإجابة الخاطئة', 'Feedback when wrong'), txt(qz, 'feedback_bad', ''))));
    return box;
  }
  const OPS = [['eq', T('يساوي', 'equals')], ['neq', T('لا يساوي', 'does not equal')], ['contains', T('يحتوي', 'contains')],
    ['not_contains', T('لا يحتوي', 'does not contain')], ['gt', T('أكبر من', 'greater than')], ['lt', T('أصغر من', 'less than')],
    ['gte', T('أكبر من أو يساوي', 'at least')], ['lte', T('أصغر من أو يساوي', 'at most')], ['answered', T('أُجيب عنه', 'is answered')], ['empty', T('لم يُجب عنه', 'is not answered')]];
  function logicEditor(q, i) {
    const before = Q.slice(0, i).filter((x) => !noAnswer(x.type) && !['file', 'signature'].includes(x.type));
    const has = q.logic && q.logic.show_if;
    const box = h('details', { class: 'logic-box', open: has ? true : null }, h('summary', {}, icon('fa-code-branch'), ' ',
      q.type === 'section' ? T('شرط إظهار القسم كله', 'Show this whole section only if…') : T('شرط إظهار السؤال', 'Show this question only if…')));
    if (!before.length) { box.append(h('p', { class: 'note' }, T('لا توجد أسئلة قبله يمكن الاعتماد عليها.', 'There are no earlier questions to depend on.'))); return box; }
    const cond = has ? q.logic.show_if : null;
    if (!cond) {
      box.append(h('button', { type: 'button', class: 'sm ghost', onclick: () => { q.logic = { show_if: { mode: 'all', rules: [{ q: before[before.length - 1].id, op: 'eq', value: '' }] } }; renderList(); dirty(); } },
        icon('fa-plus'), ' ', T('إضافة شرط', 'Add a rule')));
      return box;
    }
    box.append(h('div', { class: 'row' }, h('select', { class: 'shrink', onchange: (e) => { cond.mode = e.target.value; dirty(); } },
      h('option', { value: 'all', selected: cond.mode !== 'any' }, T('كل الشروط', 'All rules')), h('option', { value: 'any', selected: cond.mode === 'any' }, T('أي شرط', 'Any rule')))));
    cond.rules.forEach((r, k) => {
      const src = Q.find((x) => x.id === r.q) || before[0];
      let valEl;
      const choices = src && (src.choices || (src.type === 'scale' || src.type === 'rating' || src.type === 'nps'
        ? Array.from({ length: (src.max || 5) - (src.type === 'rating' ? 1 : (src.min ?? 1)) + 1 }, (_, n) => ({ id: String(n + (src.type === 'rating' ? 1 : (src.min ?? 1))), label: String(n + (src.type === 'rating' ? 1 : (src.min ?? 1))) })) : null));
      if (['answered', 'empty'].includes(r.op)) valEl = h('span');
      else if (choices && !['gt', 'lt', 'gte', 'lte'].includes(r.op)) {
        valEl = h('select', { onchange: (e) => { r.value = e.target.value; dirty(); } }, h('option', { value: '' }, T('اختر…', 'Choose…')),
          ...choices.map((c) => h('option', { value: c.id, selected: String(r.value) === String(c.id) }, c.label)),
          src.other ? h('option', { value: '__other__', selected: r.value === '__other__' }, T('أخرى', 'Other')) : null);
      } else valEl = h('input', { type: 'text', value: r.value || '', oninput: (e) => { r.value = e.target.value; dirty(); } });
      box.append(h('div', { class: 'rule-row' },
        h('select', { 'aria-label': T('السؤال', 'Question'), onchange: (e) => { r.q = e.target.value; r.value = ''; renderList(); dirty(); } },
          ...before.map((x) => h('option', { value: x.id, selected: x.id === r.q }, (x.title || T('بلا عنوان', 'Untitled')).slice(0, 60)))),
        h('select', { 'aria-label': T('الشرط', 'Condition'), onchange: (e) => { r.op = e.target.value; renderList(); dirty(); } }, ...OPS.map(([v, l]) => h('option', { value: v, selected: r.op === v }, l))),
        valEl,
        h('button', { type: 'button', class: 'icon-btn sm-ico', 'aria-label': T('حذف الشرط', 'Delete rule'), onclick: () => { cond.rules.splice(k, 1); if (!cond.rules.length) delete q.logic; renderList(); dirty(); } }, icon('fa-xmark'))));
    });
    box.append(h('button', { type: 'button', class: 'sm ghost', onclick: () => { cond.rules.push({ q: before[before.length - 1].id, op: 'eq', value: '' }); renderList(); dirty(); } }, icon('fa-plus'), ' ', T('شرط آخر', 'Another rule')));
    return box;
  }

  // ── رابط بقيم مسبقة ────────────────────────────────────────────────────
  function renderPrefill() {
    const box = document.getElementById('prefill'); if (!box) return;
    const hidden = Q.filter((q) => q.type === 'hidden');
    box.innerHTML = '';
    if (!hidden.length) { box.append(h('p', { class: 'note' }, T('أضف سؤالاً من نوع «حقل مخفي من الرابط» لتسجيل مصدر الإجابة (مثل الصف أو الحملة) دون أن يراه المستجيب.', 'Add a "Hidden field" question to record where a response came from (such as the class or campaign) without the respondent seeing it.'))); return; }
    const out = h('input', { type: 'text', readonly: true, dir: 'ltr' });
    const vals = {};
    const upd = () => { const p = new URLSearchParams(); hidden.forEach((q) => { if (vals[q.param]) p.set(q.param, vals[q.param]); }); out.value = B.publicUrl + (p.toString() ? '?' + p : ''); };
    hidden.forEach((q) => box.append(field(q.title + ' (' + q.param + ')', h('input', { type: 'text', oninput: (e) => { vals[q.param] = e.target.value; upd(); } }))));
    upd();
    box.append(h('div', { class: 'copy-row' }, out, h('button', { type: 'button', onclick: (e) => { navigator.clipboard && navigator.clipboard.writeText(out.value); e.target.textContent = T('تم النسخ ✓', 'Copied ✓'); } }, T('نسخ', 'Copy'))));
  }
  document.addEventListener('tab-shown', (e) => { if (e.detail === 'share') renderPrefill(); });

  renderList();
  setState('ok', T('محفوظ ✓', 'Saved ✓'));
})();
