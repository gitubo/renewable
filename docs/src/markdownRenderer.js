/**
 * Markdown Renderer module.
 *
 * Converts raw Markdown strings into sanitised HTML using
 * window.marked (CDN) and window.DOMPurify (CDN).
 *
 * Falls back to plain HTML-escaped text when the libraries
 * are unavailable or an unexpected error occurs.
 */

/**
 * HTML-escape a string using the DOM.
 * @param {string} s
 * @returns {string}
 */
export function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

/* ── Allowed tags & attributes for DOMPurify ────────────────────────── */

const ALLOWED_TAGS = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'ul', 'ol', 'li',
  'strong', 'em', 'a', 'code', 'pre', 'blockquote',
  'br', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
];

const ALLOWED_ATTR = ['href', 'target', 'rel'];

/* ── Main function ──────────────────────────────────────────────────── */

/**
 * Convert a Markdown string into safe HTML.
 *
 * @param {string} markdown – raw Markdown text
 * @returns {string} sanitised HTML (or empty string for blank input)
 */
export function renderMarkdown(markdown) {
  // Empty / blank input → empty string
  if (markdown == null || String(markdown).trim() === '') return '';

  // If CDN libs are missing, fall back to escaped text
  if (typeof window === 'undefined' || !window.marked || !window.DOMPurify) {
    return esc(markdown);
  }

  try {
    // Configure marked
    const renderer = new window.marked.Renderer();
    const originalLink = renderer.link;
    renderer.link = function (token) {
      const html = originalLink.call(this, token);
      // Add target and rel to every <a>
      return html
        .replace(/^<a /, '<a target="_blank" rel="noopener noreferrer" ');
    };

    window.marked.setOptions({
      gfm: true,
      breaks: true,
    });

    const rawHtml = window.marked.parse(String(markdown), { renderer });

    // Sanitise
    const cleanHtml = window.DOMPurify.sanitize(rawHtml, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
    });

    return cleanHtml;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('renderMarkdown error:', err);
    return esc(markdown);
  }
}
