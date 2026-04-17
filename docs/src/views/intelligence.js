import { getIntelligenceStats, getIntelligenceCompanies, toggleStar } from '../api.js';
import { esc, companyRow, companyTableHeader, attachRowHandlers, scoreColor } from '../row-helpers.js';

let stats = null;
let companies = null;
let filterSource = null;
let filterDataCount = null; // { min, max } or exact number
let filterScore = null; // { min, max }
let sortBy = 'score';
let sortOrder = 'desc';
let currentPage = 1;
let totalResults = 0;
const PAGE_SIZE = 20;

export async function renderIntelligence() {
  const app = document.getElementById('app');

  if (!stats) {
    app.innerHTML = '<p class="text-secondary">Loading...</p>';
    try { stats = await getIntelligenceStats(); } catch (err) { app.innerHTML = `<p class="text-error">${esc(err.message)}</p>`; return; }
  }

  const params = { sort_by: sortBy, sort_order: sortOrder, page: currentPage, page_size: PAGE_SIZE };
  if (filterSource) params.source = filterSource;
  if (filterDataCount) {
    if (filterDataCount.min != null) params.min_data_count = filterDataCount.min;
    if (filterDataCount.max != null) params.max_data_count = filterDataCount.max;
  }
  if (filterScore) {
    if (filterScore.min != null) params.min_score = filterScore.min;
    if (filterScore.max != null) params.max_score = filterScore.max;
  }
  try {
    const data = await getIntelligenceCompanies(params);
    companies = data.results || data;
    totalResults = data.total || companies.length;
  } catch { companies = []; totalResults = 0; }

  render(app);
}

