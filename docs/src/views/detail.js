import { getCompany, updateCompany, getCompanyData, createCompanyData, deleteCompanyData, getContacts, createContact, updateContact, deleteContact, getActivities, createActivity, deleteActivity, toggleStar, getStatuses, changeCompanyStatus, getCompanyTopics, getTopics, addCompanyTopic, removeCompanyTopic, changeCompanyTopicStatus } from '../api.js';
import { getSelectedTopicId } from '../state.js';
import { renderMarkdown } from '../markdownRenderer.js';

export async function renderDetail(id) {
  const app = document.getElementById('app');
  app.innerHTML = '<p class="text-secondary">Loading...</p>';
  try {
    const [company, companyData, contacts, activities, companyTopics, allTopics] = await Promise.all([
      getCompany(id), getCompanyData(id), getContacts(id), getActivities(id), getCompanyTopics(id), getTopics()
    ]);
    app.innerHTML = `
      <p class="mb-3"><a href="javascript:history.back()" class="text-secondary hover:text-primary flex items-center gap-1 text-sm"><span class="material-symbols-outlined text-sm">arrow_back</span> Back</a></p>
      <div id="d-header" class="bg-surface-container-lowest p-4 rounded-xl shadow-sm mb-3 border border-outline-variant/20"></div>
      <div id="d-edit" class="bg-surface-container-lowest p-4 rounded-xl shadow-sm mb-3 border border-outline-variant/20 hidden"></div>
      <div id="d-topics" class="bg-surface-container-lowest p-4 rounded-xl shadow-sm mb-3 border border-outline-variant/20"></div>
      <div id="d-activities" class="bg-surface-container-lowest p-4 rounded-xl shadow-sm mb-3 border border-outline-variant/20"></div>
      <div id="d-contacts" class="bg-surface-container-lowest p-4 rounded-xl shadow-sm mb-3 border border-outline-variant/20"></div>
      <div id="d-data" class="bg-surface-container-lowest p-4 rounded-xl shadow-sm mb-3 border border-outline-variant/20"></div>`;
    renderHeader(company, companyTopics);
    renderTopics(company.id, companyTopics, allTopics);
    renderActivities(company.id, activities);
    renderContacts(company.id, contacts);
    renderCompanyData(company.id, companyData);
  } catch (err) {
    app.innerHTML = `<p class="text-error">Error: ${esc(err.message)}</p>`;
  }
}

