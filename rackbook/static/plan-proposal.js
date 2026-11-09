/* AI Coach plan proposal card. Previewing writes nothing. Outside a weekly coaching call the only write
   is the explicit "Save as draft" click, which creates one new inactive draft microcycle. In a weekly
   coaching call (ADR 0002) the card instead offers "Accept as next week", which creates the next
   microcycle and makes it active on that tap, and Undo while it is untouched. No existing plan is
   edited here. Every piece of AI text is shown with textContent, never as HTML. */
const PlanProposal = (() => {
  const FENCE = 'plan-proposal-v1';
  const COMPLETE = new RegExp('```' + FENCE + '[ \\t]*\\r?\\n[\\s\\S]*?```', 'g');
  const OPEN = new RegExp('```' + FENCE + '[\\s\\S]*$');
  const NOTE = '\n\n*(Plan proposal shown below.)*\n\n';

  // Remove the machine-readable block from the text people read; found is true when one exists.
  function strip(text) {
    const value = String(text || '');
    const result = value.replace(COMPLETE, NOTE).replace(OPEN, NOTE);
    return {text: result, found: result !== value};
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function clear(node) {
    if (node.replaceChildren) node.replaceChildren(); else node.textContent = '';
  }

  async function post(path, body) {
    const response = await fetch(trainingUrl(path), {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body || {})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'The plan proposal request failed.');
    return data;
  }

  function list(items) {
    const ul = el('ul', 'plan-proposal-list');
    for (const item of items) ul.append(el('li', '', item));
    return ul;
  }

  function diffSection(diff) {
    const box = el('div', 'plan-proposal-diff');
    if (!diff.active_plan) {
      box.append(el('p', 'plan-proposal-note', 'No active microcycle to compare with.'));
      return box;
    }
    const lines = [...diff.added.map(t => 'Added: ' + t), ...diff.removed.map(t => 'Removed: ' + t),
      ...diff.changed.map(c => 'Changed: ' + c.title + ' · was ' + c.was + ' · now ' + c.now)];
    box.append(el('p', 'plan-proposal-note', 'Compared with your active microcycle, ' + diff.active_plan.name + ':'));
    box.append(lines.length ? list(lines) : el('p', 'plan-proposal-note', 'No movement differences.'));
    return box;
  }

  function render(card, result, request, options = {}) {
    clear(card);
    card.append(el('h4', 'plan-proposal-title', 'Proposed week' + (result.title ? ': ' + result.title : '')));
    if (!result.valid) {
      card.append(el('p', 'plan-proposal-note', 'This proposal cannot be saved as written:'));
      card.append(list(result.issues));
      return;
    }
    card.append(el('p', 'plan-proposal-rationale', result.rationale));
    if (result.call && result.call.matches) return renderCall(card, result, request, options);
    card.append(el('p', 'plan-proposal-note', 'Not applied. Saving creates an inactive draft that you review and activate yourself.'));
    describe(card, result);
    const status = el('p', 'plan-proposal-status');
    const button = el('button', 'plan-proposal-save', 'Save as draft');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      status.textContent = 'Saving draft…';
      try {
        const saved = await post('/api/plan-proposals/save', request);
        status.textContent = saved.already_saved ? 'Already saved as an inactive draft.' : 'Saved as an inactive draft.';
        const link = el('a', 'plan-proposal-open', 'Open the draft to review and activate');
        link.href = trainingUrl('/microcycles' + (saved.plan && saved.plan.id ? '?plan=' + encodeURIComponent(saved.plan.id) : ''));
        card.append(link);
      } catch (error) {
        status.textContent = (error.message || 'Could not save the draft.') + ' Nothing was changed.';
        button.disabled = false;
      }
    });
    card.append(button, status);
  }

  function describe(card, result, compare = true) {
    if (compare) card.append(diffSection(result.diff));
    for (const session of result.sessions) {
      card.append(el('h5', 'plan-proposal-session', session.name));
      card.append(list(session.exercises.map(e => e.title + ' — ' + e.summary + (e.notes ? ' (' + e.notes + ')' : ''))));
    }
  }

  function planLink(next) {
    const link = el('a', 'plan-proposal-open', 'Open ' + (next.name || 'next week') + ' in the builder');
    link.href = trainingUrl('/microcycles?plan=' + encodeURIComponent(next.plan_id));
    return link;
  }

  const callPath = (options, tail) => '/api/weekly-call/' + encodeURIComponent(options.call.sourcePlanId) + tail;

  // Weekly coaching call: the proposal is a candidate next week that becomes active only on Accept.
  function renderCall(card, result, request, options) {
    const call = result.call, next = call.next, status = el('p', 'plan-proposal-status');
    const refresh = async () => {
      render(card, await post(callPath(options, '/preview'), request), request, options);
      if (options.onChange) options.onChange();
    };
    if (next) {
      card.append(el('p', 'plan-proposal-note', call.this_turn ? next.name + ' is your active microcycle, set up from this proposal.'
        : 'Next week is already set up' + (next.origin === 'repeat' ? ' with Run it back' : ' from another reply') + ': ' + next.name + '.'));
      if (next.can_undo) {
        const undo = el('button', 'plan-proposal-save', 'Undo');
        undo.type = 'button';
        undo.addEventListener('click', async () => {
          undo.disabled = true;
          status.textContent = 'Undoing…';
          try { await post(callPath(options, '/undo')); await refresh(); }
          catch (error) { status.textContent = (error.message || 'Could not undo.') + ' Nothing was changed.'; undo.disabled = false; }
        });
        card.append(undo, status);
      } else if (next.undo_problem) card.append(el('p', 'plan-proposal-note', next.undo_problem));
      card.append(planLink(next));
      return;
    }
    if (!call.source.finished) {
      describe(card, result, false);
      card.append(el('p', 'plan-proposal-note', 'The finished week has days to train again, so this cannot be set up as next week.'));
      return;
    }
    card.append(el('p', 'plan-proposal-note', 'Accept makes this your active microcycle, ' + call.next_name +
      '. Your finished week stays as it is, and you can undo it until you train its first day.'));
    describe(card, result, false);
    const button = el('button', 'plan-proposal-save', 'Accept as next week');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      status.textContent = 'Setting up next week…';
      try { await post(callPath(options, '/next-week'), request); await refresh(); }
      catch (error) { status.textContent = (error.message || 'Could not set up next week.') + ' Nothing was changed.'; button.disabled = false; }
    });
    card.append(button, status);
  }

  // Adds a card after the reply when it contains a proposal. Resolves to the card or null.
  // options.call = {sourcePlanId} when the reply belongs to that microcycle's weekly coaching call;
  // options.onChange runs after the next week is set up or undone.
  async function mount(host, {text, conversationId, turnId}, options = {}) {
    if (!strip(text).found) return null;
    const request = {text: String(text), conversation_id: conversationId, turn_id: turnId};
    const card = el('div', 'plan-proposal');
    card.append(el('p', 'plan-proposal-status', 'Checking the proposed week…'));
    host.append(card);
    try {
      const path = options.call ? callPath(options, '/preview') : '/api/plan-proposals/preview';
      render(card, await post(path, request), request, options);
    } catch (error) {
      clear(card);
      card.append(el('p', 'plan-proposal-status', (error.message || 'Could not check the proposal.') + ' Reload the saved review to try again.'));
    }
    return card;
  }

  // The reply as plain text with every machine block removed, for pages that show replies without Markdown.
  function plain(text) {
    let value = strip(text).text;
    if (typeof PlanChange !== 'undefined') value = PlanChange.strip(value).text;
    return value.replace(/\s*\*\((?:Plan proposal|Suggested plan change) shown below\.\)\*\s*/g, '\n\n').trim();
  }

  return {strip, mount, plain};
})();
