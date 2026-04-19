/**
 * SPA Router for Biogas CRM with Supabase auth.
 */
import { sb } from './supabase.js';
import { renderDashboard } from './views/dashboard.js';
import { renderCompanies } from './views/companies.js';
import { renderDetail } from './views/detail.js';
import { renderImport } from './views/import.js';
import { renderTopicSelector } from './components/topic-selector.js';
import { renderCrossSelling } from './views/cross-selling.js';

const routes = [
  { pattern: /^#\/company\/(\d+)$/, view: (id) => renderDetail(id) },
  { pattern: /^#\/companies$/,      view: () => renderCompanies() },
  { pattern: /^#\/import$/,         view: () => renderImport() },
  { pattern: /^#\/cross-selling$/,  view: () => renderCrossSelling() },
  { pattern: /^#\/dashboard$/,      view: () => renderDashboard() },
];

function showLogin() {
  document.getElementById('main-nav').classList.add('hidden');
  document.getElementById('app').innerHTML = `
    <div class="flex items-center justify-center min-h-[80vh]">
      <div class="bg-surface-container-lowest rounded-xl shadow-lg border border-outline-variant/20 p-8 w-full max-w-sm">
        <div class="flex items-center gap-2 mb-6">
          <span class="material-symbols-outlined text-primary text-2xl">energy_savings_leaf</span>
          <span class="text-xl font-bold font-headline text-primary">Biomassa</span>
        </div>
        <div class="flex flex-col gap-4">
          <label class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">
            Email
            <input id="login-email" type="email" class="mt-1 w-full px-3 py-2.5 bg-surface-container-low border-none rounded-xl text-sm" placeholder="email@example.com"/>
          </label>
          <label class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">
            Password
            <input id="login-password" type="password" class="mt-1 w-full px-3 py-2.5 bg-surface-container-low border-none rounded-xl text-sm" placeholder="••••••••"/>
          </label>
          <button id="btn-login" class="bg-primary text-on-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-xl hover:bg-primary/90 transition-colors mt-2">
            Login
          </button>
          <p id="login-error" class="text-[11px] text-error hidden"></p>
        </div>
      </div>
    </div>`;

  document.getElementById('btn-login').addEventListener('click', doLogin);
  document.getElementById('login-password').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
}

async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.classList.add('hidden');

  if (!email || !password) { errEl.textContent = 'Email and password required'; errEl.classList.remove('hidden'); return; }

  const { error } = await sb.auth.signInWithPassword({ email, password });
  if (error) { errEl.textContent = error.message; errEl.classList.remove('hidden'); return; }

  document.getElementById('main-nav').classList.remove('hidden');
  navigate();
}

function addLogoutButton() {
  const container = document.getElementById('nav-right');
  if (container && !document.getElementById('btn-logout')) {
    container.innerHTML = `<a id="btn-logout" href="#" class="text-emerald-100/70 hover:text-emerald-100 transition-colors tracking-wider uppercase text-[11px] font-bold">Logout</a>`;
    document.getElementById('btn-logout').addEventListener('click', async (e) => {
      e.preventDefault();
      await sb.auth.signOut();
      showLogin();
    });
  }
}

async function navigate() {
  const { data: { session } } = await sb.auth.getSession();
  if (!session) { showLogin(); return; }

  document.getElementById('main-nav').classList.remove('hidden');
  addLogoutButton();
  renderTopicSelector(document.getElementById('nav-links'));

  const hash = window.location.hash || '#/dashboard';
  document.querySelectorAll('#nav-links .nav-link:not(#btn-logout)').forEach(a => {
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
