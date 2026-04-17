import { sb } from '../supabase.js';

export function renderImport() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="bg-surface-container-lowest rounded-xl shadow-sm border border-outline-variant/10 p-5">
        <div class="flex items-center gap-2 mb-4">
          <span class="material-icons text-primary text-xl">business</span>
          <h2 class="text-sm font-bold uppercase tracking-widest text-on-surface">Import Companies</h2>
        </div>
        <p class="text-xs text-on-surface-variant mb-3">
          CSV columns: <code class="text-[10px] bg-surface-container px-1 py-0.5 rounded">vat_number, name, ateco_code, region, county, city, address, employees</code>
        </p>
        <div class="flex flex-col gap-3">
          <label class="flex items-center justify-center gap-2 border-2 border-dashed border-outline-variant/30 rounded-lg p-4 cursor-pointer hover:border-primary/50 transition-colors">
            <span class="material-icons text-on-surface-variant">upload_file</span>
            <span class="text-xs text-on-surface-variant" id="companies-label">Choose CSV file...</span>
            <input type="file" id="companies-file" accept=".csv" class="hidden"/>
          </label>
          <label class="flex items-center gap-2 text-xs text-on-surface-variant cursor-pointer select-none">
            <input type="checkbox" id="overwrite-check" class="accent-primary w-4 h-4"/>
            Overwrite existing companies
          </label>
          <button id="btn-import-companies" class="flex items-center justify-center gap-2 bg-primary text-on-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-lg hover:bg-primary/90 transition-colors">
            <span class="material-icons text-base">upload</span> Upload Companies
          </button>
        </div>
        <div id="companies-result" class="mt-3"></div>
      </div>
      <div class="bg-surface-container-lowest rounded-xl shadow-sm border border-outline-variant/10 p-5">
        <div class="flex items-center gap-2 mb-4">
          <span class="material-icons text-primary text-xl">description</span>
          <h2 class="text-sm font-bold uppercase tracking-widest text-on-surface">Import Intelligence Data</h2>
        </div>
        <p class="text-xs text-on-surface-variant mb-1">
          CSV columns: <code class="text-[10px] bg-surface-container px-1 py-0.5 rounded">vat_number, source, content, source_url, note</code>
        </p>
        <p class="text-[10px] text-on-surface-variant/60 mb-3">Append-only: existing data is never deleted.</p>
        <div class="flex flex-col gap-3">
          <label class="flex items-center justify-center gap-2 border-2 border-dashed border-outline-variant/30 rounded-lg p-4 cursor-pointer hover:border-primary/50 transition-colors">
            <span class="material-icons text-on-surface-variant">upload_file</span>
            <span class="text-xs text-on-surface-variant" id="data-label">Choose CSV file...</span>
            <input type="file" id="data-file" accept=".csv" class="hidden"/>
          </label>
          <button id="btn-import-data" class="flex items-center justify-center gap-2 bg-primary text-on-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-lg hover:bg-primary/90 transition-colors">
            <span class="material-icons text-base">upload</span> Upload Data
          </button>
        </div>
        <div id="data-result" class="mt-3"></div>
      </div>
    </div>`;

  document.getElementById('companies-file').addEventListener('change', e => {
    document.getElementById('companies-label').textContent = e.target.files[0]?.name || 'Choose CSV file...';
  });
  document.getElementById('data-file').addEventListener('change', e => {
    document.getElementById('data-label').textContent = e.target.files[0]?.name || 'Choose CSV file...';
  });
  document.getElementById('btn-import-companies').addEventListener('click', handleCompanies);
  document.getElementById('btn-import-data').addEventListener('click', handleData);
}

/** Simple CSV parser — handles quoted fields with commas and newlines */
function parseCSV(text) {
  const lines = []; let row = []; let field = ''; let inQuote = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuote) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuote = false;
      else field += c;
    } else {
      if (c === '"') inQuote = true;
      else if (c === ',') { row.push(field.trim()); field = ''; }
      else if (c === '\n' || (c === '\r' && text[i + 1] === '\n')) {
        row.push(field.trim()); field = '';
        if (row.some(f => f)) lines.push(row);
        row = [];
        if (c === '\r') i++;
      } else field += c;
    }
  }
  if (field || row.length) { row.push(field.trim()); if (row.some(f => f)) lines.push(row); }
  if (!lines.length) return [];
  const headers = lines[0];
  return lines.slice(1).map(r => {
    const obj = {};
    headers.forEach((h, i) => { obj[h] = r[i] || ''; });
    return obj;
  });
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file, 'utf-8');
  });
}

const COMPANY_COLS = ['vat_number','name','ateco_code','region','county','city','address','employees'];

async function handleCompanies() {
  const file = document.getElementById('companies-file').files[0];
  if (!file) { alert('Select a CSV file'); return; }
  const overwrite = document.getElementById('overwrite-check').checked;
  const el = document.getElementById('companies-result');
  el.innerHTML = '<p class="text-xs text-on-surface-variant animate-pulse">Importing...</p>';

  try {
    const text = await readFile(file);
    const rows = parseCSV(text);
    let inserted = 0, updated = 0, skipped = 0;
    const errors = [];
    const skippedDetails = [];

    for (const row of rows) {
      const vat = (row.vat_number || '').trim();
      const name = (row.name || '').trim();
      if (!vat || !name) { errors.push('Row missing vat_number or name'); continue; }

      const company = {};
      for (const col of COMPANY_COLS) {
        const val = (row[col] || '').trim();
        if (val && val !== '-') company[col] = val;
      }

      try {
        const { data: existing } = await sb.from('companies').select('id').eq('vat_number', vat).maybeSingle();
        if (existing) {
          if (overwrite) {
            const { vat_number, ...updates } = company;
            await sb.from('companies').update({ ...updates, updated_at: new Date().toISOString() }).eq('id', existing.id);
            updated++;
          } else {
            skipped++;
            skippedDetails.push({ vat_number: vat, name, reason: 'already exists' });
          }
        } else {
          await sb.from('companies').insert(company);
          inserted++;
        }
      } catch (e) { errors.push(`${vat}: ${e.message}`); }
    }

    el.innerHTML = `
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-[10px] font-bold bg-green-100 text-green-800 px-2 py-0.5 rounded">${inserted} inserted</span>
        <span class="text-[10px] font-bold bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded">${updated} updated</span>
        <span class="text-[10px] font-bold bg-gray-100 text-gray-600 px-2 py-0.5 rounded">${skipped} skipped</span>
      </div>
      ${errors.length ? `<p class="text-[10px] text-red-600 mt-1">Errors: ${errors.slice(0, 10).join(', ')}</p>` : '<p class="text-[10px] text-green-700 mt-1">Done</p>'}`;
  } catch (e) { el.innerHTML = `<p class="text-[10px] text-red-600">${esc(e.message)}</p>`; }
}

async function handleData() {
  const file = document.getElementById('data-file').files[0];
  if (!file) { alert('Select a CSV file'); return; }
  const el = document.getElementById('data-result');
  el.innerHTML = '<p class="text-xs text-on-surface-variant animate-pulse">Importing...</p>';

  try {
    const text = await readFile(file);
    const rows = parseCSV(text);
    let inserted = 0, skippedNoMatch = 0;
    const errors = [];

    // Build VAT → id lookup
    const { data: allCompanies } = await sb.from('companies').select('id,vat_number');
    const vatMap = {};
    for (const c of allCompanies) vatMap[c.vat_number] = c.id;

    const batch = [];
    for (const row of rows) {
      const vat = (row.vat_number || '').trim();
      if (!vat) { errors.push('Row missing vat_number'); continue; }
      const companyId = vatMap[vat];
      if (!companyId) { skippedNoMatch++; continue; }
      batch.push({
        company_id: companyId,
        source: (row.source || 'unknown').trim(),
        content: row.content || null,
        source_url: row.source_url || null,
        note: row.note || null,
      });
    }

    // Insert in chunks of 500
    for (let i = 0; i < batch.length; i += 500) {
      const chunk = batch.slice(i, i + 500);
      const { error } = await sb.from('company_data').insert(chunk);
      if (error) errors.push(error.message);
      else inserted += chunk.length;
    }

    el.innerHTML = `
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-[10px] font-bold bg-green-100 text-green-800 px-2 py-0.5 rounded">${inserted} imported</span>
        <span class="text-[10px] font-bold bg-gray-100 text-gray-600 px-2 py-0.5 rounded">${skippedNoMatch} VAT not found</span>
      </div>
      ${errors.length ? `<p class="text-[10px] text-red-600 mt-1">Errors: ${errors.slice(0, 5).join(', ')}</p>` : '<p class="text-[10px] text-green-700 mt-1">Done</p>'}`;
  } catch (e) { el.innerHTML = `<p class="text-[10px] text-red-600">${esc(e.message)}</p>`; }
}

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
