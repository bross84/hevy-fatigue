"""AI week proposal: preview, explicit draft save and unchanged active plan, all providers mocked."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/plan-proposal'
OUT.mkdir(parents=True, exist_ok=True)
URL = 'http://127.0.0.1:18241'

with (OUT / 'preview.log').open('w', encoding='utf-8') as log:
    server = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn', 'tools.plan_proposal_preview:app',
                               '--host', '127.0.0.1', '--port', '18241', '--no-access-log'],
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        for _ in range(150):
            if server.poll() is not None:
                raise RuntimeError('Preview startup failed')
            try:
                urllib.request.urlopen(URL + '/api/sync/status', timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Preview did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport=dict(width=390, height=844))
            context.route('https://**/*', lambda route: route.fulfill(
                content_type='text/javascript',
                body="window.marked={parse:s=>s};window.Chart=class {static register(){} constructor(){this.destroy=()=>{};}};"))
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))

            def plans():
                return page.request.get(URL + '/training/api/mesocycles').json()

            before = plans()
            assert len(before) == 1 and before[0]['active']
            page.goto(URL + '/#ai')
            expect(page.locator('#ai-chat-send')).to_be_enabled()
            page.locator('#ai-chat-input').fill('Please propose a week for me.')
            page.locator('#ai-chat-send').click()
            card = page.locator('.plan-proposal').first
            expect(card).to_be_visible()
            expect(card).to_contain_text('Proposed week: Deload <b>week</b>')
            expect(card).to_contain_text('Not applied')
            expect(card).to_contain_text('Compared with your active microcycle, Mock preview plan')
            expect(card).to_contain_text('Squat (Barbell)')
            expect(page.locator('#ai-chat-messages')).not_to_contain_text('"version"')
            expect(page.locator('#ai-chat-messages')).to_contain_text('Plan proposal shown below.')
            assert page.evaluate('window.unsafeProposal') is None
            assert page.locator('.plan-proposal img, .plan-proposal b').count() == 0
            assert plans() == before, 'preview must not change any plan'
            page.screenshot(path=str(OUT / 'proposal-phone.png'), full_page=True)

            save = card.get_by_role('button', name='Save as draft')
            assert save.bounding_box()['height'] >= 40
            save.click()
            expect(card).to_contain_text('Saved as an inactive draft.')
            after = plans()
            assert len(after) == 2
            draft = next(plan for plan in after if plan['id'] != before[0]['id'])
            original = next(plan for plan in after if plan['id'] == before[0]['id'])
            assert not draft['active'] and not draft['archived'] and draft['name'] == 'Deload <b>week</b>'
            assert original == before[0], 'the active plan must be untouched'
            assert all(s['weight_kg'] is None for sess in draft['weeks'][0]['sessions'] for ex in sess['exercises'] for s in ex['sets'])

            # A reload restores the saved review; saving again reuses the first draft.
            page.reload()
            card = page.locator('.plan-proposal').first
            expect(card).to_be_visible()
            card.get_by_role('button', name='Save as draft').click()
            expect(card).to_contain_text('Already saved as an inactive draft.')
            assert len(plans()) == 2

            link = card.get_by_role('link', name='Open the draft to review and activate')
            expect(link).to_be_visible()
            draft = next(p for p in plans() if not p['active'])
            assert link.get_attribute('href') == '/training/microcycles?plan=' + draft['id']
            link.click()
            expect(page.locator('body')).to_contain_text('Deload <b>week</b>')
            assert page.locator('body b').count() == 0 or 'Deload' not in page.locator('body b').first.inner_text()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert [p['id'] for p in plans() if p['active']] == [before[0]['id']]
            assert page.evaluate('window.unsafeProposal') is None
            assert not errors, errors
            browser.close()
        print(json.dumps(dict(preview='read-only', save='one inactive draft, repeat reuses it',
                              active_plan='unchanged', markup='shown as text', providers='fully mocked')))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
