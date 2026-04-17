/**
 * SPA Router for Biogas CRM.
 */
import { renderDashboard } from './views/dashboard.js';
import { renderCompanies } from './views/companies.js';
import { renderDetail } from './views/detail.js';
import { renderImport } from './views/import.js';

const routes = [
  { pattern: /^#\/company\/(\d+)$/, view: (id) => renderDetail(id) },
  { pattern: /^#\/companies$/,      view: () => renderCompanies() },
  { pattern: /^#\/import$/,         view: () => renderImport() },
  { pattern: /^#\/dashboard$/,      view: () => renderDashboard() },
];

function navigate() {
  const hash = window.location.hash || '#/dashboard';
  document.querySelectorAll('#nav-links .nav-link').forEach(a => {
    const isActive = hash.startsWith(a.dataset.route);
    a.classList.toggle('text-emerald-300', isActive);
    a.classList.toggle('border-b-2', isActive);
    a.classList.toggle('border-emerald-300', isActive);
    a.classList.toggle('pb-1', isActive);
    a.classList.toggle('text-emerald-100/70', !isActive);
  });
  for (const route of routes) {
    const m = hash.match(route.pattern);
    if (m) { route.view(...m.slice(1)); return; }
  }
  window.location.hash = '#/dashboard';
}

window.addEventListener('hashchange', navigate);
window.addEventListener('DOMContentLoaded', navigate);
