/* AI Coach plan proposal card. Previewing writes nothing. The only write is the explicit
   "Save as draft" click, which creates one new inactive draft microcycle; no plan is edited,
   activated or applied here. Every piece of AI text is shown with textContent, never as HTML. */
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
      body: JSON.stringify(body)});
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

  function render(card, result, request) {
    clear(card);
    card.append(el('h4', 'plan-proposal-title', 'Proposed week' + (result.title ? ': ' + result.title : '')));
    if (!result.valid) {
      card.append(el('p', 'plan-proposal-note', 'This proposal cannot be saved as written:'));
      card.append(list(result.issues));
      return;
    }
    card.append(el('p', 'plan-proposal-rationale', result.rationale));
    card.append(el('p', 'plan-proposal-note', 'Not applied. Saving creates an inactive draft that you review and activate yourself.'));
    card.append(diffSection(result.diff));
    for (const session of result.sessions) {
      card.append(el('h5', 'plan-proposal-session', session.name));
      card.append(list(session.exercises.map(e => e.title + ' — ' + e.summary + (e.notes ? ' (' + e.notes + ')' : ''))));
    }
    const status = el('p', 'plan-proposal-status');
    const button = el('button', 'plan-proposal-save', 'Save as draft');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      status.textContent = 'Saving draft…';
      try {
        const saved = await post('/api/plan-proposals/save', request);
        status.textContent = saved.already_saved ? 'Already saved as an inactive draft.' : 'Saved as an inactive draft.';
        const link = el('a', 'plan-proposal-open', 'Open microcycles to review and activate');
        link.href = trainingUrl('/microcycles');
        card.append(link);
      } catch (error) {
        status.textContent = (error.message || 'Could not save the draft.') + ' Nothing was changed.';
        button.disabled = false;
      }
    });
    card.append(button, status);
  }

  // Adds a card after the reply when it contains a proposal. Resolves to the card or null.
  async function mount(host, {text, conversationId, turnId}) {
    if (!strip(text).found) return null;
    const request = {text: String(text), conversation_id: conversationId, turn_id: turnId};
    const card = el('div', 'plan-proposal');
    card.append(el('p', 'plan-proposal-status', 'Checking the proposed week…'));
    host.append(card);
    try {
      render(card, await post('/api/plan-proposals/preview', request), request);
    } catch (error) {
      clear(card);
      card.append(el('p', 'plan-proposal-status', (error.message || 'Could not check the proposal.') + ' Reload the saved review to try again.'));
    }
    return card;
  }

  return {strip, mount};
})();
