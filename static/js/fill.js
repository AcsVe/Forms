/* صفحة تعبئة النموذج: يرسم الأسئلة، ويطبّق منطق الإظهار والتفرّع (مطابق لـ schema.py)، ويتحقق، ويرسل. */
(function () {
  'use strict';
  const D = window.FILL, S = D.settings || {}, QS = D.questions || [];
  const EN = D.lang === 'en';
  const T = (ar, en) => (EN ? en : ar);
  const A = {};                     // الإجابات: معرّف السؤال ← القيمة
  const FILES = {};                 // ملفات أسئلة الرفع
  const touched = new Set();
  const OTHER = '__other__', SUBMIT = '__submit__';
  const NO_ANSWER = ['section', 'statement'];
  const ONE = ['single', 'dropdown', 'yesno', 'image_choice'];
  const tx = (o, k) => (EN && S.bilingual && o[k + '_en']) || o[k] || '';
  const params = new URLSearchParams(location.search);
  const draftKey = 'fdraft_' + D.slug;

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

  // ── المنطق (نسخة من schema.py) ─────────────────────────────────────────
  function pages() {
    const ps = [{ section: null, items: [] }];
    QS.forEach((q) => { if (q.type === 'section') ps.push({ section: q, items: [] }); else ps[ps.length - 1].items.push(q); });
    if (ps.length > 1 && !ps[0].items.length) ps.shift();
    return ps;
  }
  const PAGES = pages();
  const empty = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length) || (typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length);
  const norm = (v) => String(v ?? '').normalize('NFKC').toLowerCase().replace(/[ً-ْـ⁦-⁩]/g, '')
    .replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/\s+/g, ' ').trim();
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
  function checkRule(r, ans) {
    let v = ans[r.q]; const op = r.op || 'eq', t = r.value ?? '';
    if (op === 'answered') return !empty(v);
    if (op === 'empty') return empty(v);
    if (empty(v)) return op === 'neq' || op === 'not_contains';
    if (v && typeof v === 'object' && !Array.isArray(v)) v = Object.values(v).flat();
    if (Array.isArray(v)) { const has = v.map(String).includes(String(t)); return ['eq', 'contains'].includes(op) ? has : (['neq', 'not_contains'].includes(op) ? !has : false); }
    if (['gt', 'lt', 'gte', 'lte'].includes(op)) { const a = num(v), b = num(t); if (a === null || b === null) return false; return { gt: a > b, lt: a < b, gte: a >= b, lte: a <= b }[op]; }
    const a = norm(v), b = norm(t);
    return { eq: a === b, neq: a !== b, contains: a.includes(b), not_contains: !a.includes(b) }[op] || false;
  }
  function visible(item, ans) {
    const c = item && item.logic && item.logic.show_if;
    if (!c || !c.rules || !c.rules.length) return true;
    const res = c.rules.map((r) => checkRule(r, ans));
    return c.mode === 'any' ? res.some(Boolean) : res.every(Boolean);
  }
  const index = {}; PAGES.forEach((p, i) => { if (p.section) index[p.section.id] = i; });
  /* يمشي الصفحات بالإجابات الحالية: {visited, shown, next(i)} */
  function walk(ans) {
    const eff = {}, visited = [], shown = new Set(), nextOf = {};
    let i = 0;
    while (i >= 0 && i < PAGES.length) {
      const p = PAGES[i];
      if (p.section && !visible(p.section, eff)) { i++; continue; }
      visited.push(i);
      let jump = null;
      p.items.forEach((q) => {
        if (!visible(q, eff)) return;
        shown.add(q.id);
        if (NO_ANSWER.includes(q.type)) return;
        if (!empty(ans[q.id])) eff[q.id] = ans[q.id];
        if (ONE.includes(q.type) && q.id in eff) { const ch = (q.choices || []).find((c) => c.id === eff[q.id]); if (ch && ch.goto) jump = ch.goto; }
      });
      if (jump === null && p.section && p.section.next) jump = p.section.next;
      let n;
      if (jump === SUBMIT) n = -1;
      else if (jump && jump in index && index[jump] > i) n = index[jump];
      else n = i + 1;
      // الصفحة التالية الظاهرة فعلاً
      while (n >= 0 && n < PAGES.length && PAGES[n].section && !visible(PAGES[n].section, eff)) n++;
      nextOf[i] = n >= 0 && n < PAGES.length ? n : -1;
      if (n < 0) break;
      i = n;
    }
    return { visited, shown, nextOf };
  }

  // ── الرسم ──────────────────────────────────────────────────────────────
  const root = document.getElementById('pages');
  const QEL = {};
  let qn = 0;
  function shuffle(a) { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
  function mediaBlock(m) {
    if (!m) return null;
    const box = h('div', { class: 'q-media' });
    if (m.image) box.append(h('img', { src: m.image, alt: '', loading: 'lazy' }));
    if (m.video) {
      const y = m.video.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{6,20})/);
      if (y) box.append(h('div', { class: 'vid' }, h('iframe', { src: 'https://www.youtube-nocookie.com/embed/' + y[1], allow: 'encrypted-media; picture-in-picture', allowfullscreen: true, loading: 'lazy', title: 'video' })));
      else if (/^https?:\/\/|^\/media\//.test(m.video)) box.append(h('video', { src: m.video, controls: true, preload: 'metadata', playsinline: true }));
    }
    return box.childNodes.length ? box : null;
  }
  function set(q, v, keepTouch) { if (empty(v)) delete A[q.id]; else A[q.id] = v; if (!keepTouch) touched.add(q.id); changed(q); }

  function control(q) {
    const t = q.type, name = 'q_' + q.id;
    const choices = q.choices ? (q.shuffle ? shuffle(q.choices) : q.choices) : [];
    if (['short_text', 'email', 'phone', 'url', 'number'].includes(t)) {
      const type = { email: 'email', phone: 'tel', url: 'url', number: 'number', short_text: 'text' }[t];
      return h('input', { type, id: name, class: 'f-in', placeholder: q.placeholder || (t === 'short_text' ? T('إجابتك', 'Your answer') : ''),
        min: q.min, max: q.max, step: q.step ?? (t === 'number' ? 'any' : null), dir: ['email', 'url', 'phone'].includes(t) ? 'ltr' : null,
        inputmode: t === 'number' ? 'decimal' : null, autocomplete: t === 'email' ? 'email' : t === 'phone' ? 'tel' : 'off',
        oninput: (e) => set(q, t === 'number' ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value) });
    }
    if (t === 'long_text') return h('textarea', { id: name, class: 'f-in', rows: 4, placeholder: q.placeholder || T('إجابتك', 'Your answer'), oninput: (e) => { set(q, e.target.value); grow(e.target); } });
    if (t === 'single' || t === 'multi' || t === 'yesno') {
      const multi = t === 'multi';
      const box = h('div', { class: 'opts' + (t === 'yesno' ? ' yesno' : ''), role: multi ? 'group' : 'radiogroup' });
      const otherIn = h('input', { type: 'text', class: 'f-in other-in', placeholder: T('اكتب إجابتك', 'Write your answer'), 'aria-label': T('أخرى', 'Other'),
        oninput: (e) => { A[q.id + ':other'] = e.target.value; const r = box.querySelector(`input[value="${OTHER}"]`); if (r && !r.checked && e.target.value) { r.checked = true; read(); } } });
      const read = () => {
        const sel = [...box.querySelectorAll('input[type=radio],input[type=checkbox]')].filter((i) => i.checked).map((i) => i.value);
        set(q, multi ? sel : (sel[0] || null));
        otherIn.hidden = !sel.includes(OTHER);
      };
      [...choices, ...(q.other ? [{ id: OTHER, label: T('أخرى', 'Other') }] : [])].forEach((c) => {
        box.append(h('label', { class: 'opt' }, h('input', { type: multi ? 'checkbox' : 'radio', name, value: c.id, onchange: read }), h('span', { class: 'mk' }), h('span', { class: 'lb' }, c.id === OTHER ? c.label : tx(c, 'label'))));
      });
      if (q.other) { otherIn.hidden = true; box.append(otherIn); }
      if (!multi && !q.required) box.append(h('button', { type: 'button', class: 'linkish clear-choice', onclick: () => { box.querySelectorAll('input').forEach((i) => { if (i.type === 'radio') i.checked = false; }); read(); } }, T('إلغاء الاختيار', 'Clear selection')));
      return box;
    }
    if (t === 'dropdown') {
      const otherIn = h('input', { type: 'text', class: 'f-in other-in', hidden: true, placeholder: T('اكتب إجابتك', 'Write your answer'), oninput: (e) => { A[q.id + ':other'] = e.target.value; } });
      const sel = h('select', { id: name, class: 'f-in', onchange: (e) => { set(q, e.target.value || null); otherIn.hidden = e.target.value !== OTHER; } },
        h('option', { value: '' }, T('اختر…', 'Choose…')), ...choices.map((c) => h('option', { value: c.id }, tx(c, 'label'))),
        q.other ? h('option', { value: OTHER }, T('أخرى', 'Other')) : null);
      return h('div', {}, sel, otherIn);
    }
    if (t === 'image_choice') {
      const box = h('div', { class: 'img-opts', role: 'radiogroup' });
      choices.forEach((c) => box.append(h('label', { class: 'img-opt' }, h('input', { type: 'radio', name, value: c.id, onchange: () => set(q, c.id) }),
        c.image ? h('img', { src: c.image, alt: '', loading: 'lazy' }) : h('span', { class: 'img-ph' }, icon('fa-image')), h('span', { class: 'lb' }, tx(c, 'label')))));
      return box;
    }
    if (t === 'scale' || t === 'nps') {
      const lo = t === 'nps' ? 0 : (q.min ?? 1), hi = t === 'nps' ? 10 : (q.max ?? 5);
      const row = h('div', { class: 'scale' + (t === 'nps' ? ' nps' : ''), role: 'radiogroup' });
      for (let v = lo; v <= hi; v++) row.append(h('label', { class: 'sc' + (t === 'nps' ? (v <= 6 ? ' det' : v <= 8 ? ' pas' : ' pro') : '') }, h('input', { type: 'radio', name, value: v, onchange: () => set(q, v) }), h('span', {}, v)));
      return h('div', { class: 'scale-wrap' }, row, h('div', { class: 'scale-labels' }, h('span', {}, tx(q, 'min_label')), h('span', {}, tx(q, 'max_label'))));
    }
    if (t === 'rating') {
      const ic = { star: 'fa-star', heart: 'fa-heart', thumb: 'fa-thumbs-up' }[q.icon];
      const faces = ['fa-face-angry', 'fa-face-frown', 'fa-face-meh', 'fa-face-smile', 'fa-face-laugh-beam'];
      const row = h('div', { class: 'rating ' + (q.icon || 'star'), role: 'radiogroup' });
      const max = q.max || 5;
      const paint = (n) => row.querySelectorAll('label').forEach((l, i) => l.classList.toggle('on', q.icon === 'smile' ? i + 1 === n : i < n));
      for (let v = 1; v <= max; v++) {
        const fi = q.icon === 'smile' ? faces[Math.min(4, Math.round((v - 1) * 4 / Math.max(1, max - 1)))] : ic;
        row.append(h('label', { title: String(v) }, h('input', { type: 'radio', name, value: v, 'aria-label': String(v), onchange: () => { set(q, v); paint(v); } }), icon(fi)));
      }
      return h('div', { class: 'scale-wrap' }, row, (q.min_label || q.max_label) ? h('div', { class: 'scale-labels' }, h('span', {}, tx(q, 'min_label')), h('span', {}, tx(q, 'max_label'))) : null);
    }
    if (t === 'slider') {
      const out = h('output', { class: 'sl-out' }, '—');
      const r = h('input', { type: 'range', id: name, min: q.min ?? 0, max: q.max ?? 100, step: q.step || 1, value: Math.round(((q.min ?? 0) + (q.max ?? 100)) / 2), class: 'untouched',
        oninput: (e) => { e.target.classList.remove('untouched'); out.textContent = e.target.value; set(q, Number(e.target.value)); } });
      return h('div', { class: 'slider' }, r, out, h('div', { class: 'scale-labels' }, h('span', {}, tx(q, 'min_label') || (q.min ?? 0)), h('span', {}, tx(q, 'max_label') || (q.max ?? 100))));
    }
    if (['likert', 'matrix', 'matrix_multi'].includes(t)) {
      const multi = t === 'matrix_multi';
      const val = {};
      const tbl = h('table', { class: 'matrix' }, h('thead', {}, h('tr', {}, h('th', {}), ...(q.cols || []).map((c) => h('th', { scope: 'col' }, tx(c, 'label'))))));
      const tb = h('tbody'); tbl.append(tb);
      (q.rows || []).forEach((r) => {
        tb.append(h('tr', {}, h('th', { scope: 'row' }, tx(r, 'label')), ...(q.cols || []).map((c) => h('td', { 'data-col': tx(c, 'label') },
          h('label', { class: 'mx' }, h('input', { type: multi ? 'checkbox' : 'radio', name: name + '_' + r.id, value: c.id, 'aria-label': tx(r, 'label') + ' — ' + tx(c, 'label'),
            onchange: () => {
              const sel = [...tb.querySelectorAll(`input[name="${name}_${r.id}"]:checked`)].map((i) => i.value);
              if (sel.length) val[r.id] = multi ? sel : sel[0]; else delete val[r.id];
              set(q, Object.assign({}, val));
            } }), h('span', { class: 'mk' }), h('span', { class: 'mx-lb' }, tx(c, 'label')))))));
      });
      return h('div', { class: 'matrix-wrap' }, tbl);
    }
    if (t === 'ranking') {
      const ul = h('ol', { class: 'rank' });
      const order = choices.map((c) => c.id);
      const draw = () => {
        ul.innerHTML = '';
        order.forEach((id, i) => {
          const c = q.choices.find((x) => x.id === id);
          const li = h('li', { draggable: 'true', 'data-id': id }, h('span', { class: 'rk' }, i + 1), h('span', { class: 'lb' }, tx(c, 'label')),
            h('button', { type: 'button', class: 'rk-btn', 'aria-label': T('أعلى', 'Up'), disabled: i === 0, onclick: () => mv(i, -1) }, icon('fa-chevron-up')),
            h('button', { type: 'button', class: 'rk-btn', 'aria-label': T('أسفل', 'Down'), disabled: i === order.length - 1, onclick: () => mv(i, 1) }, icon('fa-chevron-down')));
          li.addEventListener('dragstart', (e) => e.dataTransfer.setData('text/plain', String(i)));
          li.addEventListener('dragover', (e) => e.preventDefault());
          li.addEventListener('drop', (e) => { e.preventDefault(); const f = Number(e.dataTransfer.getData('text/plain')); const [m] = order.splice(f, 1); order.splice(i, 0, m); draw(); set(q, order.slice()); });
          ul.append(li);
        });
      };
      const mv = (i, d) => { [order[i], order[i + d]] = [order[i + d], order[i]]; draw(); set(q, order.slice()); };
      draw();
      return h('div', {}, h('p', { class: 'hint' }, T('رتّب العناصر بالسحب أو بالأسهم (الأول هو الأهم).', 'Order the items by dragging or with the arrows (first is most important).')), ul,
        h('button', { type: 'button', class: 'linkish', onclick: () => set(q, order.slice()) }, T('أوافق على هذا الترتيب', 'Keep this order')));
    }
    if (t === 'constant_sum') {
      const total = q.total || 100, val = {};
      const tot = h('div', { class: 'sum-tot' });
      const upd = () => { const s = Object.values(val).reduce((a, b) => a + b, 0); tot.textContent = T(`المجموع: ${s} من ${total}`, `Total: ${s} of ${total}`); tot.classList.toggle('ok', Math.abs(s - total) < 1e-9); tot.classList.toggle('over', s > total); };
      const box = h('div', { class: 'csum' });
      choices.forEach((c) => box.append(h('label', { class: 'cs-row' }, h('span', { class: 'lb' }, tx(c, 'label')),
        h('input', { type: 'number', min: 0, max: total, step: 'any', class: 'f-in', inputmode: 'decimal', oninput: (e) => { const n = num(e.target.value); if (n === null) delete val[c.id]; else val[c.id] = n; upd(); set(q, Object.assign({}, val)); } }))));
      upd();
      return h('div', {}, box, tot);
    }
    if (t === 'date' || t === 'time' || t === 'datetime') {
      return h('input', { type: t === 'datetime' ? 'datetime-local' : t, id: name, class: 'f-in narrow', dir: 'ltr', oninput: (e) => set(q, e.target.value) });
    }
    if (t === 'file') {
      const acc = { image: 'image/*', pdf: 'application/pdf', media: 'audio/*,video/*', doc: '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,image/*' }[q.accept] || '';
      const list = h('ul', { class: 'file-list' });
      const inp = h('input', { type: 'file', id: name, accept: acc || null, multiple: (q.max_files || 1) > 1, class: 'file-in',
        onchange: (e) => {
          const fs = [...e.target.files].slice(0, q.max_files || 1);
          const big = fs.find((f) => f.size > (q.max_mb || 10) * 1048576);
          if (big) { showErr(q, T(`الملف «${big.name}» أكبر من ${q.max_mb || 10} ميغابايت.`, `"${big.name}" is larger than ${q.max_mb || 10} MB.`)); e.target.value = ''; FILES[q.id] = []; set(q, null); list.innerHTML = ''; return; }
          FILES[q.id] = fs;
          list.innerHTML = '';
          fs.forEach((f) => list.append(h('li', {}, icon('fa-file'), ' ', f.name, h('span', { class: 'muted' }, ` (${Math.ceil(f.size / 1024)} KB)`))));
          set(q, fs.length ? fs.map((f) => ({ name: f.name })) : null);
        } });
      return h('div', { class: 'file-box' }, h('label', { for: name, class: 'file-btn' }, icon('fa-cloud-arrow-up'), ' ',
        (q.max_files || 1) > 1 ? T(`اختر حتى ${q.max_files} ملفات`, `Choose up to ${q.max_files} files`) : T('اختر ملفاً', 'Choose a file')), inp, list,
        h('p', { class: 'hint' }, T(`الحد الأعلى ${q.max_mb || 10} ميغابايت للملف.`, `Up to ${q.max_mb || 10} MB per file.`)));
    }
    if (t === 'signature') {
      const cv = h('canvas', { class: 'sig', width: 600, height: 200, 'aria-label': T('مساحة التوقيع', 'Signature area') });
      const ctx = cv.getContext('2d');
      let down = false, drew = false;
      const pos = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * cv.width / r.width, (e.clientY - r.top) * cv.height / r.height]; };
      ctx.lineWidth = 3; ctx.lineCap = 'round'; ctx.strokeStyle = '#0f2a52';
      cv.addEventListener('pointerdown', (e) => { down = true; cv.setPointerCapture(e.pointerId); const [x, y] = pos(e); ctx.beginPath(); ctx.moveTo(x, y); });
      cv.addEventListener('pointermove', (e) => { if (!down) return; const [x, y] = pos(e); ctx.lineTo(x, y); ctx.stroke(); drew = true; });
      const end = () => { if (!down) return; down = false; if (drew) set(q, cv.toDataURL('image/png')); };
      cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
      return h('div', { class: 'sig-box' }, cv, h('button', { type: 'button', class: 'linkish', onclick: () => { ctx.clearRect(0, 0, cv.width, cv.height); drew = false; set(q, null); } }, T('مسح التوقيع', 'Clear signature')));
    }
    return null;
  }
  function grow(t) { t.style.height = 'auto'; t.style.height = Math.min(600, t.scrollHeight + 2) + 'px'; }

  function qCard(q) {
    if (q.type === 'hidden') {
      const v = params.get(q.param || 'ref');
      if (v) A[q.id] = v.slice(0, 1000);
      return null;
    }
    const isStmt = q.type === 'statement';
    const showNum = S.question_numbers && !isStmt;
    if (!isStmt) qn++;
    const title = tx(q, 'title');
    const card = h('div', { class: 'f-card q' + (isStmt ? ' stmt' : ''), 'data-qid': q.id, id: 'q-' + q.id },
      title || !isStmt ? h(isStmt ? 'h2' : 'div', { class: 'q-title', id: 'qt-' + q.id }, showNum ? h('span', { class: 'qn' }, qn + '.') : null, title,
        q.required ? h('span', { class: 'req', 'aria-label': T('مطلوب', 'required') }, ' *') : null,
        S.quiz && q.quiz && q.quiz.points ? h('span', { class: 'pts' }, q.quiz.points + T(' درجة', ' pts')) : null) : null,
      tx(q, 'help') ? h('div', { class: 'q-help' }, tx(q, 'help')) : null,
      mediaBlock(q.media));
    const c = control(q);
    if (c) { card.append(h('div', { class: 'q-ctl', role: ['single', 'yesno', 'scale', 'nps', 'rating', 'image_choice'].includes(q.type) ? 'group' : null, 'aria-labelledby': 'qt-' + q.id }, c)); }
    card.append(h('div', { class: 'q-err', id: 'qe-' + q.id, role: 'alert', hidden: true }));
    if (q.required) document.getElementById('reqNote').hidden = false;
    QEL[q.id] = card;
    return card;
  }
  PAGES.forEach((p, i) => {
    const pg = h('section', { class: 'page', 'data-page': i, hidden: true });
    if (p.section) pg.append(h('div', { class: 'f-card sec-card' }, h('h2', {}, tx(p.section, 'title')), tx(p.section, 'help') ? h('p', { class: 'q-help' }, tx(p.section, 'help')) : null, mediaBlock(p.section.media)));
    const items = S.shuffle ? shuffle(p.items) : p.items;
    items.forEach((q) => { const el = qCard(q); if (el) pg.append(el); });
    root.append(pg);
  });
  if (EN && S.bilingual && D.title_en) { document.getElementById('fTitle').textContent = D.title_en; document.title = D.title_en; }

  // ── التنقّل ────────────────────────────────────────────────────────────
  let cur = 0;
  const hist = [];
  const backBtn = document.getElementById('backBtn'), nextBtn = document.getElementById('nextBtn'), submitBtn = document.getElementById('submitBtn');
  const pageEls = [...root.querySelectorAll('.page')];
  function show(i, scroll) {
    cur = i;
    pageEls.forEach((p, k) => { p.hidden = k !== i; });
    refresh();
    if (scroll) { const top = document.querySelector('.f-head'); window.scrollTo({ top: Math.max(0, (pageEls[i].offsetTop || 0) - 20), behavior: 'smooth' }); if (!pageEls[i].offsetTop && top) top.scrollIntoView(); }
  }
  function refresh() {
    const w = walk(A);
    Object.entries(QEL).forEach(([id, el]) => { el.hidden = !w.shown.has(id); });
    const nxt = w.nextOf[cur] ?? -1;
    nextBtn.hidden = nxt < 0;
    submitBtn.hidden = nxt >= 0;
    backBtn.hidden = !hist.length;
    const total = w.visited.length + (w.visited.includes(cur) ? 0 : 1);
    const pos = Math.max(1, w.visited.indexOf(cur) + 1);
    const pi = document.getElementById('pageInfo');
    pi.textContent = PAGES.length > 1 ? T(`الصفحة ${pos} من ${Math.max(pos, total)}`, `Page ${pos} of ${Math.max(pos, total)}`) : '';
    if (S.progress !== false && PAGES.length > 1) {
      document.getElementById('progress').hidden = false;
      document.getElementById('progBar').style.width = Math.round(100 * (pos - 1) / Math.max(1, total)) + '%';
    }
    return w;
  }
  function showErr(q, msg) {
    const e = document.getElementById('qe-' + q.id); if (!e) return;
    e.textContent = msg; e.hidden = !msg; QEL[q.id].classList.toggle('has-err', !!msg);
  }
  function clientCheck(q) {
    const v = A[q.id], t = q.type;
    if (empty(v)) {
      if (!q.required) return '';
      return t === 'ranking' ? T('رتّب العناصر أو اضغط «أوافق على هذا الترتيب».', 'Order the items or press "Keep this order".') : T('هذا السؤال مطلوب.', 'This question is required.');
    }
    if (t === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) return T('اكتب بريداً إلكترونياً صحيحاً.', 'Enter a valid email address.');
    if (t === 'phone' && !/^\+?[0-9\s\-()]{6,20}$/.test(v)) return T('اكتب رقم هاتف صحيحاً.', 'Enter a valid phone number.');
    if (t === 'number') { if (q.min !== undefined && v < q.min) return T(`أقل قيمة ${q.min}.`, `The minimum is ${q.min}.`); if (q.max !== undefined && v > q.max) return T(`أعلى قيمة ${q.max}.`, `The maximum is ${q.max}.`); }
    if (t === 'multi') { if (q.min_select && v.length < q.min_select) return T(`اختر ${q.min_select} على الأقل.`, `Choose at least ${q.min_select}.`); if (q.max_select && v.length > q.max_select) return T(`اختر ${q.max_select} على الأكثر.`, `Choose at most ${q.max_select}.`); }
    if (['likert', 'matrix', 'matrix_multi'].includes(t) && q.required && Object.keys(v).length < (q.rows || []).length) return T('أجب عن كل صفوف الشبكة.', 'Answer every row of the grid.');
    if (t === 'constant_sum') { const s = Object.values(v).reduce((a, b) => a + b, 0); if (Math.abs(s - (q.total || 100)) > 1e-9) return T(`يجب أن يكون المجموع ${q.total || 100}.`, `The total must be ${q.total || 100}.`); }
    const val = q.validation;
    if (val && typeof v === 'string') {
      if (val.kind === 'length' && ((val.min && v.length < val.min) || (val.max && v.length > val.max))) return val.message || T('طول الإجابة غير مناسب.', 'The answer length is not allowed.');
      if (val.kind === 'regex' && val.pattern) { try { if (!new RegExp('^(?:' + val.pattern + ')$').test(v)) return val.message || T('الإجابة لا تطابق الصيغة المطلوبة.', 'The answer does not match the required format.'); } catch (_) { /* صيغة غير صالحة */ } }
    }
    return '';
  }
  function checkPage(i, w) {
    let first = null;
    PAGES[i].items.forEach((q) => {
      if (!w.shown.has(q.id) || NO_ANSWER.includes(q.type) || q.type === 'hidden') return;
      const m = clientCheck(q); showErr(q, m);
      if (m && !first) first = q;
    });
    if (first) { QEL[first.id].scrollIntoView({ behavior: 'smooth', block: 'center' }); const f = QEL[first.id].querySelector('input,select,textarea'); if (f) f.focus({ preventScroll: true }); }
    return !first;
  }
  nextBtn.addEventListener('click', () => {
    const w = refresh();
    if (!checkPage(cur, w)) return;
    const n = w.nextOf[cur];
    if (n >= 0) { hist.push(cur); show(n, true); saveDraft(); }
  });
  backBtn.addEventListener('click', () => { if (hist.length) show(hist.pop(), true); });

  let started = false;
  function changed(q) {
    if (!started) { started = true; try { navigator.sendBeacon && navigator.sendBeacon(D.start_url + (D.preview ? '?preview=1' : '')); } catch (_) { /* لا شيء */ } }
    if (q && QEL[q.id] && QEL[q.id].classList.contains('has-err')) showErr(q, clientCheck(q));
    refresh(); saveDraftSoon();
  }

  // ── المسودة في الجهاز ──────────────────────────────────────────────────
  let dt;
  function saveDraftSoon() { if (!S.autosave) return; clearTimeout(dt); dt = setTimeout(saveDraft, 600); }
  function saveDraft() {
    if (!S.autosave) return;
    const keep = {};
    Object.entries(A).forEach(([k, v]) => { const q = QS.find((x) => x.id === k.split(':')[0]); if (q && !['file', 'signature', 'hidden'].includes(q.type)) keep[k] = v; });
    try { localStorage.setItem(draftKey, JSON.stringify({ a: keep, at: Date.now() })); } catch (_) { /* التخزين غير متاح */ }
  }
  function restoreDraft() {
    if (!S.autosave) return;
    document.getElementById('draftNote').hidden = false;
    let d; try { d = JSON.parse(localStorage.getItem(draftKey) || 'null'); } catch (_) { d = null; }
    if (!d || !d.a) return;
    Object.entries(d.a).forEach(([k, v]) => {
      const qid = k.split(':')[0], q = QS.find((x) => x.id === qid), el = QEL[qid];
      if (!q || !el) return;
      if (k.endsWith(':other')) { const o = el.querySelector('.other-in'); if (o) { o.value = v; o.hidden = false; } A[k] = v; return; }
      A[k] = v;
      const t = q.type;
      if (['short_text', 'email', 'phone', 'url', 'number', 'long_text', 'date', 'time', 'datetime', 'dropdown', 'slider'].includes(t)) {
        const i = el.querySelector('.f-in, input[type=range]'); if (i) { i.value = v; i.classList.remove('untouched'); const o = el.querySelector('.sl-out'); if (o) o.textContent = v; }
        if (t === 'dropdown' && v === OTHER) { const o = el.querySelector('.other-in'); if (o) o.hidden = false; }
      } else if (['single', 'yesno', 'image_choice', 'scale', 'nps', 'rating'].includes(t)) {
        const i = el.querySelector(`input[value="${CSS.escape(String(v))}"]`); if (i) i.checked = true;
        if (t === 'rating') el.querySelectorAll('.rating label').forEach((l, k2) => l.classList.toggle('on', q.icon === 'smile' ? k2 + 1 === v : k2 < v));
        if (v === OTHER) { const o = el.querySelector('.other-in'); if (o) o.hidden = false; }
      } else if (t === 'multi') {
        v.forEach((x) => { const i = el.querySelector(`input[value="${CSS.escape(String(x))}"]`); if (i) i.checked = true; });
        if (v.includes(OTHER)) { const o = el.querySelector('.other-in'); if (o) o.hidden = false; }
      } else if (['likert', 'matrix', 'matrix_multi'].includes(t)) {
        Object.entries(v).forEach(([r, c]) => [].concat(c).forEach((x) => { const i = el.querySelector(`input[name="q_${q.id}_${r}"][value="${CSS.escape(String(x))}"]`); if (i) i.checked = true; }));
      } else if (t === 'constant_sum') {
        const ins = el.querySelectorAll('.cs-row input'); (q.shuffle ? [] : q.choices).forEach((c, k2) => { if (ins[k2] && v[c.id] !== undefined) { ins[k2].value = v[c.id]; ins[k2].dispatchEvent(new Event('input')); } });
      }
    });
  }
  document.getElementById('clearDraft').addEventListener('click', () => { try { localStorage.removeItem(draftKey); } catch (_) { /* لا شيء */ } location.reload(); });

  // ── المهلة ─────────────────────────────────────────────────────────────
  if (S.time_limit > 0) {
    const tm = document.getElementById('timer'); tm.hidden = false;
    const key = 'ftime_' + D.slug;
    let st; try { st = Number(sessionStorage.getItem(key)) || Date.now(); sessionStorage.setItem(key, st); } catch (_) { st = Date.now(); }
    const end = st + S.time_limit * 60000;
    const tick = () => {
      const left = Math.max(0, end - Date.now());
      const m = Math.floor(left / 60000), s = Math.floor(left / 1000) % 60;
      tm.innerHTML = ''; tm.append(icon('fa-hourglass-half'), ' ', T('الوقت المتبقي: ', 'Time left: '), h('b', { dir: 'ltr' }, `${m}:${String(s).padStart(2, '0')}`));
      tm.classList.toggle('low', left < 60000);
      if (left <= 0) { clearInterval(iv); send(true); }
    };
    const iv = setInterval(tick, 1000); tick();
  }

  // ── الإرسال ────────────────────────────────────────────────────────────
  const errBox = document.getElementById('formErr');
  let sending = false;
  async function send(timeout) {
    if (sending) return;
    const w = refresh();
    if (!timeout) { for (const i of w.visited) { if (!checkPage(i, w)) { if (i !== cur) { hist.push(cur); show(i, true); checkPage(i, w); } return; } } }
    sending = true; submitBtn.disabled = true;
    submitBtn.innerHTML = ''; submitBtn.append(icon('fa-spinner fa-spin'), ' ', T('جارٍ الإرسال…', 'Sending…'));
    const answers = {};
    Object.entries(A).forEach(([k, v]) => { if (w.shown.has(k.split(':')[0])) answers[k] = v; });
    const fd = new FormData();
    fd.append('payload', JSON.stringify({ answers, parent: D.parent, hp: document.getElementById('hp').value, timeout: !!timeout,
      meta: { screen: `${screen.width}x${screen.height}`, viewport: `${innerWidth}x${innerHeight}`, tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || ''),
        lang: navigator.language || '', platform: (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '',
        referrer: document.referrer.slice(0, 200), touch: ('ontouchstart' in window) ? '1' : '0', source: params.get('utm_source') || params.get('src') || '' } }));
    Object.entries(FILES).forEach(([qid, fs]) => { if (w.shown.has(qid)) fs.forEach((f) => fd.append('file__' + qid, f, f.name)); });
    try {
      const r = await fetch(D.submit_url + (D.preview ? '?preview=1' : ''), { method: 'POST', body: fd, credentials: 'same-origin' });
      const d = await r.json().catch(() => ({ ok: false, error: T('تعذّر الاتصال بالخادم.', 'Could not reach the server.') }));
      if (d.ok) {
        try { localStorage.removeItem(draftKey); sessionStorage.removeItem('ftime_' + D.slug); } catch (_) { /* لا شيء */ }
        location.href = d.redirect; return;
      }
      if (d.redirect && r.status === 403) { location.href = d.redirect; return; }
      errBox.textContent = d.error || T('تعذّر الإرسال.', 'Could not submit.'); errBox.hidden = false;
      if (d.errors) {
        let firstPage = null;
        Object.entries(d.errors).forEach(([qid, msg]) => { const q = QS.find((x) => x.id === qid); if (q) { showErr(q, msg); const pi = PAGES.findIndex((p) => p.items.includes(q)); if (firstPage === null || pi < firstPage) firstPage = pi; } });
        if (firstPage !== null && firstPage !== cur) { hist.push(cur); show(firstPage, true); }
      }
    } catch (e) {
      errBox.textContent = T('انقطع الاتصال. تأكد من الإنترنت ثم أعد الإرسال؛ إجاباتك ما زالت هنا.', 'The connection dropped. Check the internet and submit again; your answers are still here.'); errBox.hidden = false;
    }
    sending = false; submitBtn.disabled = false; submitBtn.innerHTML = ''; submitBtn.append(icon('fa-paper-plane'), ' ', T('إرسال', 'Submit'));
  }
  document.getElementById('fillForm').addEventListener('submit', (e) => { e.preventDefault(); send(false); });
  document.getElementById('fillForm').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'submit') { e.preventDefault(); if (!nextBtn.hidden) nextBtn.click(); }
  });

  restoreDraft();
  show(0, false);
})();