function render(app) {
  const d = stats;
  const covPct = d.pct_coverage || 0;
  const totalCompanies = d.total || 1;
  const withData = d.with_data || 1;

  // Coverage breakdown rows (clickable)
  const breakdownRows = (d.by_row_count || []).slice().reverse().map(r => {
    const pct = (r.companies / withData * 100).toFixed(1);
    const active = filterDataCount && filterDataCount.min === r.rows && filterDataCount.max === r.rows;
    const dim = filterDataCount && !active ? 'opacity-40' : '';
    return `<tr class="cursor-pointer data-filter transition-all hover:bg-surface-container ${active?'bg-primary-fixed/20':''} ${dim}" data-rows="${r.rows}">
      <td class="px-3 py-1.5 text-[11px] font-bold uppercase">${r.rows}</td>
      <td class="px-3 py-1.5 text-[11px] text-right font-mono">${r.companies}</td>
      <td class="px-3 py-1.5 text-[11px] text-right font-mono">${pct}%</td>
    </tr>`;
  }).join('');

  // Score breakdown rows (clickable)
  const scoreRows = (d.score_breakdown || []).map(r => {
    const pct = d.scored_total ? (r.companies / d.scored_total * 100).toFixed(1) : '0.0';
    const scoreRange = r.label === '9+' ? {min:9,max:10} : r.label === '<6' ? {min:0,max:5} : {min:parseInt(r.label),max:parseInt(r.label)};
    const active = filterScore && filterScore.min === scoreRange.min && filterScore.max === scoreRange.max;
    const dim = filterScore && !active ? 'opacity-40' : '';
    return `<tr class="cursor-pointer score-filter transition-all hover:bg-surface-container ${active?'bg-primary-fixed/20':''} ${dim}" data-min="${scoreRange.min}" data-max="${scoreRange.max}">
      <td class="px-3 py-1.5 text-[11px] font-bold uppercase">${r.label}</td>
      <td class="px-3 py-1.5 text-[11px] text-right font-mono">${r.companies}</td>
      <td class="px-3 py-1.5 text-[11px] text-right font-mono">${pct}%</td>
    </tr>`;
  }).join('');

  // Source rows (clickable)
  const sourceRows = (d.by_source || []).map(s => {
    const covPctSrc = (s.count / totalCompanies * 100).toFixed(1);
    const active = filterSource === s.source;
    const dim = filterSource && !active ? 'opacity-40' : '';
    return `<tr class="cursor-pointer source-filter transition-all hover:bg-surface-container ${active?'bg-primary-fixed/20':''} ${dim}" data-source="${esc(s.source)}">
      <td class="px-3 py-1.5 text-[11px] font-bold uppercase">${esc(s.source)}</td>
      <td class="px-3 py-1.5 text-[11px] text-right font-mono">${s.count}</td>
      <td class="px-3 py-1.5 text-[11px] text-right font-mono">${covPctSrc}%</td>
    </tr>`;
  }).join('');

  const si = (col) => sortBy !== col ? '' : sortOrder === 'asc' ? ' ▲' : ' ▼';
  const tableRows = (companies || []).map(c => companyRow(c)).join('');

  // Active filter badges
  const badges = [];
  if (filterSource) badges.push(`<span class="filter-badge text-[10px] font-bold text-primary bg-primary-fixed/30 px-2 py-0.5 rounded cursor-pointer" data-clear="source">${filterSource} ✕</span>`);
  if (filterDataCount) badges.push(`<span class="filter-badge text-[10px] font-bold text-primary bg-primary-fixed/30 px-2 py-0.5 rounded cursor-pointer" data-clear="data">${filterDataCount.min === filterDataCount.max ? filterDataCount.min + ' records' : filterDataCount.min + '-' + filterDataCount.max + ' records'} ✕</span>`);
  if (filterScore) badges.push(`<span class="filter-badge text-[10px] font-bold text-primary bg-primary-fixed/30 px-2 py-0.5 rounded cursor-pointer" data-clear="score">score ${filterScore.min}-${filterScore.max} ✕</span>`);

  app.innerHTML = `
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-3">
      <!-- Left sidebar: cards stacked vertically -->
      <div class="lg:col-span-3 flex flex-col gap-3">
        <!-- Overall Coverage -->
        <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm">
          <h2 class="text-sm font-bold font-headline uppercase tracking-wider mb-2">Overall Coverage</h2>
          <h2 class="text-2xl font-extrabold font-headline text-primary tracking-tighter">${covPct}%</h2>
          <div class="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden mt-2">
            <div class="h-full bg-gradient-to-r from-primary to-surface-tint rounded-full" style="width:${covPct}%"></div>
          </div>
          <p class="text-[10px] text-on-surface-variant mt-1">${d.with_data} / ${d.total} with at least one record</p>
        </div>
        <!-- Score Breakdown -->
        <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm">
          <h2 class="text-sm font-bold font-headline uppercase tracking-wider mb-2">Score Breakdown</h2>
          <table class="w-full text-left border-collapse">
            <thead><tr class="border-b border-outline-variant/20">
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Score</th>
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Companies</th>
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Coverage</th>
            </tr></thead>
            <tbody class="divide-y divide-surface-variant/10">${scoreRows}</tbody>
          </table>
        </div>
        <!-- Source Breakdown -->
        ${sourceRows ? `<div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm">
          <h2 class="text-sm font-bold font-headline uppercase tracking-wider mb-2">Source Breakdown</h2>
          <table class="w-full text-left border-collapse">
            <thead><tr class="border-b border-outline-variant/20">
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Source</th>
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Companies</th>
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Coverage</th>
            </tr></thead>
            <tbody class="divide-y divide-surface-variant/10">${sourceRows}</tbody>
          </table>
        </div>` : ''}
        <!-- Record Breakdown -->
        <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm">
          <h2 class="text-sm font-bold font-headline uppercase tracking-wider mb-2">Record Breakdown</h2>
          <table class="w-full text-left border-collapse">
            <thead><tr class="border-b border-outline-variant/20">
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Records</th>
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Companies</th>
              <th class="px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Coverage</th>
            </tr></thead>
            <tbody class="divide-y divide-surface-variant/10">${breakdownRows}</tbody>
          </table>
        </div>
      </div>

      <!-- Right: company table -->
      <div class="lg:col-span-9">
        <section class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
          <div class="px-5 py-3 bg-surface-container-low flex justify-between items-center">
            <div class="flex items-center gap-3 flex-wrap">
              <h3 class="text-sm font-bold font-headline text-on-surface tracking-tight">Companies (not yet contacted)</h3>
              ${badges.join(' ')}
            </div>
            <span class="text-[10px] text-on-surface-variant">${totalResults} total, page ${currentPage}</span>
          </div>
          <table class="w-full text-left border-collapse">
            <thead class="bg-surface-container-low"><tr>
              <th class="px-4 py-2 w-10"></th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer sortable" data-col="name">Company${si('name')}</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer sortable" data-col="city">Location${si('city')}</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant cursor-pointer sortable" data-col="score">Score${si('score')}</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant text-center cursor-pointer sortable" data-col="data_count">Intel${si('data_count')}</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Status</th>
            </tr></thead>
            <tbody class="divide-y divide-surface-variant/20">${tableRows}</tbody>
          </table>
          <div id="intel-pagination" class="px-4 py-2 bg-surface-container-low flex justify-center gap-1 border-t border-surface-variant/20"></div>
        </section>
      </div>
    </div>`;

  // Pagination
  const totalPages = Math.max(1, Math.ceil(totalResults / PAGE_SIZE));
  const pagEl = document.getElementById('intel-pagination');
  if (pagEl && totalPages > 1) {
    let h = '';
    if (currentPage > 1) h += `<button class="pg w-6 h-6 flex items-center justify-center rounded bg-surface-bright text-primary border border-surface-variant hover:bg-surface-container-high" data-p="${currentPage-1}"><span class="material-symbols-outlined text-sm">chevron_left</span></button>`;
    h += `<span class="w-6 h-6 flex items-center justify-center rounded bg-primary text-on-primary text-[10px] font-bold">${currentPage}</span>`;
    h += `<span class="text-[10px] text-on-surface-variant self-center">/ ${totalPages}</span>`;
    if (currentPage < totalPages) h += `<button class="pg w-6 h-6 flex items-center justify-center rounded bg-surface-bright text-primary border border-surface-variant hover:bg-surface-container-high" data-p="${currentPage+1}"><span class="material-symbols-outlined text-sm">chevron_right</span></button>`;
    pagEl.innerHTML = h;
    pagEl.querySelectorAll('.pg').forEach(b => b.addEventListener('click', () => { currentPage = +b.dataset.p; renderIntelligence(); }));
  }

  // Data count filter
  app.querySelectorAll('.data-filter').forEach(el => el.addEventListener('click', () => {
    const rows = parseInt(el.dataset.rows);
    if (filterDataCount && filterDataCount.min === rows && filterDataCount.max === rows) {
      filterDataCount = null;
    } else {
      filterDataCount = { min: rows, max: rows };
    }
    currentPage = 1;
    renderIntelligence();
  }));

  // Score filter
  app.querySelectorAll('.score-filter').forEach(el => el.addEventListener('click', () => {
    const min = parseInt(el.dataset.min), max = parseInt(el.dataset.max);
    if (filterScore && filterScore.min === min && filterScore.max === max) {
      filterScore = null;
    } else {
      filterScore = { min, max };
    }
    currentPage = 1;
    renderIntelligence();
  }));

  // Source filter
  app.querySelectorAll('.source-filter').forEach(el => el.addEventListener('click', () => {
    const val = el.dataset.source;
    filterSource = filterSource === val ? null : val;
    currentPage = 1;
    renderIntelligence();
  }));

  // Clear filter badges
  app.querySelectorAll('.filter-badge').forEach(el => el.addEventListener('click', () => {
    const type = el.dataset.clear;
    if (type === 'source') filterSource = null;
    if (type === 'data') filterDataCount = null;
    if (type === 'score') filterScore = null;
    currentPage = 1;
    renderIntelligence();
  }));

  // Column sorting
  app.querySelectorAll('.sortable').forEach(th => th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (sortBy === col) {
      if (sortOrder === 'desc') sortOrder = 'asc';
      else { sortBy = 'score'; sortOrder = 'desc'; }
    } else {
      sortBy = col;
      sortOrder = 'desc';
    }
    currentPage = 1;
    renderIntelligence();
  }));

  attachRowHandlers(app, toggleStar, () => { stats = null; renderIntelligence(); });
}
