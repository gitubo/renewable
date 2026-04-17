import { getCompanies, getRegions, autocompleteCompanies, toggleStar, createCompany } from '../api.js';
import { esc, companyRow, companyTableHeader, attachRowHandlers } from '../row-helpers.js';

let state = { search: '', region: '', crm_status: '', starred: false, sort_by: 'name', sort_order: 'asc', page: 1 };
let regions = [];

export async function renderCompanies() {
  const app = document.getElementById('app');
  if (!regions.length) {
    try { regions = await getRegions(); } catch { regions = []; }
  }
  app.innerHTML = `
    <div class="grid grid-cols-12 gap-2 mb-4 sticky top-[56px] z-10">
      <section id="co-filters" class="col-span-11 bg-surface-container-low rounded-xl p-2"></section>
      <div class="col-span-1 flex items-center justify-center">
        <button id="btn-new-company" class="w-full bg-primary text-on-primary rounded-xl text-[10px] font-bold uppercase tracking-wider hover:bg-primary/90 transition-colors flex items-center justify-center py-1.5">Add</button>
      </div>
    </div>
    <div id="co-table" class="bg-surface-container-lowest rounded-xl overflow-hidden shadow-sm"><p class="p-4 text-secondary">Loading...</p></div>
    <div id="co-pagination" class="mt-2 flex justify-center"></div>
    <!-- New Company Modal -->
    <div id="modal-new" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl border border-outline-variant/20 p-5 w-full max-w-3xl mx-4">
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-sm font-bold font-headline uppercase tracking-wider text-primary">New Company</h2>
          <button id="modal-close" class="text-on-surface-variant hover:text-error"><span class="material-symbols-outlined">close</span></button>
        </div>
        <div class="grid grid-cols-12 gap-3">
          <label class="col-span-5 text-[10px] font-bold text-on-surface-variant uppercase">Name *<input id="nc-name" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-3 text-[10px] font-bold text-on-surface-variant uppercase">VAT Number *<input id="nc-vat" placeholder="12345678901" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">ATECO<input id="nc-ateco" placeholder="35.11" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">Score<select id="nc-score" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"><option value="">—</option>${[0,1,2,3,4,5,6,7,8,9,10].map(n=>'<option value="'+n+'">'+n+'</option>').join('')}</select></label>
          <label class="col-span-5 text-[10px] font-bold text-on-surface-variant uppercase">Address<input id="nc-address" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-3 text-[10px] font-bold text-on-surface-variant uppercase">City<input id="nc-city" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">County<input id="nc-county" placeholder="MI" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">Region<input id="nc-region" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-6 text-[10px] font-bold text-on-surface-variant uppercase">Website<input id="nc-web" placeholder="https://..." class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
          <label class="col-span-6 text-[10px] font-bold text-on-surface-variant uppercase">Website Notes<input id="nc-notes" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        </div>
        <div class="flex items-center gap-3 mt-4 justify-end">
          <span id="nc-feedback" class="text-xs mr-auto"></span>
          <button id="modal-cancel" class="text-on-surface-variant text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-lg hover:bg-surface-container-high transition-colors">Cancel</button>
          <button id="btn-create" class="bg-primary text-on-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-lg hover:bg-primary/90 transition-colors">Add</button>
        </div>
      </div>
    </div>`;
  renderFilters();
  await loadData();
}