function renderHeader(c, companyTopics) {
  const el = document.getElementById('d-header');
  const crm = c.crm_status || 'new';
  const starIcon = c.starred ? '★' : '☆';
  const starColor = c.starred ? 'text-amber-400' : 'text-gray-300';

  // Task 10.2: Score from selected topic or highest among all
  const selectedTopicId = getSelectedTopicId();
  let rel = null;
  if (companyTopics && companyTopics.length) {
    if (selectedTopicId) {
      const match = companyTopics.find(t => t.topic_id === selectedTopicId);
      if (match) rel = { score: match.score, confidence: match.confidence, scored_at: match.scored_at, reasoning: match.reasoning };
    } else {
      // "Tutti i topic": show highest score
      const best = companyTopics.reduce((b, t) => (!b || (t.score || 0) > (b.score || 0)) ? t : b, null);
      if (best) rel = { score: best.score, confidence: best.confidence, scored_at: best.scored_at, reasoning: best.reasoning };
    }
  }
  const scoreLine = rel ? `<p class="text-xs text-secondary mt-1"><span class="font-semibold">Score:</span> ${rel.score} | <span class="font-semibold">Confidence:</span> ${Number(rel.confidence).toFixed(2)} | <span class="font-semibold">Elaborated:</span> ${rel.scored_at ? new Date(rel.scored_at).toLocaleDateString('it-IT') : '-'}</p>` : '';
  const reasoningHtml = rel && rel.reasoning ? `<p class="text-[11px] text-secondary/70 mt-0.5 italic">${esc(rel.reasoning)}</p>` : '';
  const addressParts = [c.address, c.city, c.county, c.region].filter(Boolean).join(', ');
  el.innerHTML = `<div class="flex justify-between items-start">
    <div>
      <h1 class="text-2xl font-headline font-extrabold text-primary flex items-center gap-2">
        <span id="btn-star" class="${starColor} cursor-pointer text-xl">${starIcon}</span>
        ${esc(c.name)}
        <span class="relative">
          <span id="btn-status" class="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase crm-badge-${crm} cursor-pointer hover:ring-2 hover:ring-primary/30">${crm}</span>
          <div id="status-dropdown" class="hidden absolute left-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-outline-variant/20 z-50 min-w-[160px]"></div>
        </span>
      </h1>
      ${scoreLine}
      ${reasoningHtml}
      <p class="text-xs text-secondary mt-1"><span class="font-semibold">VAT:</span> ${esc(c.vat_number)} | <span class="font-semibold">ATECO:</span> ${esc(c.ateco_code||'-')}${c.founding_date ? ' | <span class="font-semibold">Founded:</span> ' + fmtDate(c.founding_date) : ''}</p>
      <p class="text-xs text-secondary mt-0.5"><span class="font-semibold">Location:</span> ${addressParts || '-'}</p>
      ${revProfitLine(c)}
      ${empCostLine(c)}
      ${c.notes?'<p class="text-xs text-secondary/70 mt-1 italic">'+esc(c.notes)+'</p>':''}
    </div>
    <button id="btn-edit" class="px-3 py-1.5 bg-secondary text-on-secondary rounded-lg font-semibold text-xs hover:bg-[#374765] transition-colors flex items-center gap-1"><span class="material-symbols-outlined text-sm">edit</span> Edit</button>
  </div>`;
  document.getElementById('btn-edit').addEventListener('click', () => showEdit(c));
  document.getElementById('btn-star').addEventListener('click', async () => { await toggleStar(c.id); renderDetail(c.id); });

  // Status dropdown
  const btnStatus = document.getElementById('btn-status');
  const dropdown = document.getElementById('status-dropdown');
  btnStatus.addEventListener('click', async (e) => {
    e.stopPropagation();
    if (!dropdown.classList.contains('hidden')) { dropdown.classList.add('hidden'); return; }
    try {
      const statuses = await getStatuses();
      dropdown.innerHTML = statuses.map(s =>
        `<div class="status-opt px-3 py-2 text-[11px] cursor-pointer hover:bg-surface-container-low ${s.name===crm?'font-bold text-primary':'text-on-surface'}" data-status="${esc(s.name)}">
          <span class="uppercase font-bold">${esc(s.name)}</span>
          <span class="text-[10px] text-secondary ml-1">${esc(s.description||'')}</span>
        </div>`
      ).join('');
      dropdown.classList.remove('hidden');
      dropdown.querySelectorAll('.status-opt').forEach(opt => opt.addEventListener('click', async () => {
        dropdown.classList.add('hidden');
        const newStatus = opt.dataset.status;
        if (newStatus !== crm) {
          await changeCompanyStatus(c.id, { status: newStatus });
          renderDetail(c.id);
        }
      }));
    } catch (err) { console.error(err); }
  });
  document.addEventListener('click', () => dropdown.classList.add('hidden'), { once: true });
}

