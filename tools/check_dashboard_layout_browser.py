"""Real charts and responsive navigation on self-owned, disposable mock data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/dashboard-layout'
OUT.mkdir(parents=True, exist_ok=True)
URL = 'http://127.0.0.1:18130'


def check_card_geometry(page, width):
    cards = page.locator('.dashboard-card').evaluate_all("""els => els.map(el => {
      const r = el.getBoundingClientRect();
      return {id:el.id,x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom};
    })""")
    by_id = {card['id']: card for card in cards}
    ready, trend = by_id['dashboard-readiness-card'], by_id['today-readiness-trend-card']
    vf, pattern = by_id['dashboard-vf-card'], by_id['today-pattern-fatigue-card']
    current = by_id['dashboard-pattern-card']
    if width >= 1400:
        assert abs(ready['y']-current['y']) < 1 and ready['x'] < current['x'], (width,cards)
        assert abs(ready['width']-current['width']) < 1, (width,cards)
    else:
        assert current['y'] >= ready['bottom'], (width,cards)
        assert abs(current['width']-trend['width']) < 1, (width,cards)
    assert trend['y'] >= max(ready['bottom'],current['bottom']), (width,cards)
    assert trend['width'] == by_id['dashboard-recent-card']['width'], (width,cards)
    assert current['height'] < 320, (width,cards)
    assert min(vf['y'],pattern['y']) >= trend['bottom'], (width,cards)
    assert by_id['dashboard-recent-card']['y'] >= max(vf['bottom'],pattern['bottom']), (width,cards)
    if width >= 700:
        # Main keeps the variable-length recommendation inside Readiness.
        # Check that the score and action area stays compact independently.
        recommendation = page.locator('#daily-coach-review').bounding_box()
        recommendation_height = recommendation['height'] if recommendation else 0
        assert ready['height'] - recommendation_height < 240 and trend['height'] >= 380, (width,cards)
        assert page.locator('.dashboard-card').evaluate_all("""els => els.every(el =>
          el.scrollHeight <= el.clientHeight + 2 && el.scrollWidth <= el.clientWidth + 2)"""), width
    if width >= 2000:
        assert abs(vf['y']-pattern['y']) < 1 and abs(vf['height']-pattern['height']) < 1, cards
        assert abs(vf['width']-pattern['width']) < 1 and vf['width'] >= 800, cards
    else:
        assert pattern['y'] >= vf['bottom'], (width,cards)
        assert abs(vf['width']-trend['width']) < 1, (width,cards)


with (OUT / 'preview.log').open('w', encoding='utf-8') as log:
    server = subprocess.Popen(
        [sys.executable, '-X', 'utf8', '-m', 'uvicorn', 'tools.dashboard_preview:app',
         '--host', '127.0.0.1', '--port', '18130', '--no-access-log'], cwd=ROOT,
        stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        for _ in range(150):
            if server.poll() is not None:
                raise RuntimeError('Dashboard preview failed; see artifacts/dashboard-layout/preview.log')
            try:
                with urllib.request.urlopen(URL + '/api/sync/status', timeout=1):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Dashboard preview did not become ready')

        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width':2560,'height':1440}, color_scheme='dark')
            # Serve the shipped Chart.js for the host's matching CDN import;
            # no external network or fake chart renderer is involved.
            def external(route):
                if '/chart.js@4.4.0/' in route.request.url:
                    code = (ROOT/'rackbook/static/vendor/chart-4.4.0.umd.js').read_text(encoding='utf-8')
                    route.fulfill(body=code+'\nChart.defaults.animation=false;', content_type='text/javascript')
                else:
                    route.fulfill(content_type='text/javascript',body='window.marked={parse:s=>s};')
            context.route('https://**/*', external)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(URL + '/')
            prompt = page.get_by_role('button', name='Check in', exact=True)
            dialog = page.get_by_role('dialog', name='Daily Check-in')
            workout = page.locator('#dashboard-readiness-card').get_by_role('link', name='Log Workout')
            expect(prompt).to_be_visible()
            expect(dialog).to_be_hidden()
            expect(workout).to_be_hidden()
            expect(page.locator('#dashboard-readiness-summary')).not_to_contain_text('No check-in')
            assert page.locator('#checkin-prompt-banner').evaluate("""prompt => {
              const [explanation, action] = [...prompt.children].map(el => el.getBoundingClientRect());
              return action.x - explanation.right <= 16 && action.x >= explanation.right;
            }""")
            expect(page.get_by_role('table', name='Pattern stress').get_by_role('row')).to_have_count(5)
            for width, height in [(390, 844), (1440, 900)]:
                page.set_viewport_size({'width': width, 'height': height})
                if width < 1100:
                    expect(workout).to_be_visible()
                    expect(workout).to_have_attribute('href', '/training/log')
                    assert workout.bounding_box()['height'] >= 44
                    check_card_geometry(page, width)
                    page.screenshot(path=str(OUT/'dashboard-missing-390.png'),animations='disabled')
                else:
                    expect(workout).to_be_hidden()
                prompt.focus()
                page.keyboard.press('Enter')
                expect(dialog).to_be_visible()
                close = dialog.get_by_role('button', name='Close', exact=True)
                submit = dialog.get_by_role('button', name='Submit Check-in')
                expect(close).to_be_focused()
                page.keyboard.press('Shift+Tab')
                expect(submit).to_be_focused()
                page.keyboard.press('Tab')
                expect(close).to_be_focused()
                page.keyboard.press('Tab')
                expect(dialog.locator('#ci-date')).to_be_focused()
                page.keyboard.press('Escape')
                expect(dialog).to_be_hidden()
                expect(prompt).to_be_focused()
                prompt.click()
                close.click()
                expect(dialog).to_be_hidden()
                expect(prompt).to_be_focused()
                prompt.click()
                page.mouse.click(4, 4)
                expect(dialog).to_be_hidden()
                expect(prompt).to_be_focused()
            page.set_viewport_size({'width':2560,'height':1440})
            page.wait_for_function('todayReadinessChart && _dashboardVfChart && todayPatternFatigueChart')
            assert page.locator('#dashboard-recent-card .recent-session-item').count() == 7
            assert page.evaluate("getComputedStyle(document.querySelector('.dashboard-wrap')).gridTemplateColumns.split(' ').length") == 2
            check_card_geometry(page, 2560)
            expect(page.locator('#hostSidebar')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            expected = page.request.get(URL + '/api/readiness/combined-history?days=7').json()
            expected_points = [row.get('smoothed_score') if row.get('data_sufficient') else None for row in expected]
            actual = page.evaluate('todayReadinessChart.data.datasets[0].data')
            assert actual == expected_points, (actual, expected_points)
            assert None in actual, 'Missing monitoring must remain a chart gap'
            assert any(value is not None for value in actual), 'Fixture must include observed trend data'
            assert page.evaluate('todayReadinessChart.data.datasets[0].spanGaps') is False
            page.screenshot(path=str(OUT/'dashboard-desktop-2560.png'),animations='disabled')
            page.get_by_role('button',name='8 Weeks',exact=True).last.click()
            expect(page.locator('#dashboard-vf-range-btns [data-dashboard-vf-range="8"]')).to_have_class('btn btn-secondary active')
            page.wait_for_function('_dashboardVfChart && _dashboardVfChart.canvas.isConnected && document.getElementById("dashboard-vf-note").textContent.length > 0')
            page.locator('#theme-toggle [data-theme-btn="light"]').click()
            expect(page.locator('html')).to_have_attribute('data-theme','light')
            page.wait_for_function('todayReadinessChart && _dashboardVfChart && _dashboardVfChart.canvas.isConnected && document.getElementById("dashboard-vf-note").textContent.length > 0')
            assert page.evaluate('todayReadinessChart.data.datasets[0].data') == expected_points
            page.screenshot(path=str(OUT/'dashboard-desktop-light.png'),animations='disabled')
            page.locator('#theme-toggle [data-theme-btn="dark"]').click()

            # Exercise the actual renderer with a populated, synthetic summary as well
            # as the initial missing-check-in state. No model calculation is replaced.
            page.wait_for_function('_dashboardVfChart && _dashboardVfChart.canvas.isConnected && document.getElementById("dashboard-vf-note").textContent.length > 0')
            # Keep the browser-only fixture in the cached payload so a pending
            # theme refresh reads the same summary instead of replacing it.
            page.route('**/api/readiness/today', lambda route: route.fulfill(json={}))
            page.evaluate("""async () => {
              const payload=await ensureTrainingLoadPayload();
              payload.today={...payload.today,checkin_exists:true,
                recommendation_v2:{data_sufficient:true,smoothed_score:6,
                  training_state_label:'Increase',training_state:'increase',
                  training_state_detail:'Below baseline - good time to add volume or intensity',
                  subjective_score:2.6,objective_score:9.7,combined_score:4}};
              await loadTrainingLoadCard();
              await checkTodayReadiness();
            }""")
            expect(prompt).to_be_hidden()
            page.unroute('**/api/readiness/today')
            page.wait_for_function('_dashboardVfChart && _dashboardVfChart.canvas.isConnected && document.getElementById("dashboard-vf-note").textContent.length > 0')
            expect(page.locator('.readiness-breakdown-item')).to_have_count(3)
            expect(page.locator('#dashboard-readiness-summary .readiness-score')).to_have_text('6.0 / 20')
            check_card_geometry(page, 2560)
            page.screenshot(path=str(OUT/'dashboard-chart-focus-2560.png'),animations='disabled')
            for width, height, columns in [(2000,1200,2),(1999,1200,2),(1920,1080,2),(1900,1080,2),(1899,1080,2),(1500,1000,2),(1400,900,2),(1399,900,2),(1280,900,2),(1200,900,2),(1199,900,2),
                                            (1100,900,2),(1099,900,2),(700,900,2),(699,900,1),
                                            (1024,768,2),(820,1180,2),(390,844,1),(320,700,1)]:
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_function('(n)=>getComputedStyle(document.querySelector(".dashboard-wrap")).gridTemplateColumns.split(" ").length===n',arg=columns)
                page.wait_for_timeout(100)
                check_card_geometry(page, width)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
                page.wait_for_function('todayReadinessChart.canvas.getBoundingClientRect().width <= todayReadinessChart.canvas.parentElement.clientWidth + 1')
                if width < 1100:
                    expect(page.locator('#hostSidebar')).to_be_hidden()
                    page.locator('#hostMenu').click()
                    expect(page.locator('#hostCloseMenu')).to_be_focused()
                    assert page.evaluate("document.querySelector('main').inert")
                    page.keyboard.press('Escape')
                    expect(page.locator('#hostMenu')).to_be_focused()
                    assert not page.evaluate("document.querySelector('main').inert")
                if width in (1500,820,390):
                    page.screenshot(path=str(OUT/f'dashboard-{width}.png'),full_page=True,animations='disabled')
            page.set_viewport_size({'width':1500,'height':1000})
            page.locator('#today-joint-card').evaluate("el=>{el.style.display='block';el.textContent='Mock joint advisory';}")
            joint=page.locator('#today-joint-card').bounding_box()
            grid=page.locator('.dashboard-wrap').bounding_box()
            assert abs(joint['width']-grid['width']) < 1
            page.locator('#today-joint-card').evaluate("el=>{el.style.display='none';el.textContent='';}")
            page.set_viewport_size({'width':390,'height':844})
            page.locator('#hostMenu').click()
            page.locator('#hostSidebar [data-tab="settings"]').click()
            expect(page.locator('#tab-settings')).to_have_class('tab-content active')
            assert page.url.endswith('/#settings')
            expect(page.locator('#hostMenu')).to_be_focused()
            page.reload()
            expect(page.locator('#tab-settings')).to_have_class('tab-content active')
            page.wait_for_function("document.getElementById('checkin-prompt-banner').style.display === 'flex'")
            expect(prompt).to_be_hidden()
            expect(dialog).to_be_hidden()
            page.locator('#hostMenu').click()
            page.locator('#hostSidebar [data-tab="dashboard"]').click()
            expect(page.locator('#tab-dashboard')).to_have_class('tab-content active')
            prompt.click()
            expect(page.locator('#ci-submit')).to_be_visible()
            dialog.locator('#ci-date').fill('2020-01-01')
            page.evaluate("location.hash = '#settings'")
            expect(page.locator('#tab-settings')).to_have_class('tab-content active')
            expect(dialog).to_be_hidden()
            page.locator('#hostMenu').click()
            expect(page.locator('#hostCloseMenu')).to_be_focused()
            page.locator('#hostSidebar [data-tab="dashboard"]').click()
            expect(prompt).to_be_visible()
            prompt.click()
            expect(dialog.locator('#ci-date')).to_have_value('2020-01-01')
            page.keyboard.press('Escape')
            expect(prompt).to_be_focused()
            # Header/sidebar never fall under the training service worker.
            assert page.evaluate('navigator.serviceWorker.controller===null')
            workout.click()
            expect(page.locator('h1')).to_contain_text('Log Workout')
            host_links = ['/', '/training/log', '/training/microcycles', '/training/recent',
                          '/training/progress', '/training/stress', '/training/rpe-charts',
                          '/static/docs.html', '/#settings']
            for link in host_links:
                assert page.locator(f'#loggerNav a[href="{link}"]').count() == 1, link
            assert not errors, errors
            print(json.dumps({'real_chartjs':'passed','desktop':'2560x1440 chart-focused two columns',
                              'tablet_phone':'two/one columns','range_theme_gaps':'preserved','compact_readiness_wide_charts':'passed',
                              'drawer_focus_hashes_checkin_training_links':'passed',
                              'browser_errors':errors,'physical_device':'not performed'}))
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
