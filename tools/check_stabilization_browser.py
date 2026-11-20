"""Workout stabilization acceptance, entirely disposable/mocked; never uses an account."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/stabilization'
URL = 'http://127.0.0.1:18138'


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/'preview.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.preview_app:app','--host','127.0.0.1','--port','18138','--no-access-log'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError('Preview exited')
                try:
                    urllib.request.urlopen(URL+'/training/health',timeout=1).close();break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Preview unavailable')
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,service_workers='block')
                context.route('https://**/*',lambda route:route.abort())
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(URL+'/training/log')
                page.get_by_role('button',name='Start an empty workout',exact=True).click()
                page.evaluate("""() => {
                  draft.exercises=[{id:'bench',template_id:'sq',title:'Bench Press (Barbell)',ref:{...defaultRef(),autoWeights:false,state:{found:false,previous_workout_start_time:'2026-11-13T17:00:00Z',previous:[
                    {type:'warmup',weight_kg:20,reps:5,rpe:null},{type:'normal',weight_kg:100,reps:8,rpe:7},
                    {type:'normal',weight_kg:100,reps:7,rpe:null}]}},sets:[
                    {type:'warmup',kg:'20',reps:'5',rpe:'',arpe:'',done:false,manual:true},
                    {type:'normal',kg:'100',reps:'8',rpe:'8',arpe:'',done:false,manual:true}]}];
                  renderWorkout();saveDraft();
                }""")
                expect(page.locator('.previous-session')).to_contain_text('Nov 13, 2026')
                expect(page.locator('.previous-inline').nth(1)).to_have_text('Last time: 100 kg × 8 @ 7')
                page.locator('.previous-extra summary').click()
                expect(page.locator('.previous-extra')).to_contain_text('100 kg × 7 @ ?')
                expect(page.locator('.set.next-working-set .kind')).to_have_text('W')
                page.locator('.set.next-working-set .tick').click()
                expect(page.locator('.set.next-working-set .kind')).to_have_text('1')
                expect(page.locator('#plateStrip')).to_contain_text('100 kg · 220 lb')
                page.screenshot(path=str(OUT/'phone-history.png'),full_page=True)
                page.locator('#plateStrip').click()
                expect(page.locator('.loadwhich:visible')).to_contain_text('100 kg · 220 lb')
                page.screenshot(path=str(OUT/'phone-plates.png'))
                page.locator('[data-panel="plates"] .ex-plates .panel-close').click()
                page.evaluate("draft.exercises[0].ref.weightUnit='lb';renderWorkout();saveDraft()")
                expect(page.locator('#plateStrip')).to_contain_text('100 kg · 220 lb')
                assert page.evaluate('draft.exercises[0].sets[0].kg') in ('20','100')
                assert page.evaluate("draft.exercises[0].sets.find(s=>s.type==='normal').kg")=='100'
                page.locator('#loggerMenu').click();page.locator('#loggerCloseMenu').click()
                expect(page.locator('#loggerMenu')).to_have_attribute('aria-expanded','false')
                page.evaluate('restStart(180,draft.exercises[0])')
                page.locator('#restPill').click()
                plus=page.get_by_role('button',name='+15',exact=True)
                for _ in range(4):plus.click(delay=10)
                assert page.evaluate('restTotal')==240
                assert plus.evaluate("e=>getComputedStyle(e).touchAction")=='manipulation'
                page.route('**/training/exercise-refs/*',lambda route:route.fulfill(status=503,json={'detail':'Mock unavailable'}))
                page.get_by_role('button',name='Keep 4:00 for Bench Press (Barbell)',exact=True).click()
                expect(page.get_by_role('button',name='Retry saving rest for Bench Press (Barbell)',exact=True)).to_be_visible()
                page.unroute('**/training/exercise-refs/*')
                page.get_by_role('button',name='Retry saving rest for Bench Press (Barbell)',exact=True).click()
                expect(page.get_by_role('button',name='4:00 kept for Bench Press (Barbell) ✓',exact=True)).to_be_visible()
                page.locator('.sheet-close').click()
                page.evaluate('restStop()')
                # Preview blocks create before a POST; status/recovery never silently reposts.
                page.evaluate("ExerciseCreate.open({catalog:[]})")
                expect(page.get_by_role('button',name='Create in Hevy')).to_be_disabled()
                page.locator('.exercise-create').get_by_role('button',name='Close',exact=True).click()
                options={'enabled':True,'types':['weight_reps'],'equipment':['barbell'],'muscles':['chest','triceps']}
                page.route('**/training/exercise-creation/options',lambda r:r.fulfill(json=options))
                page.route('**/training/exercise-creation/template/*',lambda r:r.fulfill(json={'title':'Bench Press','type':'weight_reps','equipment':'barbell','primary_muscle_group':'chest','secondary_muscle_groups':['triceps']}))
                calls=[]
                def create(route):
                    calls.append(route.request.post_data_json)
                    route.fulfill(json={'state':'uncertain','request_id':calls[-1]['request_id']})
                page.route('**/training/exercise-creation',create)
                page.evaluate("ExerciseCreate.open({catalog:[{id:'sq',title:'Bench Press'}],duplicate:true})")
                form=page.locator('.exercise-create')
                form.get_by_label('Start from').select_option('sq')
                expect(form.get_by_label('Exercise name')).to_have_value('Bench Press (copy)')
                form.get_by_label('Exercise name').fill('Low Pin Bench')
                form.get_by_role('button',name='Create in Hevy').click()
                expect(form.get_by_role('status')).to_contain_text('uncertain')
                expect(form.get_by_role('button',name='Create in Hevy')).to_be_disabled()
                form.get_by_role('button',name='Close',exact=True).click()
                page.reload()
                page.evaluate('ExerciseCreate.open({catalog:[]})')
                expect(page.get_by_role('button',name='Create in Hevy')).to_be_disabled()
                expect(page.get_by_label('Exercise name')).to_have_value('Low Pin Bench')
                page.route('**/training/exercise-creation/*/reconcile',lambda r:r.fulfill(json={'state':'complete','exercise_id':'new','title':'Low Pin Bench'}))
                page.get_by_role('button',name='Check creation status').click()
                expect(page.locator('.exercise-create')).to_have_count(0)
                assert len(calls)==1
                assert calls[0]['other_muscles']==['triceps']
                # The builder shares the same editor and exposes both entry points.
                page.goto(URL+'/training/mesocycles')
                page.get_by_role('button',name='Edit plan',exact=True).click()
                page.get_by_role('button',name='+ Movement',exact=True).click()
                page.get_by_role('button',name='Create exercise',exact=True).click()
                form=page.locator('.exercise-create')
                form.get_by_label('Exercise name').fill('New accessory')
                assert form.locator('[name="other_muscles"]').evaluate('e=>e.selectedOptions.length')==0
                created=[]
                page.unroute('**/training/exercise-creation')
                def created_exercise(route):
                    created.append(route.request.post_data_json)
                    route.fulfill(json={'state':'complete','exercise_id':'new','title':'New accessory'})
                page.route('**/training/exercise-creation',created_exercise)
                page.route('**/training/exercises',lambda r:r.fulfill(json=[{'id':'sq','title':'Squat (Barbell)'},{'id':'new','title':'New accessory'}]))
                page.screenshot(path=str(OUT/'phone-create.png'))
                before=page.evaluate('session().exercises.length')
                form.get_by_role('button',name='Create in Hevy').click()
                expect(form).to_have_count(0)
                assert page.evaluate('session().exercises.length')==before,'Creation must not automatically modify a plan'
                page.get_by_role('button',name='New accessory',exact=True).click()
                assert page.evaluate('session().exercises.at(-1).exercise_template_id')=='new'
                assert len(created)==1 and created[0]['other_muscles']==[]
                page.on('dialog',lambda dialog:dialog.accept())
                page.goto(URL+'/training/log');page.set_viewport_size({'width':1280,'height':900})
                page.screenshot(path=str(OUT/'desktop-history.png'),full_page=True)
                assert not errors,errors
                print(json.dumps({'history':'passed','kg_lb_equipment':'passed','warmup_focus':'passed','rest_retry':'passed','creation_recovery':'passed','phone':'emulated; physical acceptance outstanding','errors':errors}))
                browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)


if __name__=='__main__':run()
