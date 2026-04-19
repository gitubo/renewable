import { sb } from '../supabase.js';
import { getSelectedTopicId, setSelectedTopicId } from '../state.js';

/**
 * Fetches topics and renders a <select> dropdown in the navbar.
 * Topics are shown hierarchically: root topics first, children indented.
 * Includes "Tutti i topic" option (value="" → null).
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
 */
export async function renderTopicSelector(navElement) {
  const { data: topics, error } = await sb
    .from('topics')
    .select('*')
    .order('parent_id', { ascending: true, nullsFirst: true })
    .order('name');

  if (error) {
    console.error('Failed to load topics:', error.message);
    return;
  }

  // Build hierarchical options: roots first, then their children indented
  const roots = topics.filter(t => t.parent_id === null);
  const children = topics.filter(t => t.parent_id !== null);

  const options = [];
  for (const root of roots) {
    options.push({ id: root.id, label: root.name });
    const kids = children.filter(c => c.parent_id === root.id);
    for (const kid of kids) {
      options.push({ id: kid.id, label: `\u00A0\u00A0${kid.name}` });
    }
  }

  const currentId = getSelectedTopicId();

  const select = document.createElement('select');
  select.id = 'topic-selector';
  select.className =
    'bg-emerald-900/60 text-emerald-100/70 text-[11px] font-bold uppercase tracking-wider ' +
    'border border-emerald-700/40 rounded-md px-2 py-1 outline-none ' +
    'focus:ring-1 focus:ring-emerald-400/50 cursor-pointer';

  // Default option
  const allOpt = document.createElement('option');
  allOpt.value = '';
  allOpt.textContent = 'Tutti i topic';
  if (!currentId) allOpt.selected = true;
  select.appendChild(allOpt);

  for (const opt of options) {
    const el = document.createElement('option');
    el.value = String(opt.id);
    el.textContent = opt.label;
    if (currentId && String(currentId) === String(opt.id)) el.selected = true;
    select.appendChild(el);
  }

  select.addEventListener('change', () => {
    const val = select.value;
    setSelectedTopicId(val === '' ? null : Number(val));
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });

  // Remove existing selector if re-rendered
  const existing = navElement.querySelector('#topic-selector');
  if (existing) existing.remove();

  navElement.appendChild(select);
}
