/**
 * Shared helpers for unified company row rendering across all views.
 */

export function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

/** Score color: grey(0) → green(10) */
export function scoreColor(score) {
  const s = Math.max(0, Math.min(10, Number(score) || 0));
  if (s === 0) return '#c5c6ce';
  // Interpolate from light grey-green to dark green
  const colors = [
    '#c5c6ce','#a8b5a0','#8da882','#739b66','#5e8e50',
    '#4a813c','#3b6934','#2d5528','#23501e','#143200','#0b2000'
  ];
  return colors[s] || '#0b2000';
}

/** CRM badge HTML */
export function crmBadge(status) {
  const crm = status || 'new';
  return `<span class="crm-badge-${crm} px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-tighter">${crm}</span>`;
}

/**
 * Render a unified table row for a company.
 * c must have: id, name, vat_number, city, region, starred, score, confidence, data_count, crm_status
 */
export function companyRow(c) {
  const starIcon = c.starred ? '★' : '☆';
  const starColor = c.starred ? 'text-amber-400' : 'text-gray-300 hover:text-amber-300';
  const score = Number(c.score) || 0;
  const conf = c.confidence != null ? Number(c.confidence) : 0;
  const confDisplay = conf > 1 ? (conf / 100).toFixed(2) : conf.toFixed(2);
  const intel = c.data_count || 0;

  return `<tr class="hover:bg-surface-container-low/50 transition-colors cursor-pointer">
    <td class="px-4 py-2 w-10"><span class="star-toggle ${starColor} cursor-pointer text-xl" data-id="${c.id}">${starIcon}</span></td>
    <td class="px-4 py-2" data-nav="${c.id}">
      <div class="text-xs font-semibold text-primary">${esc(c.name)}</div>
      <div class="text-[10px] text-outline">P.IVA: ${esc(c.vat_number||'')}</div>
    </td>
    <td class="px-4 py-2">
      <div class="text-[11px] text-secondary">${esc(c.city||'')}</div>
      <div class="text-[10px] text-outline">${esc(c.region||'')}</div>
    </td>
    <td class="px-4 py-2">
      <div class="text-xs font-bold" style="color:${scoreColor(score)}">${score}</div>
      <div class="text-[10px] text-outline">${confDisplay}</div>
    </td>
    <td class="px-4 py-2 text-[11px] text-center">${intel}</td>
    <td class="px-4 py-2">${crmBadge(c.crm_status)}</td>
  </tr>`;
}

/** Unified table header */
export function companyTableHeader() {
  return `<thead class="bg-surface-container-low"><tr>
    <th class="px-4 py-2 w-10"></th>
    <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Company</th>
    <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Location</th>
    <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Score</th>
    <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant text-center">Intel</th>
    <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Status</th>
  </tr></thead>`;
}

/** Attach star toggle and row navigation handlers */
export function attachRowHandlers(container, toggleStarFn, onStarDone) {
  container.querySelectorAll('.star-toggle').forEach(s => s.addEventListener('click', async (e) => {
    e.stopPropagation();
    await toggleStarFn(s.dataset.id);
    if (onStarDone) onStarDone();
  }));
  container.querySelectorAll('[data-nav]').forEach(td => td.addEventListener('click', () => {
    location.hash = '#/company/' + td.dataset.nav;
  }));
}