function renderTopics(companyId, companyTopics, allTopics) {
  const el = document.getElementById('d-topics');
  if (!el) return;

  const associatedIds = new Set(companyTopics.map(ct => ct.topic_id));
  const availableTopics = allTopics.filter(t => !associatedIds.has(t.id));

  const rows = companyTopics.map(ct => {
    const topicName = ct.topics?.name || `Topic #${ct.topic_id}`;
    const status = ct.crm_status || 'new';
    const score = ct.score != null ? ct.score : '-';
    const confidence = ct.confidence != null ? Number(ct.confidence).toFixed(2) : '-';
    const scoredAt = ct.scored_at ? new Date(ct.scored_at).toLocaleDateString('it-IT') : '-';
    return `<tr class="hover:bg-surface-container-low transition-colors">
      <td class="px-4 py-3 text-sm font-medium">${esc(topicName)}</td>
      <td class="px-4 py-3">
        <span class="relative inline-block">
          <span class="topic-status-btn px-2 py-0.5 rounded-md text-[10px] font-bold uppercase crm-badge-${status} cursor-pointer hover:ring-2 hover:ring-primary/30" data-company-id="${companyId}" data-topic-id="${ct.topic_id}" data-current-status="${esc(status)}">${esc(status)}</span>
          <div class="topic-status-dropdown hidden absolute left-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-outline-variant/20 z-50 min-w-[160px]"></div>
        </span>
      </td>
      <td class="px-4 py-3 text-sm">${score}</td>
      <td class="px-4 py-3 text-sm">${confidence}</td>
      <td class="px-4 py-3 text-sm">${scoredAt}</td>
      <td class="px-4 py-3"><button class="remove-topic text-error hover:text-red-800" data-topic-id="${ct.topic_id}" title="Remove topic"><span class="material-symbols-outlined text-sm">close</span></button></td>
    </tr>`;
  }).join('');

  const addDropdownOptions = availableTopics.map(t =>
    `<option value="${t.id}">${esc(t.name)}</option>`
  ).join('');

  el.innerHTML = `<h2 class="text-sm font-headline font-bold text-primary uppercase tracking-wider mb-3">Topics (${companyTopics.length})</h2>
    ${companyTopics.length ? `<table class="w-full text-left"><thead><tr class="bg-surface-container-low"><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Topic</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Status</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Score</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Confidence</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Scored At</th><th class="px-4 py-3"></th></tr></thead><tbody class="divide-y divide-surface-container">${rows}</tbody></table>` : '<p class="text-secondary text-xs">No topics associated.</p>'}
    ${availableTopics.length ? `<div class="mt-3 flex items-center gap-2">
      <select id="add-topic-select" class="px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm">
        <option value="">Select a topic...</option>
        ${addDropdownOptions}
      </select>
      <button id="btn-add-topic" class="px-4 py-2 bg-primary text-primary-fixed font-bold rounded-xl text-sm">+ Add Topic</button>
      <span id="topic-fb" class="text-sm"></span>
    </div>` : ''}`;

  // Task 10.3: Per-topic status change
  el.querySelectorAll('.topic-status-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const dropdown = btn.parentElement.querySelector('.topic-status-dropdown');
      if (!dropdown.classList.contains('hidden')) { dropdown.classList.add('hidden'); return; }
      // Close any other open dropdowns
      el.querySelectorAll('.topic-status-dropdown').forEach(d => d.classList.add('hidden'));
      try {
        const statuses = await getStatuses();
        const currentStatus = btn.dataset.currentStatus;
        dropdown.innerHTML = statuses.map(s =>
          `<div class="topic-status-opt px-3 py-2 text-[11px] cursor-pointer hover:bg-surface-container-low ${s.name === currentStatus ? 'font-bold text-primary' : 'text-on-surface'}" data-status="${esc(s.name)}">
            <span class="uppercase font-bold">${esc(s.name)}</span>
            <span class="text-[10px] text-secondary ml-1">${esc(s.description || '')}</span>
          </div>`
        ).join('');
        dropdown.classList.remove('hidden');
        dropdown.querySelectorAll('.topic-status-opt').forEach(opt => opt.addEventListener('click', async () => {
          dropdown.classList.add('hidden');
          const newStatus = opt.dataset.status;
          if (newStatus !== currentStatus) {
            await changeCompanyTopicStatus(companyId, parseInt(btn.dataset.topicId), newStatus);
            renderDetail(companyId);
          }
        }));
      } catch (err) { console.error(err); }
    });
  });

  // Close dropdowns on outside click
  document.addEventListener('click', () => {
    el.querySelectorAll('.topic-status-dropdown').forEach(d => d.classList.add('hidden'));
  }, { once: true });

  // Remove topic
  el.querySelectorAll('.remove-topic').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (confirm('Remove this topic association?')) {
        await removeCompanyTopic(companyId, parseInt(btn.dataset.topicId));
        renderDetail(companyId);
      }
    });
  });

  // Add topic
  document.getElementById('btn-add-topic')?.addEventListener('click', async () => {
    const select = document.getElementById('add-topic-select');
    const topicId = parseInt(select?.value);
    if (!topicId) { const fb = document.getElementById('topic-fb'); if (fb) fb.textContent = 'Select a topic first'; return; }
    try {
      await addCompanyTopic(companyId, topicId);
      renderDetail(companyId);
    } catch (e) {
      const fb = document.getElementById('topic-fb');
      if (fb) fb.textContent = e.message;
    }
  });
}

