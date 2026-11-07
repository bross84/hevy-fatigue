/* The one definition of the app menu. Every logger page draws its menu from here.
   Monitoring pages inside the dashboard (/#tab) are separate in-page tabs; the dashboard's own
   sidebar stays hand-written for its tab buttons and badges, and a test keeps it identical. */
const AppMenu = (() => {
  const groups = [
    {name: 'Overview', items: [{label: 'Dashboard', href: '/'}]},
    {name: 'Training', items: [
      {label: 'Log Workout', href: '/training/log'},
      {label: 'Plans', href: '/training/microcycles', also: ['/training/mesocycles']},
      {label: 'Recent', href: '/training/recent'},
      {label: 'Progress', href: '/training/progress'},
      {label: 'Stress', href: '/training/stress'},
      {label: 'RPE Charts', href: '/training/rpe-charts'},
    ]},
    {name: 'Monitoring', items: [
      {label: 'Exercises', href: '/#exercise-metrics'},
      {label: 'Workouts', href: '/#workouts'},
      {label: 'Check-in History', href: '/#log'},
      {label: 'Patterns', href: '/#exercises'},
    ]},
    {name: 'Tools', items: [
      {label: 'AI Coach', href: '/#ai'},
      {label: 'Docs', href: '/static/docs.html'},
      {label: 'Settings', href: '/#settings', pinned: true},
    ]},
  ];

  function isCurrent(item) {
    if (item.href.includes('#')) return false;
    const path = location.pathname.replace(/\/+$/, '') || '/';
    return [item.href, ...(item.also || [])].includes(path);
  }

  function link(item) {
    const a = document.createElement('a');
    a.href = item.href;
    a.textContent = item.label;
    if (isCurrent(item)) a.setAttribute('aria-current', 'page');
    return a;
  }

  // Phone-friendly top bar: Dashboard, Training and pinned items (Settings) stay visible; the rest sit behind "More".
  function renderBar(container) {
    const extra = document.createElement('div');
    extra.className = 'app-nav-more';
    extra.id = 'appNavMore';
    extra.hidden = true;
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'app-nav-more-toggle';
    toggle.textContent = 'More';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', extra.id);
    toggle.addEventListener('click', () => {
      extra.hidden = !extra.hidden;
      toggle.setAttribute('aria-expanded', String(!extra.hidden));
    });
    for (const group of groups) {
      const always = group.name === 'Overview' || group.name === 'Training';
      for (const item of group.items) (always || item.pinned ? container : extra).append(link(item));
    }
    container.append(toggle, extra);
  }

  // Full grouped list for the logger's slide-out sidebar.
  function renderSidebar(container) {
    for (const group of groups) {
      const heading = document.createElement('span');
      heading.className = 'logger-nav-group';
      heading.textContent = group.name;
      container.append(heading);
      for (const item of group.items) container.append(link(item));
    }
  }

  function style() {
    if (document.getElementById('appMenuStyle')) return;
    const css = document.createElement('style');
    css.id = 'appMenuStyle';
    css.textContent = [
      '.app-nav .app-nav-more-toggle{display:flex;align-items:center;justify-content:center;flex:1 0 auto;min-height:40px;padding:6px 14px;border:0;border-radius:9px;background:transparent;color:var(--muted);font:inherit;font-size:14px;font-weight:550;cursor:pointer}',
      '.app-nav .app-nav-more-toggle:hover{background:var(--soft);color:var(--text)}',
      '.app-nav .app-nav-more-toggle[aria-expanded=true]{background:var(--accent-soft);color:var(--accent)}',
      '.app-nav .app-nav-more{display:flex;flex-wrap:wrap;gap:4px;flex:1 0 100%}',
      '.app-nav .app-nav-more[hidden]{display:none}',
      '@media (max-width:767px){.app-nav .app-nav-more-toggle{flex:1 0 28%;min-height:44px;padding:6px 8px;font-size:13px}}',
    ].join('\n');
    document.head.append(css);
  }

  function render(container, variant = container.dataset.appMenu) {
    container.replaceChildren();
    if (variant === 'sidebar') renderSidebar(container);
    else { style(); renderBar(container); }
  }

  function mount() {
    for (const container of document.querySelectorAll('[data-app-menu]')) render(container);
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
    else mount();
  }
  return {groups, render, mount};
})();
