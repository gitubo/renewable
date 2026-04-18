/**
 * API client for Biogas CRM — Supabase backend.
 * Drop-in replacement: same exported function signatures as the old fetch-based client.
 */
import { sb } from './supabase.js';

function err(e) { throw new Error(e?.message || e?.details || String(e)); }

// ── Dashboard ────────────────────────────────────────────────────────────

export async function getDashboard() {
  const { data, error } = await sb.rpc('get_dashboard_stats');
  if (error) err(error);
  return data;
}

export async function getDashboardCompanies(params = {}) {
  let q = sb.from('v_companies_full').select('id,name,city,region,crm_status,starred,relevance_score,data_count', { count: 'exact' });
  if (params.crm_status) q = q.eq('crm_status', params.crm_status);
  if (params.region) q = q.eq('region', params.region);
  q = q.order('starred', { ascending: false })
       .order('relevance_score', { ascending: false });
  const page = parseInt(params.page) || 1;
  const ps = parseInt(params.page_size) || 20;
  q = q.range((page - 1) * ps, page * ps - 1);
  const { data, error, count } = await q;
  if (error) err(error);
  return { total: count, page, page_size: ps, results: data.map(r => ({ ...r, score: r.relevance_score })) };
}

export async function getIntelligenceStats() {
  const { data, error } = await sb.rpc('get_intelligence_stats');
  if (error) err(error);
  return data;
}

export async function getIntelligenceCompanies(params = {}) {
  let q = sb.from('v_companies_full').select('id,name,vat_number,city,region,starred,crm_status,relevance_score,relevance_confidence,data_count', { count: 'exact' });
  q = q.eq('crm_status', 'new');
  if (params.source) {
    // Get company_ids that have this source
    const { data: srcIds } = await sb.from('company_data').select('company_id').eq('source', params.source);
    if (srcIds && srcIds.length) q = q.in('id', srcIds.map(r => r.company_id));
    else return { total: 0, page: 1, page_size: 20, results: [] };
  }
  if (params.min_score != null) q = q.gte('relevance_score', params.min_score);
  if (params.max_score != null) q = q.lte('relevance_score', params.max_score);
  if (params.min_data_count != null) q = q.gte('data_count', params.min_data_count);
  if (params.max_data_count != null) q = q.lte('data_count', params.max_data_count);

  const sortMap = { name: 'name', score: 'relevance_score', confidence: 'relevance_confidence', data_count: 'data_count', city: 'city' };
  const col = sortMap[params.sort_by] || 'relevance_score';
  q = q.order(col, { ascending: params.sort_order === 'asc' });

  const page = parseInt(params.page) || 1;
  const ps = parseInt(params.page_size) || 20;
  q = q.range((page - 1) * ps, page * ps - 1);

  const { data, error, count } = await q;
  if (error) err(error);
  return { total: count, page, page_size: ps, results: data.map(r => ({ ...r, score: r.relevance_score, confidence: r.relevance_confidence })) };
}

// ── Companies ────────────────────────────────────────────────────────────

export async function getCompanies(params = {}) {
  let q = sb.from('v_companies_full').select('*', { count: 'exact' });
  if (params.search) q = q.or(`name.ilike.%${params.search}%,vat_number.ilike.%${params.search}%`);
  if (params.region) q = q.eq('region', params.region);
  if (params.crm_status) q = q.eq('crm_status', params.crm_status);
  if (params.starred) q = q.eq('starred', true);
  if (params.min_score != null) q = q.gte('relevance_score', params.min_score);
  if (params.max_score != null) q = q.lte('relevance_score', params.max_score);
  if (params.emp_min != null) q = q.gte('employees_max', params.emp_min);
  if (params.emp_max != null) q = q.lte('employees_min', params.emp_max);

  const sortMap = { name: 'name', score: 'relevance_score', updated_at: 'updated_at', crm_status: 'crm_status', data_count: 'data_count', city: 'city', employees: 'employees_max' };
  const col = sortMap[params.sort_by] || 'name';
  q = q.order(col, { ascending: params.sort_order !== 'desc' });

  const page = parseInt(params.page) || 1;
  const ps = parseInt(params.page_size) || 50;
  q = q.range((page - 1) * ps, page * ps - 1);

  const { data, error, count } = await q;
  if (error) err(error);
  return { total: count, page, page_size: ps, results: data };
}

export async function getRegions() {
  const { data, error } = await sb.from('companies').select('region').neq('region', null).neq('region', '');
  if (error) err(error);
  return [...new Set(data.map(r => r.region))].sort();
}