function showEdit(c) {
  const el = document.getElementById('d-edit');
  el.classList.remove('hidden');
  const crmOpts = ['new','contacted','interested','negotiating','not_interested','customer'].map(s =>
    `<option value="${s}" ${c.crm_status===s?'selected':''}>${s}</option>`).join('');
  el.innerHTML = `<h2 class="text-xl font-headline font-bold text-primary mb-4">Edit Company</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <label class="text-xs font-bold text-secondary/70 uppercase">Name <input id="e-name" value="${esc(c.name||'')}" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
      <label class="text-xs font-bold text-secondary/70 uppercase">ATECO <input id="e-ateco" value="${esc(c.ateco_code||'')}" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
      <label class="text-xs font-bold text-secondary/70 uppercase">Region <input id="e-region" value="${esc(c.region||'')}" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
      <label class="text-xs font-bold text-secondary/70 uppercase">City <input id="e-city" value="${esc(c.city||'')}" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
      <label class="text-xs font-bold text-secondary/70 uppercase">Address <input id="e-address" value="${esc(c.address||'')}" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
      <label class="text-xs font-bold text-secondary/70 uppercase">CRM Status <select id="e-crm" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm">${crmOpts}</select></label>
      <label class="text-xs font-bold text-secondary/70 uppercase md:col-span-2">Notes <textarea id="e-notes" rows="2" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm">${esc(c.notes||'')}</textarea></label>
      <div class="md:col-span-2 flex gap-3 mt-2">
        <button id="btn-save" class="px-5 py-2 bg-primary text-primary-fixed font-bold rounded-xl">Save</button>
        <button id="btn-cancel" class="px-5 py-2 bg-surface-container-highest text-secondary font-semibold rounded-xl">Cancel</button>
      </div>
      <div id="e-feedback" class="md:col-span-2"></div>
    </div>`;
  document.getElementById('btn-cancel').addEventListener('click', () => { el.classList.add('hidden'); });
  document.getElementById('btn-save').addEventListener('click', async () => {
    try {
      await updateCompany(c.id, {
        name: v('e-name'), ateco_code: v('e-ateco')||null, region: v('e-region')||null,
        city: v('e-city')||null, address: v('e-address')||null,
        crm_status: v('e-crm')||null, notes: v('e-notes')||null,
      });
      document.getElementById('e-feedback').innerHTML = '<p class="text-on-tertiary-container">Saved</p>';
      setTimeout(() => renderDetail(c.id), 600);
    } catch (err) { document.getElementById('e-feedback').innerHTML = `<p class="text-error">${esc(err.message)}</p>`; }
  });
}

function renderCompanyData(companyId, dataRows) {
  const el = document.getElementById('d-data');
  if (!el) return;
  const cards = (dataRows||[]).map((d, i) => {
    const date = d.created_at ? new Date(d.created_at).toLocaleString() : '—';
    const urlHtml = d.source_url ? `<p class="mt-1 text-xs"><span class="text-on-surface-variant font-bold">Source:</span> <a href="${esc(d.source_url)}" target="_blank" class="text-primary hover:underline">${esc(d.source_url.substring(0,80))}${d.source_url.length>80?'...':''}</a></p>` : '';
    const contentHtml = d.content ? `<div class="intel-content text-xs text-on-surface leading-relaxed line-clamp-md md-content cursor-pointer" data-idx="${i}" title="Click to expand">${renderMarkdown(d.content)}</div>` : '';
    return `<div class="border border-outline-variant/10 rounded-lg p-3 mb-2 bg-surface-container-low/30">
      <div class="flex justify-between items-center mb-1">
        <div class="flex gap-3 items-center text-xs text-secondary"><span class="px-1.5 py-0.5 bg-primary-fixed/30 text-primary rounded text-[10px] font-bold">${esc(d.source)}</span><span>${date}</span></div>
        <button class="del-data text-error hover:text-red-800" data-id="${d.id}"><span class="material-symbols-outlined text-sm">delete</span></button>
      </div>
      ${contentHtml}
      ${d.content ? '<p class="expand-indicator text-[10px] text-secondary/60 mt-1 cursor-pointer italic">Clicca per espandere</p>' : ''}
      ${urlHtml}
    </div>`;
  }).join('');

  el.innerHTML = `<h2 class="text-sm font-headline font-bold text-primary uppercase tracking-wider mb-3">Intelligence Data (${(dataRows||[]).length})</h2>
    ${cards || '<p class="text-secondary text-xs">No data available.</p>'}
    <details class="mt-3"><summary class="cursor-pointer font-semibold text-primary text-sm">+ Add Intelligence</summary>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <label class="text-xs font-bold text-secondary/70 uppercase">Source <input id="nd-source" value="manual" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Source URL <input id="nd-url" placeholder="https://..." class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase md:col-span-2">Content <textarea id="nd-content" rows="3" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"></textarea></label>
        <label class="text-xs font-bold text-secondary/70 uppercase md:col-span-2">Note <input id="nd-note" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <div class="md:col-span-2"><button id="btn-add-data" class="px-4 py-2 bg-primary text-primary-fixed font-bold rounded-xl text-sm">Add</button> <span id="nd-fb" class="text-sm"></span></div>
      </div></details>`;

  el.querySelectorAll('.intel-content').forEach(div => {
    div.addEventListener('click', () => {
      div.classList.toggle('line-clamp-md');
      const indicator = div.nextElementSibling;
      if (indicator && indicator.classList.contains('expand-indicator')) {
        indicator.textContent = div.classList.contains('line-clamp-md') ? 'Clicca per espandere' : 'Clicca per comprimere';
      }
    });
  });
  el.querySelectorAll('.del-data').forEach(b => b.addEventListener('click', async () => {
    if (confirm('Delete this intelligence entry?')) {
      await deleteCompanyData(b.dataset.id);
      renderCompanyData(companyId, await getCompanyData(companyId));
    }
  }));
  document.getElementById('btn-add-data')?.addEventListener('click', async () => {
    const source = v('nd-source'); const content = v('nd-content');
    if (!source) { document.getElementById('nd-fb').textContent = 'Source required'; return; }
    try {
      await createCompanyData(companyId, { source, content: content||null, source_url: v('nd-url')||null, note: v('nd-note')||null });
      renderCompanyData(companyId, await getCompanyData(companyId));
    } catch(e) { document.getElementById('nd-fb').textContent = e.message; }
  });
}