function renderFilters() {
  const regionOpts = regions.map(r => `<option value="${esc(r)}" ${state.region===r?'selected':''}>${esc(r)}</option>`).join('');
  document.getElementById('co-filters').innerHTML = `
    <div class="flex flex-wrap items-center gap-3">
      <div class="relative flex-1 min-w-[240px]">
        <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-lg">search</span>
        <input id="f-search" type="text" value="${state.search}" placeholder="Search by name, VAT or city..." autocomplete="off" class="w-full bg-surface-bright border-none rounded-lg py-1.5 pl-10 pr-4 text-sm focus:ring-1 focus:ring-primary-fixed-dim placeholder:text-outline" />
        <div id="ac-dropdown" class="absolute left-0 right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-outline-variant/20 z-50 hidden max-h-60 overflow-y-auto"></div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-tighter">Region</span>
        <select id="f-region" class="bg-surface-bright border-none rounded-lg py-1.5 px-3 text-sm focus:ring-1 focus:ring-primary-fixed-dim min-w-[160px]">
          <option value="">All</option>
          ${regionOpts}
        </select>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-tighter">Status</span>
        <select id="f-crm" class="bg-surface-bright border-none rounded-lg py-1.5 px-3 text-sm focus:ring-1 focus:ring-primary-fixed-dim min-w-[120px]">
          <option value="">All</option>
          ${['new','contacted','interested','negotiating','not_interested','customer'].map(s => `<option value="${s}" ${state.crm_status===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>
      <div class="flex items-center gap-2 ml-auto">
        <button id="btn-starred" class="${state.starred ? 'bg-amber-100 text-amber-600' : 'bg-surface-container-highest text-on-surface-variant'} p-1.5 rounded-lg hover:bg-surface-variant transition-colors" title="Filter starred"><span class="material-symbols-outlined">${state.starred ? 'star' : 'star_border'}</span></button>
      </div>
    </div>`;

  document.getElementById('btn-starred').addEventListener('click', () => {
    state.starred = !state.starred;
    state.page = 1;
    loadData();
    renderFilters();
  });
  // New company modal
  document.getElementById('btn-new-company').addEventListener('click', () => {
    document.getElementById('modal-new').classList.remove('hidden');
  });
  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal-new').classList.add('hidden');
  });
  document.getElementById('modal-cancel').addEventListener('click', () => {
    document.getElementById('modal-new').classList.add('hidden');
  });
  document.getElementById('modal-new').addEventListener('click', (e) => {
    if (e.target.id === 'modal-new') document.getElementById('modal-new').classList.add('hidden');
  });
  document.getElementById('btn-create').addEventListener('click', async () => {
    const fb = document.getElementById('nc-feedback');
    const vat = document.getElementById('nc-vat').value.trim();
    const name = document.getElementById('nc-name').value.trim();
    if (!vat || !name) { fb.innerHTML = '<span class="text-error">Name and VAT are required</span>'; return; }
    fb.innerHTML = '<span class="text-on-surface-variant animate-pulse">Creating...</span>';
    try {
      const data = { vat_number: vat, name };
      const v = (id) => document.getElementById(id).value.trim();
      if (v('nc-ateco')) data.ateco_code = v('nc-ateco');
      if (v('nc-region')) data.region = v('nc-region');
      if (v('nc-city')) data.city = v('nc-city');
      if (v('nc-county')) data.county = v('nc-county');
      if (v('nc-address')) data.address = v('nc-address');
      if (v('nc-web')) data.website_url = v('nc-web');
      if (v('nc-notes')) data.notes = v('nc-notes');
      const score = document.getElementById('nc-score').value;
      if (score !== '') data.score = parseInt(score);
      const r = await createCompany(data);
      document.getElementById('modal-new').classList.add('hidden');
      location.hash = '#/company/' + r.id;
    } catch (err) { fb.innerHTML = `<span class="text-error">${esc(err.message)}</span>`; }
  });
  document.getElementById('f-region').addEventListener('change', applyFilters);
  document.getElementById('f-crm').addEventListener('change', applyFilters);
  document.getElementById('f-search').addEventListener('keydown', e => { if (e.key === 'Enter') { hideAc(); applyFilters(); } });

  // Autocomplete
  let acTimer = null;
  const searchInput = document.getElementById('f-search');
  const acDrop = document.getElementById('ac-dropdown');

  searchInput.addEventListener('input', () => {
    clearTimeout(acTimer);
    const q = searchInput.value.trim();
    if (q.length < 2) { hideAc(); return; }
    acTimer = setTimeout(async () => {
      try {
        const results = await autocompleteCompanies(q);
        if (!results.length) { hideAc(); return; }
        acDrop.innerHTML = results.map(r =>
          `<div class="ac-item px-3 py-2 hover:bg-surface-container-low cursor-pointer text-sm" data-id="${r.id}" data-name="${esc(r.name)}">
            <div class="font-semibold text-primary">${esc(r.name)}</div>
            <div class="text-[10px] text-outline">P.IVA: ${esc(r.vat_number)}</div>
          </div>`
        ).join('');
        acDrop.classList.remove('hidden');
        acDrop.querySelectorAll('.ac-item').forEach(item => item.addEventListener('mousedown', (e) => {
          e.preventDefault();
          location.hash = '#/company/' + item.dataset.id;
        }));
      } catch { hideAc(); }
    }, 300);
  });

  searchInput.addEventListener('blur', () => setTimeout(hideAc, 200));
  function hideAc() { acDrop.classList.add('hidden'); }
}

function applyFilters() {
  state.search = document.getElementById('f-search').value;
  state.region = document.getElementById('f-region').value;
  state.crm_status = document.getElementById('f-crm').value;
  state.page = 1;
  loadData();
}

async function loadData() {
  try {
    const params = {};
    if (state.search) params.search = state.search;
    if (state.region) params.region = state.region;
    if (state.crm_status) params.crm_status = state.crm_status;
    if (state.starred) params.starred = true;
    params.sort_by = state.sort_by; params.sort_order = state.sort_order;
    params.page = state.page; params.page_size = 20;
    const data = await getCompanies(params);
    renderTable(data); renderPagination(data);
  } catch (err) { document.getElementById('co-table').innerHTML = `<p class="p-4 text-error">${esc(err.message)}</p>`; }
}

function renderTable(data) {
  const el = document.getElementById('co-table');
  if (!data.results.length) { el.innerHTML = '<p class="p-4 text-secondary">No companies found.</p>'; return; }

  // Map API fields to unified row format
  const rows = data.results.map(c => companyRow({
    ...c,
    score: c.relevance_score != null ? c.relevance_score : 0,
    confidence: c.relevance_confidence || 0,
    data_count: c.data_count || 0,
  })).join('');

  const si = (col) => state.sort_by !== col ? '' : state.sort_order === 'asc' ? ' ▲' : ' ▼';

  el.innerHTML = `<table class="w-full text-left border-collapse">
    <thead class="bg-surface-container-low"><tr>
      <th class="px-4 py-2 w-10"></th>
      <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer co-sort" data-col="name">Company${si('name')}</th>
      <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer co-sort" data-col="city">Location${si('city')}</th>
      <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer co-sort" data-col="score">Score${si('score')}</th>
      <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant text-center cursor-pointer co-sort" data-col="data_count">Intel${si('data_count')}</th>
      <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer co-sort" data-col="crm_status">Status${si('crm_status')}</th>
    </tr></thead>
    <tbody class="divide-y divide-surface-variant/30">${rows}</tbody>
  </table>
  <div class="px-4 py-2 bg-surface-container-low flex justify-between items-center border-t border-surface-variant/20">
    <p class="text-[10px] font-semibold text-on-surface-variant uppercase tracking-widest">Showing ${data.results.length} of ${data.total} companies</p>
  </div>`;

  attachRowHandlers(el, toggleStar, () => loadData());

  // Column sorting
  el.querySelectorAll('.co-sort').forEach(th => th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (state.sort_by === col) {
      if (state.sort_order === 'asc') state.sort_order = 'desc';
      else { state.sort_by = 'name'; state.sort_order = 'asc'; }
    } else {
      state.sort_by = col;
      state.sort_order = col === 'name' || col === 'city' ? 'asc' : 'desc';
    }
    state.page = 1;
    loadData();
  }));
}

function renderPagination(data) {
  const el = document.getElementById('co-pagination');
  const tp = Math.max(1, Math.ceil(data.total / data.page_size));
  if (tp <= 1) { el.innerHTML = ''; return; }
  let h = '';
  if (data.page > 1) h += `<button class="pg w-6 h-6 flex items-center justify-center rounded bg-surface-bright text-primary border border-surface-variant hover:bg-surface-container-high" data-p="${data.page-1}"><span class="material-symbols-outlined text-sm">chevron_left</span></button>`;
  h += `<span class="w-6 h-6 flex items-center justify-center rounded bg-primary text-on-primary text-[10px] font-bold">${data.page}</span>`;
  if (data.page < tp) h += `<button class="pg w-6 h-6 flex items-center justify-center rounded bg-surface-bright text-primary border border-surface-variant hover:bg-surface-container-high" data-p="${data.page+1}"><span class="material-symbols-outlined text-sm">chevron_right</span></button>`;
  el.innerHTML = `<div class="flex gap-1">${h}</div>`;
  el.querySelectorAll('.pg').forEach(b => b.addEventListener('click', () => { state.page = +b.dataset.p; loadData(); }));
}