export async function autocompleteCompanies(q) {
  const { data, error } = await sb.from('companies').select('id,name,vat_number').or(`name.ilike.%${q}%,vat_number.ilike.%${q}%`).limit(10);
  if (error) err(error);
  return data;
}

export async function getCompany(id) {
  const { data, error } = await sb.from('companies').select('*').eq('id', id).single();
  if (error) err(error);
  // Attach relevance
  const { data: rel } = await sb.from('company_scores').select('score,confidence,reasoning').eq('company_id', id).maybeSingle();
  data.relevance = rel || null;
  return data;
}

export async function createCompany(body) {
  const { score, ...companyData } = body;
  companyData.crm_status = 'new';
  const { data, error } = await sb.from('companies').insert(companyData).select().single();
  if (error) err(error);
  // Insert initial status
  const { data: statusRow } = await sb.from('statuses').select('id').eq('name', 'new').single();
  if (statusRow) await sb.from('company_statuses').insert({ company_id: data.id, status_id: statusRow.id, note: 'created' });
  // Insert score if provided
  if (score != null) {
    await sb.from('company_scores').insert({ company_id: data.id, score, confidence: 0.5, reasoning: 'manually set', model_used: 'manual' });
  }
  return data;
}

export async function updateCompany(id, body) {
  const { error } = await sb.from('companies').update({ ...body, updated_at: new Date().toISOString() }).eq('id', id);
  if (error) err(error);
  return { ok: true };
}

export async function toggleStar(id) {
  const { data: row } = await sb.from('companies').select('starred').eq('id', id).single();
  const newVal = !row.starred;
  await sb.from('companies').update({ starred: newVal }).eq('id', id);
  return { starred: newVal };
}

// ── Company Data ─────────────────────────────────────────────────────────

export async function getCompanyData(id) {
  const { data, error } = await sb.from('company_data').select('*').eq('company_id', id).order('created_at', { ascending: false });
  if (error) err(error);
  return data;
}

export async function createCompanyData(id, body) {
  const { data, error } = await sb.from('company_data').insert({ company_id: id, ...body }).select().single();
  if (error) err(error);
  return data;
}

export async function deleteCompanyData(id) {
  const { error } = await sb.from('company_data').delete().eq('id', id);
  if (error) err(error);
  return { ok: true };
}

// ── Contacts ─────────────────────────────────────────────────────────────

export async function getContacts(id) {
  const { data, error } = await sb.from('contacts').select('*').eq('company_id', id).order('name');
  if (error) err(error);
  return data;
}

export async function createContact(id, body) {
  const { data, error } = await sb.from('contacts').insert({ company_id: id, ...body }).select().single();
  if (error) err(error);
  return data;
}

export async function updateContact(id, body) {
  const { data, error } = await sb.from('contacts').update({ ...body, updated_at: new Date().toISOString() }).eq('id', id).select().single();
  if (error) err(error);
  return data;
}

export async function deleteContact(id) {
  const { error } = await sb.from('contacts').delete().eq('id', id);
  if (error) err(error);
  return { ok: true };
}

// ── Activities ───────────────────────────────────────────────────────────

export async function getActivities(id) {
  const { data, error } = await sb.from('activities').select('*').eq('company_id', id).order('activity_date', { ascending: false });
  if (error) err(error);
  return data;
}

export async function createActivity(id, body) {
  const { data, error } = await sb.from('activities').insert({ company_id: id, ...body }).select().single();
  if (error) err(error);
  return data;
}

export async function deleteActivity(id) {
  const { error } = await sb.from('activities').delete().eq('id', id);
  if (error) err(error);
  return { ok: true };
}

// ── Statuses ─────────────────────────────────────────────────────────────

export async function getStatuses() {
  const { data, error } = await sb.from('statuses').select('*').order('sort_order');
  if (error) err(error);
  return data;
}

export async function getCompanyStatusHistory(id) {
  const { data, error } = await sb.from('company_statuses').select('id,status_id,note,created_at,statuses(name,description)').eq('company_id', id).order('created_at', { ascending: false });
  if (error) err(error);
  return data.map(r => ({ ...r, status: r.statuses?.name, description: r.statuses?.description }));
}

export async function changeCompanyStatus(companyId, body) {
  const { data: statusRow, error: sErr } = await sb.from('statuses').select('id').eq('name', body.status).single();
  if (sErr) err(sErr);
  const { data, error } = await sb.from('company_statuses').insert({ company_id: companyId, status_id: statusRow.id, note: body.note || null }).select('id,status_id,note,created_at').single();
  if (error) err(error);
  await sb.from('companies').update({ crm_status: body.status, updated_at: new Date().toISOString() }).eq('id', companyId);
  return { ...data, status: body.status };
}