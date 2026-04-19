import { getCompanies, getRegions, autocompleteCompanies, toggleStar, createCompany } from '../api.js';
import { esc, scoreColor, crmBadge, attachRowHandlers } from '../row-helpers.js';
import { getSelectedTopicId } from '../state.js';

let state = { search:'', region:'', crm_status:'', starred:false, score_min:0, score_max:10,
  emp_min:0, emp_max:10000, sort_by:'name', sort_order:'asc', page:1 };
let regions = [];
const PAGE_SIZE = 50;
const EMP_SLIDER_MAX = 1000; // slider goes 0-1000, with 1000 meaning "1000+"

export async function renderCompanies() {
  const app = document.getElementById('app');
  if (!regions.length) { try { regions = await getRegions(); } catch { regions = []; } }
  app.innerHTML = `
    <div class="flex gap-3 mb-3 sticky top-[56px] z-10 items-stretch">
      <div class="flex-1 relative">
        <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-lg">search</span>
        <input id="f-search" type="text" value="${esc(state.search)}" placeholder="Search by name, VAT or city..." autocomplete="off"
          class="w-full bg-surface-container-low border-none rounded-xl py-2 pl-10 pr-4 text-sm focus:ring-1 focus:ring-primary-fixed-dim placeholder:text-outline" />
        <div id="ac-dropdown" class="absolute left-0 right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-outline-variant/20 z-50 hidden max-h-60 overflow-y-auto"></div>
      </div>
      <button id="btn-new-company" class="bg-primary text-on-primary rounded-xl text-[10px] font-bold uppercase tracking-wider hover:bg-primary/90 transition-colors px-4">Add</button>
    </div>
    <div class="flex gap-3">
      <aside id="filter-panel" class="w-1/6 min-w-[180px] shrink-0"></aside>
      <div class="flex-1 min-w-0">
        <div id="co-table" class="bg-surface-container-lowest rounded-xl overflow-hidden shadow-sm"><p class="p-4 text-secondary">Loading...</p></div>
        <div id="co-pagination" class="mt-2 flex justify-center"></div>
      </div>
    </div>
    ${modalHTML()}`;
  renderFilterPanel();
  attachSearchHandlers();
  attachModalHandlers();
  await loadData();
}

function empLabel(v) { return v >= EMP_SLIDER_MAX ? '1000+' : String(v); }

