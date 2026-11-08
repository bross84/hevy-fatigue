"""Mandatory check-in and weekly remote-coach workflow, all providers mocked."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/weekly-coaching';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:18239'

with (OUT/'preview.log').open('w',encoding='utf-8') as log:
    server=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.coaching_preview:app','--host','127.0.0.1','--port','18239','--no-access-log'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
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
            context.route('https://**/*',lambda route:route.fulfill(content_type='text/javascript',body="window.marked={parse:s=>s};window.Chart=class {static register(){} constructor(){this.destroy=()=>{};}};"))
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def calls():return page.request.get(URL+'/mock/ai-calls').json()['calls']
            def load():
                page.goto(URL+'/training/microcycles')
                page.get_by_role('link',name='Start next workout',exact=True).click()
            def checkin(level,note=''):
                page.locator('.mobile-set-gate button').first.click()
                page.locator('#motivation-level').select_option(str(level));page.locator('#motivation-note').fill(note)
                with page.expect_response(lambda r:r.url.endswith('/session-checkins') and r.request.method=='POST') as response:
                    page.locator('#confirmMotivation').click()
                assert response.value.ok,response.value.text()
            def save():
                for button in page.locator('.set .tick').all():button.click()
                page.locator('#finish').click()
                with page.expect_response(lambda r:r.url.endswith('/training/hevy/workouts') and r.request.method=='POST') as response:
                    page.locator('#confirmSave').click()
                result=response.value.json();assert result['state']=='complete',result
                expect(page.locator('#done')).to_be_visible()
                return result
            load()
            plan=page.request.get(URL+'/training/api/mesocycles').json()[0]
            initial_weeks=plan['weeks']
            before=page.request.get(URL+'/api/diagnostics/snapshot').json()
            expect(page.get_by_role('button',name='Mark set done',exact=True).first).to_be_disabled()
            expect(page.locator('.mobile-set-gate').first).to_contain_text('Confirm motivation')
            checkin(0,'Tired but excited for pull-ups')
            expect(page.locator('#weeklyOpeningReview')).to_contain_text('Before day 1 · complete')
            assert calls()==1
            assert page.request.get(URL+'/api/diagnostics/snapshot').json()==before
            draft=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")
            opening_id=draft['weekly_review_id']
            opening=page.request.get(URL+'/api/ai/conversations/'+opening_id).json()
            assert opening['evidence']['week_context']['current_checkin']['motivation']['level']==0
            assert opening['evidence']['week_context']['current_checkin']['motivation']['note']=='Tired but excited for pull-ups'
            page.reload();expect(page.locator('#weeklyOpeningReview')).to_contain_text('Before day 1 · complete')
            page.locator('#sessionMotivationHome > summary').click()
            expect(page.get_by_role('link',name='Discuss this week with AI Coach')).to_be_visible()
            assert calls()==1
            page.screenshot(path=str(OUT/'opening-phone.png'),full_page=True)
            save()
            load();expect(page.locator('#title')).to_have_value('Next Workout')
            checkin(2)
            assert calls()==1
            save()
            # The microcycle is finished, but nothing reviews it until the next check-in.
            page.goto(URL+'/training/microcycles')
            assert calls()==1
            second=page.request.post(URL+'/training/api/mesocycles',data=dict(name='Second microcycle',weeks=[dict(name='Week',sessions=[
                dict(id='b-one',name='Second Workout',exercises=[dict(exercise_template_id='sq',title='Squat (Barbell)',sets=[dict(reps=5,rpe=7)])])])]))
            assert second.ok,second.text()
            load();expect(page.locator('#title')).to_have_value('Second Workout')
            checkin(1)
            expect(page.locator('#microcycleClosingReview')).to_contain_text('Finished microcycle · complete')
            expect(page.locator('#weeklyOpeningReview')).to_contain_text('Before day 1 · complete')
            assert calls()==3  # the finished microcycle first, then the new microcycle's day 1
            draft=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")
            auto_closing_id=draft['closing_review_id']
            page.reload()
            expect(page.locator('#microcycleClosingReview')).to_contain_text('Finished microcycle · complete')
            assert calls()==3  # a reload never resends
            page.screenshot(path=str(OUT/'automatic-closing-phone.png'),full_page=True)
            save()
            page.goto(URL+'/training/microcycles');page.locator('#completedPlans').evaluate('(el)=>el.open=true')
            review=page.locator('a[href*="coaching_week='+plan['id']+'"]')
            expect(review).to_have_text('Review this microcycle with AI Coach');assert calls()==3
            review.click()
            expect(page.locator('#ai-chat-messages')).to_contain_text('Microcycle review')
            expect(page.locator('#ai-chat-send')).to_be_enabled()
            assert calls()==3  # the request opens the automatic review; it is not generated again
            closing_id=page.locator('#ai-conversation-select').input_value()
            assert closing_id==auto_closing_id
            closing=page.request.get(URL+'/api/ai/conversations/'+closing_id).json()
            week=closing['evidence']['week_context']
            assert week['saved_workout_count']==2 and week['manually_marked_count']==0
            assert len(week['actual_workouts'])==2 and week['opening_review_id']==opening_id
            assert week['opening_discussion']
            page.locator('#ai-chat-input').fill('Can we discuss changing accessories for next week?')
            page.locator('#ai-chat-send').click();expect(page.locator('#ai-chat-send')).to_be_enabled()
            page.reload();expect(page.locator('#ai-chat-messages')).to_contain_text('Can we discuss changing accessories')
            assert calls()==4
            assert len(page.request.get(URL+'/api/ai/conversations/'+closing_id).json()['turns'])==2
            final=next(p for p in page.request.get(URL+'/training/api/mesocycles').json() if p['id']==plan['id'])
            assert final['weeks']==initial_weeks
            assert len(final['completed'])==2
            # Skipping a day finishes the microcycle without counting as trained, and the next check-in reviews it.
            def make_plan(name,days):
                made=page.request.post(URL+'/training/api/mesocycles',data=dict(name=name,weeks=[dict(name='Week',sessions=[
                    dict(id=d,name=d.replace('-',' ').title(),exercises=[dict(exercise_template_id='sq',title='Squat (Barbell)',sets=[dict(reps=5,rpe=7)])]) for d in days])]))
                assert made.ok,made.text();return made.json()
            skip_plan=make_plan('Skip microcycle',['skip-one','skip-two'])
            after_plan=make_plan('After skip microcycle',['after-one'])
            assert page.request.post(URL+'/training/api/mesocycles/'+skip_plan['id']+'/sessions/skip-one/complete').ok
            page.goto(URL+'/training/log')
            page.get_by_label('Select microcycle').select_option(skip_plan['id'])
            expect(page.get_by_label('Select workout day')).to_have_value('skip-two')
            page.once('dialog',lambda dialog:dialog.accept('Pull-ups after day 1 of the next microcycle'))
            page.get_by_role('button',name='Skip this day',exact=True).click()
            expect(page.locator('#plannedStart')).to_contain_text('Microcycle complete')
            expect(page.get_by_label('Select workout day')).to_contain_text('Skipped')
            skipped=next(p for p in page.request.get(URL+'/training/api/mesocycles').json() if p['id']==skip_plan['id'])
            outcomes={c['session_id']:(c['outcome'],c['note'],c['hevy_workout_id']) for c in skipped['completed']}
            assert outcomes['skip-two']==('skipped','Pull-ups after day 1 of the next microcycle',None),outcomes
            assert outcomes['skip-one'][0]=='completed' and not skipped['active']
            assert calls()==4  # skipping alone starts no AI review
            page.get_by_label('Select microcycle').select_option(after_plan['id'])
            page.get_by_role('button',name='Load selected workout',exact=True).click()
            checkin(1)
            expect(page.locator('#microcycleClosingReview')).to_contain_text('Finished microcycle · complete')
            expect(page.locator('#weeklyOpeningReview')).to_contain_text('Before day 1 · complete')
            assert calls()==6  # the skipped microcycle's review, then the new microcycle's opening review
            skip_review=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")['closing_review_id']
            context=page.request.get(URL+'/api/ai/conversations/'+skip_review).json()['evidence']['week_context']
            assert context['plan_id']==skip_plan['id'] and context['skipped_count']==1 and context['manually_marked_count']==1
            assert context['skipped_sessions'][0]['note']=='Pull-ups after day 1 of the next microcycle'
            page.screenshot(path=str(OUT/'skip-day-phone.png'),full_page=True)
            page.set_viewport_size(dict(width=1280,height=900))
            page.screenshot(path=str(OUT/'closing-desktop.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            browser.close()
        print(json.dumps(dict(mandatory_checkin='passed',opening='once before day 1',closing='automatic at the next check-in, once, with saved discussion',skip_day='finishes a microcycle without counting as trained',ai_calls=6,fatigue='unchanged by check-in',programming='unchanged',providers='fully mocked')))
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
