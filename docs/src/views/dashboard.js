import { getDashboard, toggleStar } from '../api.js';
import { esc, companyRow, attachRowHandlers, scoreColor } from '../row-helpers.js';

let stats = null;

export async function renderDashboard() {
  const app = document.getElementById('app');
  // Always re-fetch stats so topic filter changes are reflected
  stats = null;
  app.innerHTML = '<p class="text-secondary">Loading...</p>';
  try { stats = await getDashboard(); } catch (err) { app.innerHTML = `<p class="text-error">${esc(err.message)}</p>`; return; }
  render(app);
}

function limitRows(items, max) {
  if (items.length <= max) return items;
  const visible = items.slice(0, max - 1);
  const rest = items.slice(max - 1);
  const otherCount = rest.reduce((s, r) => s + (r.companies || r.count || 0), 0);
  const otherPct = rest.reduce((s, r) => s + parseFloat(r._pct || 0), 0);
  return [...visible, { _other: true, companies: otherCount, _pct: otherPct.toFixed(1) }];
}

function render(app) {
  const d = stats;
  const totalCo = d.total_companies || 1;
  const MAX = 6;

  const highPotNew = d.high_potential_new || 0;
  const needsScoring = d.needs_scoring || 0;
  const overallCov = d.overall_coverage || 0;
  const notInt = d.not_interested_count || (d.by_crm_status['not_interested'] || 0);
  const notIntPct = (notInt / totalCo * 100).toFixed(1);

  const pipelineLabels = { new:'New', contacted:'Contacted', interested:'Interested', negotiating:'Negotiating', customer:'Customer', not_interested:'Not Interested' };
  const newCo = d.by_crm_status['new'] || 0;
  const contacted = d.by_crm_status['contacted'] || 0;
  const interested = d.by_crm_status['interested'] || 0;
  const negotiating = d.by_crm_status['negotiating'] || 0;
  const customer = d.by_crm_status['customer'] || 0;
  const cv = (a, b) => a ? ((b / a) * 100).toFixed(1) : '0.0';
  const wr = d.weekly_rates || {};
  const fw = (v) => v != null ? `${v}/wk` : '0.0/wk';

  function bdTable(title, col, items, base) {
    const enriched = items.map(r => ({ ...r, _pct: (((r.companies||r.count||0) / base) * 100).toFixed(1) }));
    const limited = limitRows(enriched, MAX);
    const rows = limited.map(r => {
      if (r._other) return `<tr><td class="px-3 py-1 text-[11px] italic text-secondary">Other</td><td class="px-3 py-1 text-[11px] text-right font-mono">${r.companies}</td><td class="px-3 py-1 text-[11px] text-right font-mono">${r._pct}%</td></tr>`;
      const lbl = r.label || r.source || '';
      return `<tr><td class="px-3 py-1 text-[11px] font-bold uppercase">${esc(pipelineLabels[lbl]||lbl)}</td><td class="px-3 py-1 text-[11px] text-right font-mono">${r.companies||r.count||0}</td><td class="px-3 py-1 text-[11px] text-right font-mono">${r._pct}%</td></tr>`;
    }).join('');
    return `<div class="bg-surface-container-lowest rounded-xl shadow-sm flex flex-col overflow-hidden">
      <div class="px-3 py-2 bg-surface-container-low"><h2 class="text-sm font-bold font-headline uppercase tracking-wider">${title}</h2></div>
      <table class="w-full text-left border-collapse flex-1"><thead><tr class="border-b border-outline-variant/20">
        <th class="px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">${col}</th>
        <th class="px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Companies</th>
        <th class="px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant text-right">Coverage</th>
      </tr></thead><tbody class="divide-y divide-surface-variant/10">${rows}</tbody></table></div>`;
  }

  const statusItems = ['new','contacted','interested','negotiating','customer','not_interested'].map(s => ({ label: s, companies: d.by_crm_status[s]||0 }));
  const regionItems = Object.entries(d.by_region).map(([n,c]) => ({ label: n, companies: c }));
  const scoreItems = (d.score_breakdown||[]).map(r => ({ label: r.label, companies: r.companies }));
  const sourceItems = (d.by_source||[]).map(r => ({ label: r.source, companies: r.count }));
  const relevantList = (d.starred_companies||[]).map(c => companyRow(c)).join('');

  app.innerHTML = `
    <!-- Row 1: 5 counters -->
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-3">
      <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm border border-outline-variant/10">
        <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Total Companies</p>
        <span class="text-2xl font-extrabold font-headline text-primary tracking-tighter">${d.total_companies}</span>
      </div>
      <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm border border-outline-variant/10">
        <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">New High Potential</p>
        <div class="flex items-baseline gap-2"><span class="text-2xl font-extrabold font-headline text-primary tracking-tighter">${highPotNew}</span><span class="text-[10px] font-bold text-on-tertiary-container">${(highPotNew/totalCo*100).toFixed(1)}%</span></div>
      </div>
      <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm border border-outline-variant/10">
        <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Overall Coverage</p>
        <div class="flex items-baseline gap-2"><span class="text-2xl font-extrabold font-headline text-primary tracking-tighter">${overallCov}%</span><span class="text-[10px] font-bold text-on-tertiary-container">${d.with_data}/${d.total_companies}</span></div>
      </div>
      <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm border border-outline-variant/10">
        <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Not Interested</p>
        <div class="flex items-baseline gap-2"><span class="text-2xl font-extrabold font-headline text-primary tracking-tighter">${notInt}</span><span class="text-[10px] font-bold text-on-tertiary-container">${notIntPct}%</span></div>
      </div>
      <div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm border border-outline-variant/10">
        <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-1">Needs Scoring</p>
        <div class="flex items-baseline gap-2"><span class="text-2xl font-extrabold font-headline text-primary tracking-tighter">${needsScoring}</span><span class="text-[10px] font-bold text-on-tertiary-container">${(needsScoring/totalCo*100).toFixed(1)}%</span></div>
      </div>
    </div>

    <!-- Row 2: Funnel -->
    <div class="mb-3"><div class="bg-surface-container-lowest p-3 rounded-xl shadow-sm border border-outline-variant/10">
      <h2 class="text-sm font-bold font-headline uppercase tracking-wider mb-3">Conversion Funnel</h2>
      <div class="flex items-center justify-between gap-0">
        <div class="flex flex-col items-center flex-1 py-3 crm-badge-new rounded-lg min-w-0"><span class="text-xl font-extrabold font-headline">${newCo}</span><span class="text-[9px] font-bold uppercase">New</span></div>
        <div class="flex flex-col items-center px-2 min-w-[60px]"><span class="text-xs font-extrabold text-gray-600 bg-gray-200 px-2.5 py-1 rounded-full leading-none">${cv(newCo,contacted)}%</span><span class="text-[9px] text-secondary mt-1">${fw(wr.new_to_contacted)}</span></div>
        <div class="flex flex-col items-center flex-1 py-3 crm-badge-contacted rounded-lg min-w-0"><span class="text-xl font-extrabold font-headline">${contacted}</span><span class="text-[9px] font-bold uppercase">Contacted</span></div>
        <div class="flex flex-col items-center px-2 min-w-[60px]"><span class="text-xs font-extrabold text-gray-600 bg-gray-200 px-2.5 py-1 rounded-full leading-none">${cv(contacted,interested)}%</span><span class="text-[9px] text-secondary mt-1">${fw(wr.contacted_to_interested)}</span></div>
        <div class="flex flex-col items-center flex-1 py-3 crm-badge-interested rounded-lg min-w-0"><span class="text-xl font-extrabold font-headline">${interested}</span><span class="text-[9px] font-bold uppercase">Interested</span></div>
        <div class="flex flex-col items-center px-2 min-w-[60px]"><span class="text-xs font-extrabold text-gray-600 bg-gray-200 px-2.5 py-1 rounded-full leading-none">${cv(interested,negotiating)}%</span><span class="text-[9px] text-secondary mt-1">${fw(wr.interested_to_negotiating)}</span></div>
        <div class="flex flex-col items-center flex-1 py-3 crm-badge-negotiating rounded-lg min-w-0"><span class="text-xl font-extrabold font-headline">${negotiating}</span><span class="text-[9px] font-bold uppercase">Negotiating</span></div>
        <div class="flex flex-col items-center px-2 min-w-[60px]"><span class="text-xs font-extrabold text-gray-600 bg-gray-200 px-2.5 py-1 rounded-full leading-none">${cv(negotiating,customer)}%</span><span class="text-[9px] text-secondary mt-1">${fw(wr.negotiating_to_customer)}</span></div>
        <div class="flex flex-col items-center flex-1 py-3 crm-badge-customer rounded-lg min-w-0"><span class="text-xl font-extrabold font-headline">${customer}</span><span class="text-[9px] font-bold uppercase">Customer</span></div>
      </div>
    </div></div>

    <!-- Row 3: Breakdowns (1/3) + Most Relevant (2/3) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-3 items-stretch">
      <div class="lg:col-span-4 flex flex-col gap-3">
        ${bdTable('Score Breakdown','Score',scoreItems,d.scored_total||1)}
        ${bdTable('Region Breakdown','Region',regionItems,totalCo)}
      </div>
      <div class="lg:col-span-8">
        <div class="bg-surface-container-lowest rounded-xl shadow-sm overflow-hidden">
          <div class="px-4 py-3 bg-surface-container-low"><h2 class="text-sm font-bold font-headline uppercase tracking-wider">Most Relevant</h2></div>
          <table class="w-full text-left border-collapse">
            <thead class="bg-surface-container-low"><tr>
              <th class="px-4 py-2 w-10"></th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Company</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Location</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Score</th>
              <th class="px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Status</th>
            </tr></thead>
            <tbody class="divide-y divide-surface-variant/20">
              ${(d.starred_companies||[]).map(c => `<tr class="hover:bg-surface-container-low/50 transition-colors cursor-pointer">
                <td class="px-4 py-2 w-10"><span class="star-toggle ${c.starred?'text-amber-400':'text-gray-300 hover:text-amber-300'} cursor-pointer text-xl" data-id="${c.id}">${c.starred?'★':'☆'}</span></td>
                <td class="px-4 py-2" data-nav="${c.id}"><div class="text-xs font-semibold text-primary">${esc(c.name)}</div></td>
                <td class="px-4 py-2"><div class="text-[11px] text-secondary">${esc(c.city||'')}</div><div class="text-[10px] text-outline">${esc(c.region||'')}</div></td>
                <td class="px-4 py-2"><div class="text-xs font-bold" style="color:${scoreColor(c.score||0)}">${c.score||0}</div></td>
                <td class="px-4 py-2"><span class="crm-badge-${c.crm_status||'new'} px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-tighter">${c.crm_status||'new'}</span></td>
              </tr>`).join('') || '<tr><td colspan="5" class="px-4 py-4 text-xs text-secondary text-center">No companies</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

  attachRowHandlers(app, toggleStar, () => { stats = null; renderDashboard(); });
}
