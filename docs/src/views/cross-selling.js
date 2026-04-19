import { getTopics, getCrossSellingOpportunities } from '../api.js';
import { esc, crmBadge } from '../row-helpers.js';

let topics = [];

export async function renderCrossSelling() {
  const app = document.getElementById('app');
  if (!topics.length) { try { topics = await getTopics(); } catch { topics = []; } }

  app.innerHTML = `
    <div class="bg-surface-container-lowest p-4 rounded-xl shadow-sm border border-outline-variant/20">
      <h2 class="text-sm font-bold text-on-surface mb-3">Cross-Selling Opportunities</h2>
      <div class="flex gap-3 mb-4">
        <select id="cs-source" class="px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm">
          <option value="">Source Topic</option>
          ${topics.map(t => `<option value="${t.id}">${esc(t.parent_id ? '\u00A0\u00A0' + t.name : t.name)}</option>`).join('')}
        </select>
        <select id="cs-target" class="px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm">
          <option value="">Target Topic</option>
          ${topics.map(t => `<option value="${t.id}">${esc(t.parent_id ? '\u00A0\u00A0' + t.name : t.name)}</option>`).join('')}
        </select>
      </div>
      <div id="cs-results">
        <p class="text-secondary text-sm p-4">Select both a source and target topic to find cross-selling opportunities.</p>
      </div>
    </div>`;

  const srcSel = document.getElementById('cs-source');
  const tgtSel = document.getElementById('cs-target');
  srcSel.addEventListener('change', () => loadResults(srcSel, tgtSel));
  tgtSel.addEventListener('change', () => loadResults(srcSel, tgtSel));
}

async function loadResults(srcSel, tgtSel) {
  const srcId = parseInt(srcSel.value);
  const tgtId = parseInt(tgtSel.value);
  const el = document.getElementById('cs-results');

  if (!srcId || !tgtId) {
    el.innerHTML = '<p class="text-secondary text-sm p-4">Select both a source and target topic to find cross-selling opportunities.</p>';
    return;
  }

  el.innerHTML = '<p class="text-secondary text-sm p-4">Loading…</p>';

  try {
    const data = await getCrossSellingOpportunities(srcId, tgtId);
    if (!data.length) {
      el.innerHTML = '<p class="text-secondary text-sm p-4">No cross-selling opportunities found for this combination.</p>';
      return;
    }

    const rows = data.map(r => `<tr class="hover:bg-surface-container-low/50 transition-colors">
      <td class="px-3 py-2"><a href="#/company/${r.id}" class="text-primary hover:underline text-xs font-semibold">${esc(r.name)}</a></td>
      <td class="px-3 py-2 text-[11px] text-secondary">${esc(r.city || '')}</td>
      <td class="px-3 py-2 text-[11px] text-secondary">${esc(r.region || '')}</td>
      <td class="px-3 py-2">${crmBadge(r.source_status)}</td>
    </tr>`).join('');

    el.innerHTML = `<table class="w-full text-left border-collapse">
      <thead class="bg-surface-container-low"><tr>
        <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant">Company</th>
        <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant">City</th>
        <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant">Region</th>
        <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant">Source Status</th>
      </tr></thead>
      <tbody class="divide-y divide-surface-variant/30">${rows}</tbody>
    </table>
    <div class="px-3 py-2 bg-surface-container-low border-t border-surface-variant/20">
      <p class="text-[10px] font-semibold text-on-surface-variant uppercase tracking-widest">${data.length} opportunit${data.length === 1 ? 'y' : 'ies'} found</p>
    </div>`;
  } catch (e) {
    el.innerHTML = `<p class="text-red-500 text-sm p-4">Error: ${esc(e.message)}</p>`;
  }
}