function renderActivities(companyId, activities) {
  const el = document.getElementById('d-activities');
  if (!el) return;
  const tl = { email_sent:'Email', call:'Call', meeting:'Meeting', note:'Note', linkedin:'LinkedIn', other:'Other' };
  const rows = activities.map(a => `<tr class="hover:bg-surface-container-low transition-colors"><td class="px-4 py-3 text-sm">${a.activity_date?new Date(a.activity_date).toLocaleString():'—'}</td><td class="px-4 py-3 text-sm">${esc(tl[a.activity_type]||a.activity_type)}</td><td class="px-4 py-3 text-sm">${esc(a.subject||'')}</td><td class="px-4 py-3 text-sm">${esc(a.contact_name||'')}</td><td class="px-4 py-3"><button class="del-act text-error hover:text-red-800" data-id="${a.id}"><span class="material-symbols-outlined text-sm">delete</span></button></td></tr>`).join('');
  el.innerHTML = `<h2 class="text-xl font-headline font-bold text-primary mb-4">Activities (${activities.length})</h2>
    ${activities.length?`<table class="w-full text-left"><thead><tr class="bg-surface-container-low"><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Date</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Type</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Subject</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Contact</th><th class="px-4 py-3"></th></tr></thead><tbody class="divide-y divide-surface-container">${rows}</tbody></table>`:'<p class="text-secondary">No activities.</p>'}
    <details class="mt-4"><summary class="cursor-pointer font-semibold text-primary text-sm">+ Log Activity</summary>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <label class="text-xs font-bold text-secondary/70 uppercase">Type <select id="act-type" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"><option value="email_sent">Email</option><option value="call">Call</option><option value="meeting">Meeting</option><option value="linkedin">LinkedIn</option><option value="note">Note</option><option value="other">Other</option></select></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Subject <input id="act-subject" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Contact <input id="act-contact" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Date <input id="act-date" type="datetime-local" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase md:col-span-2">Description <textarea id="act-desc" rows="2" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"></textarea></label>
        <div class="md:col-span-2"><button id="btn-add-act" class="px-4 py-2 bg-primary text-primary-fixed font-bold rounded-xl text-sm">Log</button> <span id="act-fb" class="text-sm"></span></div>
      </div></details>`;
  el.querySelectorAll('.del-act').forEach(b => b.addEventListener('click', async () => { if (confirm('Delete?')) { await deleteActivity(b.dataset.id); renderActivities(companyId, await getActivities(companyId)); } }));
  document.getElementById('btn-add-act')?.addEventListener('click', async () => {
    try { await createActivity(companyId, { activity_type:v('act-type'), subject:v('act-subject')||null, contact_name:v('act-contact')||null, activity_date:v('act-date')||null, description:v('act-desc')||null }); renderActivities(companyId, await getActivities(companyId)); } catch(e) { document.getElementById('act-fb').textContent=e.message; }
  });
}

