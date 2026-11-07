"""Real browser recovery regressions against a self-owned disposable mock app."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/phase1-recovery';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:18128'

with (OUT/'preview.log').open('w',encoding='utf-8') as log:
    server=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.preview_app:app',
        '--host','127.0.0.1','--port','18128','--no-access-log'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('Mock preview failed to start; see preview.log')
            try:
                with urllib.request.urlopen(URL+'/api/sync/status',timeout=1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Mock preview did not become ready')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            context.route('https://**/*',lambda route:route.abort())
            page=context.new_page();errors=[];dialogs=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def accept_dialog(dialog):
                dialogs.append(dialog.message);dialog.accept()
            page.on('dialog',accept_dialog)
            def local_draft():return page.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")
            def load():
                page.goto(URL+'/training/log')
                page.get_by_role('button',name='Load selected workout',exact=True).click()
                expect(page.locator('#title')).to_have_value('Mock Workout')
                page.locator('.mobile-set-gate button').first.click()
                page.locator('#motivation-level').select_option('2')
                with page.expect_response(lambda r:r.url.endswith('/session-checkins') and r.request.method=='POST'):
                    page.locator('#confirmMotivation').click()
                for button in page.locator('.set .tick').all():button.click()
            def save():
                page.locator('#finish').click()
                with page.expect_response(lambda r:r.url.endswith('/training/hevy/workouts') and r.request.method=='POST') as response:
                    page.locator('#confirmSave').click()
                return response.value
            # A stale plan fails business validation before any Hevy request.
            load();original=local_draft()['client_workout_id']
            # Preserve a legacy frozen request to exercise durable rejection and
            # correction even though new check-ins catch stale links before freeze.
            page.evaluate("const d=JSON.parse(localStorage.getItem('training.logDraft'));d.planned_session.mesocycle_id='missing-plan';d.frozenSave={client_workout_id:d.client_workout_id,title:d.title,start_time:d.startedAt,end_time:new Date().toISOString(),planned_session:d.planned_session,exercises:d.exercises.map(e=>({exercise_template_id:e.template_id,title:e.title,sets:e.sets.filter(s=>s.done).map(s=>({type:s.type,weight_kg:s.kg===''?null:Number(s.kg),reps:Number(s.reps),rpe:Number(s.arpe||s.rpe),ts:!!s.ts}))}))};localStorage.setItem('training.logDraft',JSON.stringify(d));")
            page.set_viewport_size({'width':820,'height':900})
            page.reload();expect(page.locator('#title')).to_have_value('Mock Workout')
            result=save().json();assert result['state']=='rejected',result
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('#finish')).to_be_hidden()
            expect(page.locator('#rest')).to_be_visible()
            correction=page.get_by_role('button',name='Correct rejected draft',exact=True)
            expect(correction).to_be_visible()
            page.reload();expect(correction).to_be_visible()  # Rejection survives reload.
            correction.click();page.wait_for_function("old=>JSON.parse(localStorage.getItem('training.logDraft')).client_workout_id!==old",arg=original)
            assert 'frozenSave' not in local_draft()
            page.get_by_role('button',name='Use as unplanned workout',exact=True).click()
            page.locator('#sessionMotivationHome > summary').click()
            with page.expect_response(lambda r:r.url.endswith('/session-checkins') and r.request.method=='POST'):
                page.locator('#confirmMotivation').click()
            page.locator('#title').fill('Corrected Mock Workout')
            result=save().json();assert result['state']=='complete',result
            expect(page.locator('#done')).to_be_visible()
            assert page.request.get(URL+'/training/workout-saves/'+original).json()['state']=='rejected'
            workouts=page.request.get(URL+'/training/hevy/workouts').json()['workouts']
            assert len(workouts)==1 and workouts[0]['title']=='Corrected Mock Workout'
            assert all(not plan['completed'] for plan in page.request.get(URL+'/training/api/mesocycles').json())
            # A malformed prior frozen request gets FastAPI field validation
            # before journal preparation. Correction discards it, not the sets.
            load();model_id=local_draft()['client_workout_id']
            page.evaluate("const d=JSON.parse(localStorage.getItem('training.logDraft'));d.frozenSave={client_workout_id:d.client_workout_id,title:d.title,start_time:d.startedAt,end_time:new Date().toISOString(),exercises:[{exercise_template_id:'sq',notes:{invalid:true},sets:[{type:'normal',weight_kg:100,reps:1,rpe:8}]}]};localStorage.setItem('training.logDraft',JSON.stringify(d));")
            page.set_viewport_size({'width':820,'height':900})
            page.reload();expect(page.locator('#title')).to_have_value('Mock Workout')
            response=save();assert response.status==422
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('#finish')).to_be_hidden()
            expect(correction).to_be_visible()
            page.reload();expect(correction).to_be_visible()
            correction.click();page.wait_for_function("old=>JSON.parse(localStorage.getItem('training.logDraft')).client_workout_id!==old",arg=model_id)
            result=save().json();assert result['state']=='complete',result
            expect(page.locator('#done')).to_be_visible()
            assert len(page.request.get(URL+'/training/hevy/workouts').json()['workouts'])==2
            before=page.request.get(URL+'/training/api/mesocycles').json()
            assert len(before[0]['completed'])==1
            # Unfinished editor fields survive reload and JSON transfer without
            # making them valid saved prescriptions or advancing a plan.
            page.goto(URL+'/training/microcycles');page.locator('#newPlan').click();page.locator('#addDay').click()
            page.get_by_role('button',name='+ Movement',exact=True).click()
            page.get_by_role('button',name='Squat (Barbell)',exact=True).click()
            page.get_by_role('spinbutton',name='Reps',exact=True).first.fill('')
            page.reload();expect(page.locator('#editor')).to_be_visible()
            expect(page.get_by_role('spinbutton',name='Reps',exact=True).first).to_have_value('')
            page.get_by_text('Transfer device draft',exact=True).click()
            with page.expect_download() as download:page.get_by_role('button',name='Export draft JSON',exact=True).click()
            file=OUT/'unfinished-editor.json';download.value.save_as(file)
            data=json.loads(file.read_text());assert data['data']['plan']['weeks'][0]['sessions'][0]['exercises'][0]['sets'][0]['reps'] is None
            # Exercise replacement confirmation against the existing local draft.
            page.get_by_label('Import draft JSON',exact=True).set_input_files(file)
            expect(page.locator('#editor')).to_be_visible()
            expect(page.get_by_role('spinbutton',name='Reps',exact=True).first).to_have_value('')
            assert any('Replace this device' in message for message in dialogs)
            assert page.request.get(URL+'/training/api/mesocycles').json()==before
            assert not errors,errors
            page.screenshot(path=str(OUT/'unfinished-editor-phone.png'),full_page=True)
            print(json.dumps({'stale_plan_correction':'passed','model_validation_correction':'passed',
                'remote_mock_workouts':2,'plan_completions':1,'unfinished_editor_transfer':'passed','browser_errors':errors}))
            browser.close()
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
