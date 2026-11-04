/* <table data-table>: رأس ثابت، وبحث عام فوق الجدول، وتصفية تحت كل عمود data-filter="text|select"، وترتيب بالضغط
   على العنوان (data-sort="num" للأرقام، data-nosort لإيقافه)، و<td data-value> قيمة الترتيب والتصفية، وتصدير الصفوف
   الظاهرة إلى ملف يفتحه Excel. الصفوف المخفية بالتصفية لا يشملها «تحديد الكل». */
(function () {
  'use strict';
  const AR = document.documentElement.lang !== 'en';
  const norm = (v) => (window.normText ? window.normText(v) : String(v || '').toLowerCase().trim());
  const val = (td) => (td ? (td.hasAttribute('data-value') ? td.getAttribute('data-value') : td.textContent.trim()) : '');
  function setup(table) {
    const head = table.tHead && table.tHead.rows[0], body = table.tBodies[0];
    if (!head || !body) return;
    const cols = [...head.cells], filters = [];
    table.classList.add('dt');
    // شريط الأدوات: بحث في كل الأعمدة + تصدير
    let q = null;
    if (body.rows.length > 1 && !table.hasAttribute('data-notools')) {
      const tools = document.createElement('div');
      tools.className = 'dt-tools';
      q = document.createElement('input');
      q.type = 'search';
      q.placeholder = AR ? 'بحث في الجدول…' : 'Search the table…';
      q.setAttribute('aria-label', AR ? 'بحث في الجدول' : 'Search the table');
      q.addEventListener('input', apply);
      const count = document.createElement('span');
      count.className = 'dt-count';
      const ex = document.createElement('button');
      ex.type = 'button';
      ex.className = 'sm ghost dt-export';
      ex.innerHTML = '<i class="fa-solid fa-file-excel" aria-hidden="true"></i> ' + (AR ? 'تصدير إلى Excel' : 'Export to Excel');
      ex.addEventListener('click', exportRows);
      tools.append(q, count, ex);
      const anchor = table.closest('.dt-wrap') || table;
      anchor.parentNode.insertBefore(tools, anchor);
      table.dtCount = count;
    }
    if (cols.some((th) => th.dataset.filter)) {
      const fr = table.tHead.insertRow(-1);
      fr.className = 'dt-filter';
      cols.forEach((th, i) => {
        const cell = document.createElement('th');
        fr.appendChild(cell);
        if (!th.dataset.filter) return;
        let el;
        if (th.dataset.filter === 'select') {
          el = document.createElement('select');
          el.add(new Option(AR ? 'الكل' : 'All', ''));
          [...new Set([...body.rows].map((r) => val(r.cells[i])).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ar'))
            .forEach((v) => el.add(new Option(v, v)));
        } else {
          el = document.createElement('input');
          el.type = 'search';
          el.placeholder = AR ? 'تصفية…' : 'Filter…';
        }
        el.setAttribute('aria-label', (AR ? 'تصفية: ' : 'Filter: ') + th.textContent.trim());
        el.addEventListener('input', apply);
        cell.appendChild(el);
        filters[i] = el;
      });
    }
    let sc = -1, dir = 1;
    cols.forEach((th, i) => {
      if (th.hasAttribute('data-nosort') || th.querySelector('input')) return;
      th.classList.add('dt-sort');
      th.tabIndex = 0;
      th.setAttribute('aria-sort', 'none');
      const go = () => {
        dir = sc === i ? -dir : 1; sc = i;
        cols.forEach((c) => { c.classList.remove('asc', 'desc'); if (c.hasAttribute('aria-sort')) c.setAttribute('aria-sort', 'none'); });
        th.classList.add(dir > 0 ? 'asc' : 'desc');
        th.setAttribute('aria-sort', dir > 0 ? 'ascending' : 'descending');
        const num = th.dataset.sort === 'num';
        [...body.rows].sort((a, b) => {
          const x = val(a.cells[i]), y = val(b.cells[i]);
          return (num ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : x.localeCompare(y, 'ar', { numeric: true })) * dir;
        }).forEach((r) => body.appendChild(r));
      };
      th.addEventListener('click', go);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    });
    function apply() {
      const all = q && q.value ? norm(q.value) : '';
      let shown = 0;
      [...body.rows].forEach((tr) => {
        const ok = filters.every((el, i) => !el || !el.value ||
          (el.tagName === 'SELECT' ? val(tr.cells[i]) === el.value : norm(val(tr.cells[i])).includes(norm(el.value))))
          && (!all || norm(tr.textContent).includes(all));
        tr.hidden = !ok;
        if (ok) shown++;
      });
      if (table.dtCount) table.dtCount.textContent = (all || filters.some((f) => f && f.value)) ? (AR ? `الظاهر: ${shown} من ${body.rows.length}` : `Showing ${shown} of ${body.rows.length}`) : '';
      document.querySelectorAll('.bulk-bar').forEach((b) => window.bulkRefresh && window.bulkRefresh(b.dataset.bulk));
    }
    function exportRows() {
      const keep = cols.map((th) => !(th.classList.contains('chk') || th.classList.contains('act')));
      const cell = (s) => '"' + String(s).replace(/\s+/g, ' ').trim().replace(/"/g, '""') + '"';
      const lines = [cols.filter((_, i) => keep[i]).map((th) => cell(th.textContent)).join(',')];
      [...body.rows].filter((r) => !r.hidden).forEach((r) => {
        lines.push([...r.cells].filter((_, i) => keep[i]).map((td) => cell(td.textContent)).join(','));
      });
      const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (document.title.split('·')[0].trim() || 'table').replace(/[\\/:*?"<>|]+/g, '-') + '.csv';
      document.body.append(a); a.click(); a.remove();
    }
    table.dtApply = apply;
  }
  const init = () => document.querySelectorAll('table[data-table]').forEach(setup);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