function renderContacts(companyId, contacts) {
  const el = document.getElementById('d-contacts');
  if (!el) return;
  const rows = contacts.map(ct => `<tr class="hover:bg-surface-container-low transition-colors"><td class="px-4 py-3 text-sm font-medium">${esc(ct.name)}</td><td class="px-4 py-3 text-sm">${esc(ct.role||'')}</td><td class="px-4 py-3 text-sm">${esc(ct.email||'')}</td><td class="px-4 py-3 text-sm">${esc(ct.phone||'')}</td><td class="px-4 py-3 text-sm">${ct.linkedin_url?`<a href="${esc(ct.linkedin_url)}" target="_blank" class="text-primary hover:underline">LinkedIn</a>`:'—'}</td><td class="px-4 py-3"><button class="del-ct text-error hover:text-red-800" data-id="${ct.id}"><span class="material-symbols-outlined text-sm">delete</span></button></td></tr>`).join('');
  el.innerHTML = `<h2 class="text-xl font-headline font-bold text-primary mb-4">Contacts (${contacts.length})</h2>
    ${contacts.length?`<table class="w-full text-left"><thead><tr class="bg-surface-container-low"><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Name</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Role</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Email</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">Phone</th><th class="px-4 py-3 text-[10px] font-bold uppercase text-secondary/60">LinkedIn</th><th></th></tr></thead><tbody class="divide-y divide-surface-container">${rows}</tbody></table>`:'<p class="text-secondary">No contacts.</p>'}
    <details class="mt-4"><summary class="cursor-pointer font-semibold text-primary text-sm">+ Add Contact</summary>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <label class="text-xs font-bold text-secondary/70 uppercase">Name <input id="nc-name" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Role <input id="nc-role" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Email <input id="nc-email" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Phone <input id="nc-phone" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">LinkedIn <input id="nc-linkedin" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <label class="text-xs font-bold text-secondary/70 uppercase">Notes <input id="nc-notes" class="mt-1 w-full px-3 py-2 bg-surface-container-low border-none rounded-xl text-sm"/></label>
        <div class="md:col-span-2"><button id="btn-add-ct" class="px-4 py-2 bg-primary text-primary-fixed font-bold rounded-xl text-sm">Add</button> <span id="nc-fb" class="text-sm"></span></div>
      </div></details>`;
  el.querySelectorAll('.del-ct').forEach(b => b.addEventListener('click', async () => { if (confirm('Delete?')) { await deleteContact(b.dataset.id); renderContacts(companyId, await getContacts(companyId)); } }));
  document.getElementById('btn-add-ct')?.addEventListener('click', async () => {
    const name=v('nc-name'); if(!name){document.getElementById('nc-fb').textContent='Name required';return;}
    try { await createContact(companyId, {name, role:v('nc-role')||null, email:v('nc-email')||null, phone:v('nc-phone')||null, linkedin_url:v('nc-linkedin')||null, notes:v('nc-notes')||null}); renderContacts(companyId, await getContacts(companyId)); } catch(e) { document.getElementById('nc-fb').textContent=e.message; }
  });
}

function v(id) { return document.getElementById(id)?.value?.trim()||''; }
function esc(s) { if(!s) return ''; const d=document.createElement('div'); d.textContent=String(s); return d.innerHTML; }

function fmtEuro(v) {
  if (v == null) return '-';
  return '€ ' + Number(v).toLocaleString('it-IT');
}

function fmtDate(d) {
  if (!d) return '-';
  const dt = new Date(d);
  return isNaN(dt) ? '-' : dt.toLocaleDateString('it-IT');
}

function empLine(c) {
  if (c.employees_min != null && c.employees_max != null) {
    const emp = c.employees_max >= 10000 ? c.employees_min + '+' : c.employees_min + '-' + c.employees_max;
    return emp;
  }
  return '-';
}

function revProfitLine(c) {
  const parts = [];
  if (c.latest_revenue != null) parts.push(`<span class="font-semibold">Revenue:</span> ${fmtEuro(c.latest_revenue)}`);
  if (c.latest_profit != null) parts.push(`<span class="font-semibold">Profit:</span> ${fmtEuro(c.latest_profit)}`);
  if (!parts.length) return '';
  return `<p class="text-xs text-secondary mt-0.5">${parts.join(' | ')}</p>`;
}

function empCostLine(c) {
  const parts = [];
  parts.push(`<span class="font-semibold">Employees:</span> ${empLine(c)}`);
  if (c.latest_personnel_cost != null) parts.push(`<span class="font-semibold">Personnel Cost:</span> ${fmtEuro(c.latest_personnel_cost)}`);
  return `<p class="text-xs text-secondary mt-0.5">${parts.join(' | ')}</p>`;
}

function financialLine(c) {
  // kept for compatibility, no longer used in header
  return '';
}
