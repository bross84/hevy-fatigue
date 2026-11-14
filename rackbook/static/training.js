/* All Rackbook-owned paths go through this one helper. */
function trainingUrl(path) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) throw new Error('Expected a training path');
  return path === '/training' || path.startsWith('/training/') ? path : '/training' + path;
}
function trainingUUID() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

/* Light/Dark: follow the choice saved on the host dashboard (localStorage "theme": light, dark or auto).
 * Training pages style dark mode with prefers-color-scheme rules, so a fixed choice rewrites those rules to always
 * (dark) or never (light) apply. "auto" or no choice leaves the phone's setting in charge. A page with its own theme
 * control (#themeSelect, the legacy settings page) keeps it. */
function trainingThemeChoice() {
  try { const t = localStorage.getItem('theme'); return t === 'light' || t === 'dark' ? t : null; } catch (e) { return null; }
}
function trainingApplyTheme(sheets) {
  const choice = trainingThemeChoice();
  if (!choice || document.getElementById('themeSelect')) return;
  document.documentElement.style.colorScheme = choice;
  const visit = rules => {
    for (const rule of rules) {
      if (rule.media && /prefers-color-scheme:\s*dark/.test(rule.media.mediaText)) rule.media.mediaText = choice === 'dark' ? 'all' : 'not all';
      else if (rule.media && /prefers-color-scheme:\s*light/.test(rule.media.mediaText)) rule.media.mediaText = choice === 'light' ? 'all' : 'not all';
    }
  };
  for (const sheet of sheets || document.styleSheets) { try { visit(sheet.cssRules); } catch (e) { /* not readable yet */ } }
  for (const meta of document.querySelectorAll('meta[name="theme-color"][media]')) {
    if (meta.media.includes(choice)) meta.removeAttribute('media'); else if (/prefers-color-scheme/.test(meta.media)) meta.remove();
  }
}
if (typeof document !== 'undefined' && typeof window !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    trainingApplyTheme();
    for (const link of document.querySelectorAll('link[rel="stylesheet"]')) link.addEventListener('load', () => trainingApplyTheme([link.sheet]));
  });
  window.addEventListener('load', () => trainingApplyTheme());
}
