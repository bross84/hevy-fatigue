"""Daily save, personal chart range and persistent Coach discussion on mocked data."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/daily-coaching';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:18241'

with (OUT/'preview.log').open('w',encoding='utf-8') as log:
    server=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.daily_coaching_preview:app','--host','127.0.0.1','--port','18241','--no-access-log'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(150):
            if server.poll() is not None:raise RuntimeError('Preview startup failed')
            try:urllib.request.urlopen(URL+'/api/sync/status',timeout=1).close();break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Preview did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport=dict(width=390,height=844))
            def external(route):
                if '/chart.js@4.4.0/' in route.request.url:
                    route.fulfill(content_type='text/javascript',body=(ROOT/'rackbook/static/vendor/chart-4.4.0.umd.js').read_text(encoding='utf-8')+'\nChart.defaults.animation=false;')
                else:route.fulfill(content_type='text/javascript',body='window.marked={parse:s=>s};')
            context.route('https://**/*',external)
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            def calls():return page.request.get(URL+'/mock/daily-provider').json()['calls']
            page.goto(URL+'/')
            expect(page.locator('#ci-submit')).to_be_visible()
            page.locator('button[data-ci-field="ci-t"][data-value="2"]').click()
            plan=page.request.get(URL+'/training/api/mesocycles').json()
            with page.expect_response(lambda r:r.url.endswith('/api/readiness') and r.request.method=='POST') as saved:
                page.locator('#ci-submit').click()
            assert saved.value.ok,saved.value.text()
            expect(page.locator('#daily-coach-review')).to_contain_text('Saved interpretation.')
            expect(page.locator('#daily-coach-review')).to_contain_text('Tiredness 2; perceived recovery 0')
            assert calls()==1
            assert not page.evaluate('Boolean(window.unsafeAI)')
            expect(page.locator('#daily-coach-review img')).to_have_count(0)
            day=saved.value.json()['date']
            view=page.request.get(URL+'/api/ai/daily-reviews/'+day).json()
            monitoring=page.request.get(URL+'/api/diagnostics/snapshot').json()
            history=page.request.get(URL+'/api/readiness/combined-history?days=7').json()
            assert history[-1]['historical_range']['sufficient']
            expect(page.locator('#today-readiness-trend-card')).to_contain_text('Usual range')
            assert 'Optimal' not in page.locator('#today-readiness-trend-card').inner_text()
            page.wait_for_function('todayReadinessChart && todayReadinessChart.data.datasets.length===2')
            assert page.evaluate('todayReadinessChart.data.datasets[0].data')==[r['smoothed_score'] if r['data_sufficient'] else None for r in history]
            assert page.evaluate('todayReadinessChart.data.datasets[1].data')==[r['combined_score'] for r in history]
            assert page.evaluate('todayReadinessChart.options.scales.y.max')==20
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(OUT/'daily-phone.png'),full_page=True)
            page.reload();expect(page.locator('#daily-coach-review')).to_contain_text('Saved interpretation.')
            assert calls()==1
            page.get_by_role('link',name='Discuss with AI Coach',exact=True).click()
            expect(page.locator('#ai-evidence-date')).to_contain_text('Evidence captured')
            expect(page.locator('#ai-chat-messages')).to_contain_text('Tiredness 2')
            # Daily fixture replies to follow-up using the same frozen context.
            page.locator('#ai-chat-input').fill('What should I watch during my next session?')
            page.locator('#ai-chat-send').click()
            page.wait_for_function("document.getElementById('ai-chat-send').disabled===false")
            assert calls()==2
            assert len(page.request.get(URL+'/api/ai/conversations/'+view['id']).json()['turns'])==2
            page.reload();expect(page.locator('#ai-chat-messages')).to_contain_text('What should I watch')
            # Missing AI configuration must leave a successfully edited check-in intact.
            page.request.post(URL+'/mock/daily-provider?value=unavailable')
            page.goto(URL+'/#log');expect(page.locator('#log-wrap')).to_contain_text(day)
            page.locator('#log-wrap tbody tr').first.get_by_role('button',name='Edit').click()
            page.locator('#lv-t').fill('3')
            with page.expect_response(lambda r:r.url.endswith('/api/readiness/'+day) and r.request.method=='PUT') as edited:
                page.get_by_role('button',name='Save Changes',exact=True).click()
            assert edited.value.ok,edited.value.text()
            expect(page.locator('#daily-coach-review')).to_contain_text('Configure AI')
            edited_monitoring=page.request.get(URL+'/api/diagnostics/snapshot').json()
            page.goto(URL+'/')
            expect(page.locator('#daily-coach-review')).to_contain_text('Context saved.')
            assert page.request.get(URL+'/api/readiness/today').json()['tiredness']==3
            assert calls()==2
            assert page.request.get(URL+'/api/ai/conversations/'+view['id']).json()['evidence']==view['evidence']
            # An explicit request after configuring produces a new saved revision.
            page.request.post(URL+'/mock/daily-provider?value=interrupted')
            page.get_by_role('button',name='Interpret this check-in',exact=True).click()
            expect(page.locator('#daily-coach-review')).to_contain_text('Mock provider interrupted')
            assert calls()==3
            page.reload();expect(page.locator('#daily-coach-review')).to_contain_text('Response interrupted')
            assert calls()==3
            page.set_viewport_size(dict(width=1440,height=1000))
            page.locator('#theme-toggle [data-theme-btn="light"]').click()
            page.wait_for_function('todayReadinessChart && todayReadinessChart.canvas.isConnected')
            page.wait_for_function('_dashboardVfChart && _dashboardVfChart.canvas.isConnected && document.getElementById("dashboard-vf-note").textContent.length > 0')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(OUT/'daily-desktop-light.png'),full_page=True)
            assert page.request.get(URL+'/training/api/mesocycles').json()==plan
            # Only the explicit rating edit can change scores; restoring interpretations cannot.
            after=page.request.get(URL+'/api/diagnostics/snapshot').json()
            assert after==edited_monitoring
            assert after['training_load']==monitoring['training_load']
            assert not errors,errors
            context.close();browser.close()
        print(json.dumps(dict(daily_save='passed',personal_range='prior-only with raw overlay',persistence='reload and discussion',ai_calls=3,outage='check-in retained',programming='unchanged',providers='fully mocked')))
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