function renderFilterPanel() {
  const regionOpts = regions.map(r =>
    `<option value="${esc(r)}" ${state.region===r?'selected':''}>${esc(r)}</option>`).join('');
  const loVal = state.emp_min, hiVal = Math.min(state.emp_max, EMP_SLIDER_MAX);

  document.getElementById('filter-panel').innerHTML = `
    <div class="bg-surface-container-low rounded-xl p-3 space-y-4 sticky top-[100px]">
      <h3 class="text-[10px] font-bold uppercase tracking-[0.15em] text-on-surface-variant">Filters</h3>

      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" id="f-starred" ${state.starred?'checked':''} class="w-4 h-4 rounded border-outline accent-amber-500" />
        <span class="text-xs font-semibold text-on-surface-variant">Starred only</span>
      </label>

      <div>
        <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Status</label>
        <select id="f-crm" class="mt-1 w-full bg-surface-bright border-none rounded-lg py-1.5 px-2 text-xs">
          <option value="">All</option>
          ${['new','contacted','interested','negotiating','not_interested','customer'].map(s =>
            `<option value="${s}" ${state.crm_status===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>

      <div>
        <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Score</label>
        <div class="flex justify-between text-[10px] text-secondary mt-1">
          <span>min: <strong id="sc-lo-label">${state.score_min}</strong></span>
          <span>max: <strong id="sc-hi-label">${state.score_max}</strong></span>
        </div>
        <div class="range-slider relative h-6 mt-1">
          <input type="range" id="sc-lo" min="0" max="10" value="${state.score_min}" step="1"
            class="range-thumb absolute w-full pointer-events-none appearance-none bg-transparent h-1 top-2.5 z-20" />
          <input type="range" id="sc-hi" min="0" max="10" value="${state.score_max}" step="1"
            class="range-thumb absolute w-full pointer-events-none appearance-none bg-transparent h-1 top-2.5 z-30" />
          <div class="absolute h-1 bg-outline/20 rounded top-2.5 left-0 right-0"></div>
          <div id="sc-track" class="absolute h-1 bg-primary rounded top-2.5"
            style="left:${state.score_min/10*100}%;right:${100-state.score_max/10*100}%"></div>
        </div>
      </div>

      <div>
        <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Employees</label>
        <div class="flex justify-between text-[10px] text-secondary mt-1">
          <span>min: <strong id="emp-lo-label">${empLabel(loVal)}</strong></span>
          <span>max: <strong id="emp-hi-label">${empLabel(hiVal)}</strong></span>
        </div>
        <div class="range-slider relative h-6 mt-1">
          <input type="range" id="emp-lo" min="0" max="${EMP_SLIDER_MAX}" value="${loVal}" step="10"
            class="range-thumb absolute w-full pointer-events-none appearance-none bg-transparent h-1 top-2.5 z-20" />
          <input type="range" id="emp-hi" min="0" max="${EMP_SLIDER_MAX}" value="${hiVal}" step="10"
            class="range-thumb absolute w-full pointer-events-none appearance-none bg-transparent h-1 top-2.5 z-30" />
          <div class="absolute h-1 bg-outline/20 rounded top-2.5 left-0 right-0"></div>
          <div id="emp-track" class="absolute h-1 bg-primary rounded top-2.5"
            style="left:${loVal/EMP_SLIDER_MAX*100}%;right:${100-hiVal/EMP_SLIDER_MAX*100}%"></div>
        </div>
      </div>

      <div>
        <label class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Region</label>
        <select id="f-region" class="mt-1 w-full bg-surface-bright border-none rounded-lg py-1.5 px-2 text-xs">
          <option value="">All</option>${regionOpts}
        </select>
      </div>

      <button id="btn-reset" class="w-full text-[10px] font-bold uppercase tracking-wider text-on-surface-variant bg-surface-bright rounded-lg py-1.5 hover:bg-surface-container-highest transition-colors">Reset</button>
    </div>
    <style>
      .range-thumb{-webkit-appearance:none;appearance:none}
      .range-thumb::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:var(--md-sys-color-primary,#0f3460);border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.3);cursor:pointer;pointer-events:auto;position:relative;z-index:30}
      .range-thumb::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--md-sys-color-primary,#0f3460);border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.3);cursor:pointer;pointer-events:auto}
    </style>`;

  // Events
  document.getElementById('f-starred').onchange = (e) => { state.starred=e.target.checked; state.page=1; loadData(); };
  document.getElementById('f-crm').onchange = applyFilters;
  document.getElementById('f-region').onchange = applyFilters;
  document.getElementById('btn-reset').onclick = () => {
    state={...state,region:'',crm_status:'',starred:false,score_min:0,score_max:10,emp_min:0,emp_max:10000,page:1};
    renderFilterPanel(); loadData();
  };

  // Score dual slider
  const slo=document.getElementById('sc-lo'), shi=document.getElementById('sc-hi');
  const strack=document.getElementById('sc-track');
  const sloL=document.getElementById('sc-lo-label'), shiL=document.getElementById('sc-hi-label');
  function updS() {
    let lv=+slo.value, hv=+shi.value;
    if(lv>hv){slo.value=hv;lv=hv;}
    strack.style.left=(lv/10*100)+'%';
    strack.style.right=(100-hv/10*100)+'%';
    sloL.textContent=lv; shiL.textContent=hv;
  }
  slo.oninput=updS; shi.oninput=updS;
  slo.onchange=()=>{state.score_min=+slo.value;state.page=1;loadData();};
  shi.onchange=()=>{state.score_max=+shi.value;state.page=1;loadData();};

  // Employee dual slider
  const lo=document.getElementById('emp-lo'), hi=document.getElementById('emp-hi');
  const track=document.getElementById('emp-track');
  const loL=document.getElementById('emp-lo-label'), hiL=document.getElementById('emp-hi-label');
  function upd() {
    let lv=+lo.value, hv=+hi.value;
    if(lv>hv){lo.value=hv;lv=hv;}
    track.style.left=(lv/EMP_SLIDER_MAX*100)+'%';
    track.style.right=(100-hv/EMP_SLIDER_MAX*100)+'%';
    loL.textContent=empLabel(lv); hiL.textContent=empLabel(hv);
  }
  lo.oninput=upd; hi.oninput=upd;
  lo.onchange=()=>{state.emp_min=+lo.value;state.page=1;loadData();};
  hi.onchange=()=>{state.emp_max=+hi.value>=EMP_SLIDER_MAX?10000:+hi.value;state.page=1;loadData();};
}

function applyFilters() {
  state.search=document.getElementById('f-search').value;
  state.region=document.getElementById('f-region').value;
  state.crm_status=document.getElementById('f-crm').value;
  state.page=1; loadData();
}

function attachSearchHandlers() {
  const si=document.getElementById('f-search'),dd=document.getElementById('ac-dropdown');
  let t=null;
  si.onkeydown=e=>{if(e.key==='Enter'){dd.classList.add('hidden');applyFilters();}};
  si.oninput=()=>{
    clearTimeout(t);const q=si.value.trim();
    if(q.length<2){dd.classList.add('hidden');return;}
    t=setTimeout(async()=>{
      try{const r=await autocompleteCompanies(q);if(!r.length){dd.classList.add('hidden');return;}
        dd.innerHTML=r.map(x=>`<div class="ac-item px-3 py-2 hover:bg-surface-container-low cursor-pointer text-sm" data-id="${x.id}"><div class="font-semibold text-primary">${esc(x.name)}</div><div class="text-[10px] text-outline">P.IVA: ${esc(x.vat_number)}</div></div>`).join('');
        dd.classList.remove('hidden');
        dd.querySelectorAll('.ac-item').forEach(i=>i.onmousedown=e=>{e.preventDefault();location.hash='#/company/'+i.dataset.id;});
      }catch{dd.classList.add('hidden');}
    },300);
  };
  si.onblur=()=>setTimeout(()=>dd.classList.add('hidden'),200);
}

async function loadData() {
  try {
    const params = {};
    if (state.search) params.search = state.search;
    if (state.region) params.region = state.region;
    if (state.crm_status) params.crm_status = state.crm_status;
    if (state.starred) params.starred = true;
    if (state.score_min > 0) params.min_score = state.score_min;
    if (state.score_max < 10) params.max_score = state.score_max;
    if (state.emp_min > 0) params.emp_min = state.emp_min;
    if (state.emp_max < 10000) params.emp_max = state.emp_max;
    params.sort_by = state.sort_by;
    params.sort_order = state.sort_order;
    params.page = state.page;
    params.page_size = PAGE_SIZE;
    const data = await getCompanies(params);
    renderTable(data);
    renderPagination(data);
  } catch(err) {
    document.getElementById('co-table').innerHTML = `<p class="p-4 text-error">${esc(err.message)}</p>`;
  }
}

function empDisplay(c) {
  if (c.employees_min != null && c.employees_max != null) {
    if (c.employees_max >= 10000) return c.employees_min + '+';
    return c.employees_min + '-' + c.employees_max;
  }
  return '-';
}

function fmtEuro(v) {
  if (v == null) return '-';
  return '€ ' + Number(v).toLocaleString('it-IT');
}

function renderTable(data) {
  const el = document.getElementById('co-table');
  if (!data.results.length) { el.innerHTML='<p class="p-4 text-secondary">No companies found.</p>'; return; }
  const si = col => state.sort_by!==col ? '' : state.sort_order==='asc' ? ' ▲' : ' ▼';

  const topicSelected = !!getSelectedTopicId();
  const rows = data.results.map(c => {
    const score = c.relevance_score!=null ? c.relevance_score : 0;
    const emp = empDisplay(c);
    const star = c.starred ? '★' : '☆';
    const sc = c.starred ? 'text-amber-400' : 'text-gray-300 hover:text-amber-300';
    const status = topicSelected ? (c.topic_crm_status || c.crm_status) : c.crm_status;
    return `<tr class="hover:bg-surface-container-low/50 transition-colors cursor-pointer">
      <td class="px-3 py-2 w-8"><span class="star-toggle ${sc} cursor-pointer text-lg" data-id="${c.id}">${star}</span></td>
      <td class="px-3 py-2" data-nav="${c.id}">
        <div class="text-xs font-semibold text-primary">${esc(c.name)}</div>
        <div class="text-[10px] text-outline">P.IVA: ${esc(c.vat_number||'')}</div>
      </td>
      <td class="px-3 py-2"><div class="text-[11px] text-secondary">${esc(c.city||'')}</div><div class="text-[10px] text-outline">${esc(c.region||'')}</div></td>
      <td class="px-3 py-2"><span class="text-xs font-bold" style="color:${scoreColor(score)}">${score}</span></td>
      <td class="px-3 py-2 text-[11px] text-secondary text-right">${fmtEuro(c.latest_revenue)}</td>
      <td class="px-3 py-2 text-[11px] text-secondary">${esc(emp)}</td>
      <td class="px-3 py-2">${crmBadge(status)}</td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="w-full text-left border-collapse">
    <thead class="bg-surface-container-low"><tr>
      <th class="px-3 py-2 w-8"></th>
      <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant cursor-pointer co-sort" data-col="name">Company${si('name')}</th>
      <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant cursor-pointer co-sort" data-col="city">Location${si('city')}</th>
      <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant cursor-pointer co-sort" data-col="score">Score${si('score')}</th>
      <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant cursor-pointer co-sort text-right" data-col="latest_revenue">Revenue${si('latest_revenue')}</th>
      <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant cursor-pointer co-sort" data-col="employees">Employees${si('employees')}</th>
      <th class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-on-surface-variant cursor-pointer co-sort" data-col="crm_status">Status${si('crm_status')}</th>
    </tr></thead>
    <tbody class="divide-y divide-surface-variant/30">${rows}</tbody>
  </table>
  <div class="px-3 py-2 bg-surface-container-low border-t border-surface-variant/20">
    <p class="text-[10px] font-semibold text-on-surface-variant uppercase tracking-widest">Showing ${data.results.length} of ${data.total}</p>
  </div>`;

  attachRowHandlers(el, toggleStar, ()=>loadData());
  el.querySelectorAll('.co-sort').forEach(th => th.onclick = () => {
    const col=th.dataset.col;
    if(state.sort_by===col){
      if(state.sort_order==='asc')state.sort_order='desc';
      else{state.sort_by='name';state.sort_order='asc';}
    }else{state.sort_by=col;state.sort_order=(col==='name'||col==='city')?'asc':'desc';}
    state.page=1;loadData();
  });
}

function renderPagination(data) {
  const el=document.getElementById('co-pagination');
  const tp=Math.max(1,Math.ceil(data.total/data.page_size));
  if(tp<=1){el.innerHTML='';return;}
  let h='';
  if(data.page>1)h+=`<button class="pg w-6 h-6 flex items-center justify-center rounded bg-surface-bright text-primary border border-surface-variant hover:bg-surface-container-high" data-p="${data.page-1}"><span class="material-symbols-outlined text-sm">chevron_left</span></button>`;
  h+=`<span class="w-6 h-6 flex items-center justify-center rounded bg-primary text-on-primary text-[10px] font-bold">${data.page}</span>`;
  if(data.page<tp)h+=`<button class="pg w-6 h-6 flex items-center justify-center rounded bg-surface-bright text-primary border border-surface-variant hover:bg-surface-container-high" data-p="${data.page+1}"><span class="material-symbols-outlined text-sm">chevron_right</span></button>`;
  el.innerHTML=`<div class="flex gap-1">${h}</div>`;
  el.querySelectorAll('.pg').forEach(b=>b.onclick=()=>{state.page=+b.dataset.p;loadData();});
}

function modalHTML() {
  return `<div id="modal-new" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/40">
    <div class="bg-surface-container-lowest rounded-xl shadow-2xl border border-outline-variant/20 p-5 w-full max-w-3xl mx-4">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-sm font-bold font-headline uppercase tracking-wider text-primary">New Company</h2>
        <button id="modal-close" class="text-on-surface-variant hover:text-error"><span class="material-symbols-outlined">close</span></button>
      </div>
      <div class="grid grid-cols-12 gap-3">
        <label class="col-span-5 text-[10px] font-bold text-on-surface-variant uppercase">Name *<input id="nc-name" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-3 text-[10px] font-bold text-on-surface-variant uppercase">VAT *<input id="nc-vat" placeholder="12345678901" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">ATECO<input id="nc-ateco" placeholder="35.11" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">Score<select id="nc-score" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"><option value="">—</option>${[0,1,2,3,4,5,6,7,8,9,10].map(n=>'<option value="'+n+'">'+n+'</option>').join('')}</select></label>
        <label class="col-span-5 text-[10px] font-bold text-on-surface-variant uppercase">Address<input id="nc-address" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-3 text-[10px] font-bold text-on-surface-variant uppercase">City<input id="nc-city" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">County<input id="nc-county" placeholder="MI" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase">Region<input id="nc-region" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-6 text-[10px] font-bold text-on-surface-variant uppercase">Website<input id="nc-web" placeholder="https://..." class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="col-span-6 text-[10px] font-bold text-on-surface-variant uppercase">Notes<input id="nc-notes" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
      </div>
      <div class="flex items-center gap-3 mt-4 justify-end">
        <span id="nc-feedback" class="text-xs mr-auto"></span>
        <button id="modal-cancel" class="text-on-surface-variant text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-lg hover:bg-surface-container-high transition-colors">Cancel</button>
        <button id="btn-create" class="bg-primary text-on-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-lg hover:bg-primary/90 transition-colors">Add</button>
      </div>
    </div>
  </div>`;
}

function attachModalHandlers() {
  const show=()=>document.getElementById('modal-new').classList.remove('hidden');
  const hide=()=>document.getElementById('modal-new').classList.add('hidden');
  document.getElementById('btn-new-company').onclick=show;
  document.getElementById('modal-close').onclick=hide;
  document.getElementById('modal-cancel').onclick=hide;
  document.getElementById('modal-new').onclick=e=>{if(e.target.id==='modal-new')hide();};
  document.getElementById('btn-create').onclick=async()=>{
    const fb=document.getElementById('nc-feedback');
    const vat=document.getElementById('nc-vat').value.trim(),name=document.getElementById('nc-name').value.trim();
    if(!vat||!name){fb.innerHTML='<span class="text-error">Name and VAT required</span>';return;}
    fb.innerHTML='<span class="text-on-surface-variant animate-pulse">Creating...</span>';
    try{
      const d={vat_number:vat,name};const v=id=>document.getElementById(id).value.trim();
      if(v('nc-ateco'))d.ateco_code=v('nc-ateco');if(v('nc-region'))d.region=v('nc-region');
      if(v('nc-city'))d.city=v('nc-city');if(v('nc-county'))d.county=v('nc-county');
      if(v('nc-address'))d.address=v('nc-address');if(v('nc-web'))d.website_url=v('nc-web');
      if(v('nc-notes'))d.notes=v('nc-notes');
      const sc=document.getElementById('nc-score').value;if(sc!=='')d.score=parseInt(sc);
      const r=await createCompany(d);hide();location.hash='#/company/'+r.id;
    }catch(err){fb.innerHTML=`<span class="text-error">${esc(err.message)}</span>`;}
  };
}
