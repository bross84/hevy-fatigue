/* The one definition of the app menu. Every logger page draws its menu from here.
   Monitoring pages inside the dashboard (/#tab) are separate in-page tabs; the dashboard's own
   sidebar stays hand-written for its tab buttons and badges, and a test keeps it identical. */
const AppMenu = (() => {
  const groups = [
    {name: 'Overview', items: [{label: 'Dashboard', href: '/'}, {label: 'AI Coach', href: '/#ai'}]},
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

  // Every page except Log and the dashboard: the same grouped list as Log's sidebar. Below 1100px it
  // slides out from a Menu button in the page header; from 1100px it stays open down the left side.
  function renderShell(nav) {
    renderSidebar(nav);
    if (nav.closest('#appNav')) return;
    const header = nav.parentElement;
    const aside = document.createElement('aside');
    aside.id = 'appNav';
    aside.className = 'app-shell-nav';
    aside.setAttribute('aria-label', 'Application navigation');
    const title = document.createElement('div');
    title.className = 'app-shell-title';
    const name = document.createElement('span');
    name.textContent = 'Hevy-Fatigue';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'close-x';
    close.setAttribute('aria-label', 'Close');
    close.textContent = '✕';
    title.append(name, close);
    aside.append(title, nav);
    const scrim = document.createElement('button');
    scrim.type = 'button';
    scrim.id = 'appNavScrim';
    scrim.setAttribute('aria-label', 'Close navigation');
    scrim.hidden = true;
    const menu = document.createElement('button');
    menu.type = 'button';
    menu.id = 'appMenuButton';
    menu.className = 'app-menu-button';
    menu.textContent = 'Menu';
    menu.setAttribute('aria-controls', aside.id);
    menu.setAttribute('aria-expanded', 'false');
    header.append(menu);
    document.body.prepend(scrim);
    document.body.prepend(aside);
    document.body.classList.add('has-app-nav');
    const wide = window.matchMedia('(min-width:1100px)');
    const setOpen = (open, focus = true) => {
      aside.classList.toggle('is-open', open);
      scrim.hidden = !open;
      menu.setAttribute('aria-expanded', String(open));
      const main = document.querySelector('main, [data-app-main]');
      if (main) main.inert = open;
      if (open) close.focus();
      else if (focus && !wide.matches) menu.focus();
    };
    menu.addEventListener('click', () => setOpen(menu.getAttribute('aria-expanded') !== 'true'));
    close.addEventListener('click', () => setOpen(false));
    scrim.addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') setOpen(false);
    });
    wide.addEventListener('change', () => { if (wide.matches) setOpen(false, false); });
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
      '.app-shell-nav{display:none;box-sizing:border-box;background:var(--card);color:var(--text);border-right:1px solid var(--line,var(--border))}',
      '.app-shell-nav.is-open{display:block;position:fixed;inset:0 auto 0 0;width:min(300px,85vw);overflow-y:auto;z-index:1001}',
      '.app-shell-title{display:flex;align-items:center;justify-content:space-between;padding:16px 12px;font-weight:500}',
      '.app-shell-title .close-x{flex:none;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;min-height:44px;padding:0;margin:0;border:1px solid var(--line,var(--border));border-radius:12px;background:var(--card);color:var(--text);font:inherit;font-size:18px;line-height:1;cursor:pointer}',
      '.app-shell-nav .app-nav{display:grid;gap:4px;position:static;width:auto;height:auto;padding:0 12px 24px;margin:0;background:none;border:0;border-radius:0}',
      '.app-shell-nav .logger-nav-group{font-size:12px;color:var(--muted);margin:20px 12px 4px}',
      '.app-shell-nav .app-nav a{display:flex;align-items:center;justify-content:flex-start;flex:none;min-height:44px;padding:8px 12px;margin:0;border-radius:8px;color:var(--text);text-decoration:none;font-size:14px;font-weight:400}',
      '.app-shell-nav .app-nav a:hover{background:var(--soft,rgba(127,127,127,.12))}',
      '.app-shell-nav .app-nav a[aria-current=page]{background:var(--accent-soft,var(--accent-sub,rgba(127,160,230,.18)));color:var(--accent);font-weight:500}',
      ".app-shell-nav .app-nav a[aria-current=page]::after{content:'Current';margin-left:auto;font-size:12px;font-weight:400}",
      '#appNavScrim{position:fixed;inset:0;width:auto;min-height:0;padding:0;margin:0;background:rgba(0,0,0,.55);border:0;border-radius:0;z-index:1000}',
      '#appNavScrim[hidden]{display:none}',
      '.app-menu-button{flex:none;width:auto;min-height:44px;padding:0 16px;margin:0;border:1px solid var(--line,var(--border));border-radius:12px;background:var(--card);color:var(--text);font:inherit;font-size:14px;font-weight:600;cursor:pointer}',
      '@media (min-width:1100px){.app-shell-nav{display:block;position:fixed;inset:0 auto 0 0;width:224px;overflow-y:auto;z-index:30}.app-menu-button,.app-shell-title .close-x{display:none}body.has-app-nav :is(main,[data-app-main]){max-width:none;margin:0 0 0 224px}}',
      '@media (min-width:1900px){.app-shell-nav{width:240px}body.has-app-nav :is(main,[data-app-main]){margin-left:240px}}',
    ].join('\n');
    document.head.append(css);
  }

  function render(container, variant = container.dataset.appMenu) {
    container.replaceChildren();
    if (variant === 'sidebar') renderSidebar(container);
    else { style(); renderShell(container); }
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
