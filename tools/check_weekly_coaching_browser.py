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
                page.locator('#motivation-level').select_option(str(level));page.locator('#motivation-note').fill(note)
                with page.expect_response(lambda r:r.url.endswith('/session-checkins') and r.request.method=='POST') as response:
                    page.locator('#confirmMotivation').click()
                assert response.value.ok,response.value.text()
            def save():
                for button in page.get_by_role('button',name='Mark set done',exact=True).all():button.click()
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
            page.get_by_role('button',name='Mark set done',exact=True).first.click()
            expect(page.locator('#msg')).to_contain_text('Confirm your motivation')
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
            assert calls()==1
            page.screenshot(path=str(OUT/'opening-phone.png'),full_page=True)
            save()
            load();expect(page.locator('#title')).to_have_value('Next Workout')
            checkin(2)
            assert calls()==1
            save()
            page.goto(URL+'/training/microcycles');page.locator('#completedPlans').evaluate('(el)=>el.open=true')
            review=page.get_by_role('link',name='Review this week with AI Coach',exact=True)
            expect(review).to_be_visible();assert calls()==1
            review.click()
            expect(page.locator('#ai-chat-messages')).to_contain_text('End-of-week review')
            expect(page.locator('#ai-chat-send')).to_be_enabled()
            assert calls()==2
            closing_id=page.locator('#ai-conversation-select').input_value()
            closing=page.request.get(URL+'/api/ai/conversations/'+closing_id).json()
            week=closing['evidence']['week_context']
            assert week['saved_workout_count']==2 and week['manually_marked_count']==0
            assert len(week['actual_workouts'])==2 and week['opening_review_id']==opening_id
            assert week['opening_discussion']
            page.locator('#ai-chat-input').fill('Can we discuss changing accessories for next week?')
            page.locator('#ai-chat-send').click();expect(page.locator('#ai-chat-send')).to_be_enabled()
            page.reload();expect(page.locator('#ai-chat-messages')).to_contain_text('Can we discuss changing accessories')
            assert calls()==3
            assert len(page.request.get(URL+'/api/ai/conversations/'+closing_id).json()['turns'])==2
            final=page.request.get(URL+'/training/api/mesocycles').json()[0]
            assert final['weeks']==initial_weeks
            assert len(final['completed'])==2
            page.set_viewport_size(dict(width=1280,height=900))
            page.screenshot(path=str(OUT/'closing-desktop.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            browser.close()
        print(json.dumps(dict(mandatory_checkin='passed',opening='once before day 1',closing='manual with saved discussion',ai_calls=3,fatigue='unchanged by check-in',programming='unchanged',providers='fully mocked')))
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
