"""Workspace regressions against a self-owned, disposable tools.preview_app only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/logger-layout'
OUT.mkdir(parents=True, exist_ok=True)
URL = 'http://127.0.0.1:18129'

with (OUT / 'preview.log').open('w', encoding='utf-8') as log:
    server = subprocess.Popen(
        [sys.executable, '-X', 'utf8', '-m', 'uvicorn', 'tools.preview_app:app',
         '--host', '127.0.0.1', '--port', '18129', '--no-access-log'],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('Mock preview failed; see artifacts/logger-layout/preview.log')
            try:
                with urllib.request.urlopen(URL + '/api/sync/status', timeout=1):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Mock preview did not become ready')

        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 2560, 'height': 1440}, color_scheme='dark')
            context.route('https://**/*', lambda route: route.abort())
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(URL + '/training/log')
            page.get_by_role('button', name='Start an empty workout', exact=True).click()
            # This fixture is browser-local. All six movements use the preview's
            # mocked template, exercising independent instances of one movement.
            page.evaluate("""() => {
              draft.title = 'Full body · mocked layout acceptance';
              const titles = ['Squat (Barbell)','Bench Press (Barbell)',
                'Romanian Deadlift (Barbell)','Lat Pulldown (Cable)',
                'Leg Curl (Machine)','Crunch (Cable)'];
              draft.exercises = titles.map((title,i) => ({id:'layout-'+i,
                template_id:'sq',title,notes:'Original note '+i,collapsed:i!==1,
                ref:{...defaultRef(),autoWeights:false,state:{found:false,previous:[
                  {type:'normal',weight_lb:209.44,reps:5,rpe:7}]}},
                sets:Array.from({length:[6,5,3,3,3,3][i]},(_,j)=>({
                  type:i===0&&j<2||i===1&&j===0?'warmup':'normal',
                  kg:String([120,95,90,60,40,30][i]),reps:'5',rpe:'5',
                  arpe:i===0||i===1&&j<2?'5':'',done:i===0||i===1&&j<2,
                  manual:true,ts:i===0&&j===2}))}));
              SessionCapture.start(draft,'ad_hoc',rpeTable);
              renderWorkout();saveDraft();
              window.layoutBar=document.getElementById('bar');
            }""")
            expect(page.locator('#loggerProgress')).to_have_text('8 of 23 sets completed')
            page.locator('#motivation-level').select_option('2')
            with page.expect_response(lambda r:r.url.endswith('/session-checkins') and r.request.method=='POST') as checkin:
                page.locator('#confirmMotivation').click()
            assert checkin.value.ok,checkin.value.text()
            expect(page.locator('#loggerToolsTitle')).to_have_text('Bench Press (Barbell)')
            assert page.locator('#loggerLoader > .loader').count() == 1
            assert page.get_by_role('textbox', name='Weight in kilograms', exact=True).first.evaluate(
                '(e)=>e.getBoundingClientRect().width') == 80
            identity = page.evaluate('draft.client_workout_id')
            original_weights = page.evaluate('draft.exercises.map(e=>e.sets.map(s=>s.kg))')
            page.locator('#loggerNotes').fill('Bench note survives layout changes')
            expect(page.locator('#loggerNotes')).to_be_focused()
            # Changing selection must return the same loader, including when the
            # previous exercise is collapsed or shares the same template ID.
            page.locator('#loggerOutline button').nth(2).click()
            expect(page.locator('#loggerToolsTitle')).to_have_text('Romanian Deadlift (Barbell)')
            expect(page.locator('#loggerNotes')).to_have_value('Original note 2')
            assert page.locator('[data-exercise-id="layout-1"] .loader').count() == 1
            page.locator('#loggerOutline button').nth(1).click()
            expect(page.locator('#loggerNotes')).to_have_value('Bench note survives layout changes')
            expect(page.locator('[data-exercise-id="layout-1"] .exright')).to_be_visible()
            expect(page.locator('[data-exercise-id="layout-2"] .exright')).to_be_visible()
            # Reference refresh replaces a card; its detached loader must not be
            # orphaned and the selected movement must remain independent.
            page.evaluate('refreshCard(draft.exercises[1])')
            assert page.locator('#loggerLoader > .loader').count() == 1
            page.locator('#exercises [data-exercise-id="layout-1"] .tick').nth(2).click()
            expect(page.locator('#loggerProgress')).to_have_text('9 of 23 sets completed')
            assert page.evaluate('draft.exercises[1].sets[2].arpe') == '5'
            timer = page.evaluate("localStorage.getItem('training.restEnd')")
            assert timer
            page.locator('#exercises [data-exercise-id="layout-1"] .tick').nth(2).click()
            assert page.evaluate('draft.exercises.map(e=>e.sets.map(s=>s.kg))') == original_weights
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(OUT / 'logger-desktop-2560.png'))

            # Every breakpoint restores controls to their phone/tablet home;
            # no field, canonical weight, timer or UUID is reconstructed.
            for width, height in [(1920,1080),(1900,1080),(1899,1080),(1500,1000),(1280,900),(1100,900),(1099,900),(1024,768),(820,1180),(390,844)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                if width >= 1100:
                    boxes = page.locator('#exercises > .card').evaluate_all("""els => els.map(el => {
                      const r=el.getBoundingClientRect(); return {x:r.x,width:r.width};
                    })""")
                    assert len(boxes) == 6
                    assert max(b['width'] for b in boxes)-min(b['width'] for b in boxes) < 1, (width,boxes)
                    assert max(b['x'] for b in boxes)-min(b['x'] for b in boxes) < 1, (width,boxes)
                    assert max(b['width'] for b in boxes) <= 880, (width,boxes)
                    # Existing set grid keeps the weight column at 80px.
                    assert page.locator('#exercises .set input').first.evaluate('(el)=>el.getBoundingClientRect().width') <= 80

                if width < 1900:
                    expect(page.locator('#loggerTools')).to_be_hidden()
                    expect(page.locator('#exercises .loader')).to_have_count(6)
                    assert page.evaluate("document.getElementById('bar').parentElement===document.body")
                assert page.evaluate('draft.client_workout_id') == identity
                assert page.evaluate('draft.exercises.map(e=>e.sets.map(s=>s.kg))') == original_weights
                assert page.evaluate("localStorage.getItem('training.restEnd')") == timer
            page.locator('#loggerMenu').click()
            expect(page.locator('#loggerCloseMenu')).to_be_focused()
            assert page.evaluate("document.querySelector('main').inert")
            page.keyboard.press('Escape')
            expect(page.locator('#loggerMenu')).to_be_focused()
            assert not page.evaluate("document.querySelector('main').inert")
            page.set_viewport_size({'width':2560,'height':1440})
            assert page.evaluate("document.getElementById('bar')===window.layoutBar")
            assert page.locator('#loggerLoader > .loader').count() == 1
            page.evaluate('restStop()')
            # Reorder the actual draft/DOM using the existing grip drag.
            page.evaluate('draft.exercises.forEach(e=>e.collapsed=true);renderWorkout()')
            page.evaluate('window.scrollTo(0,0)')
            grips = page.locator('#exercises .grip')
            start, end = grips.nth(5).bounding_box(), grips.nth(0).bounding_box()
            page.evaluate("window.layoutDragEvents=[];document.addEventListener('pointerdown',e=>layoutDragEvents.push([e.type,e.target.className]),true);document.addEventListener('pointerup',e=>layoutDragEvents.push([e.type,e.target.className]),true)")
            page.mouse.move(start['x']+10,start['y']+10)
            page.mouse.down()
            page.mouse.move(end['x']+10,end['y']-24,steps=40)
            page.mouse.up()
            assert page.evaluate('draft.exercises[0].id') == 'layout-5', {
                'order':page.evaluate('draft.exercises.map(e=>e.id)'),
                'events':page.evaluate('layoutDragEvents'),'start':start,'end':end,
                'dom':page.locator('#exercises>.card').evaluate_all('(es)=>es.map(e=>e.dataset.exerciseId)')}
            expect(page.locator('#loggerOutline button').first).to_contain_text('Crunch')
            page.reload()
            expect(page.locator('#title')).to_have_value('Full body · mocked layout acceptance')
            assert page.evaluate('draft.client_workout_id') == identity
            assert page.evaluate("draft.exercises.find(e=>e.id==='layout-1').notes") == 'Bench note survives layout changes'
            # Freeze only in memory; no save/status request is made by this view.
            page.evaluate('draft.frozenSave={client_workout_id:draft.client_workout_id};LoggerLayout.update()')
            expect(page.locator('#loggerNotes')).to_be_disabled()
            page.evaluate('delete draft.frozenSave;LoggerLayout.update()')
            assert not errors, errors
            print(json.dumps({'desktop':'2560x1440','exercises':6,'sets':23,
                              'breakpoints':'390–2560','selection_notes_loader_reorder_reload':'passed',
                              'weights_identity_timer':'preserved','browser_errors':errors,
                              'real_account':'not used','physical_device':'not performed'}))
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
