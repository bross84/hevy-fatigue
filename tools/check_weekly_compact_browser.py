"""Mandatory check-in and the weekly coaching call (ADR 0002), all providers mocked."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/weekly-compact';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:18250'

with (OUT/'preview.log').open('w',encoding='utf-8') as log:
    server=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.weekly_compact_preview:app','--host','127.0.0.1','--port','18250','--no-access-log'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(150):
            if server.poll() is not None:raise RuntimeError('Preview startup failed')
            try:urllib.request.urlopen(URL+'/api/sync/status',timeout=1).close();break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Preview did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport=dict(width=390,height=844),service_workers='block')
            context.route('https://**/*',lambda route:route.fulfill(content_type='text/javascript',body="window.marked={parse:s=>s};window.Chart=class {static register(){} constructor(){this.destroy=()=>{};}};"))
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            posted=[]
            page.on('request',lambda request: posted.append(request.url) if request.method=='POST' else None)
            context.add_init_script("localStorage.setItem('ai_preferred_model','mock/model')")
            size=page.request.get(URL+'/mock/weekly-size').json()
            assert size['raw_chars']>79000,size
            page.goto(URL+'/')
            notice=page.locator('#weekly-review-notice')
            expect(notice).to_contain_text('Week complete — ready to review')
            assert page.request.get(URL+'/mock/ai-calls').json()['calls']==0
            notice.get_by_role('link',name='Review this week').click()
            expect(page.locator('#ai-chat-messages')).to_contain_text('Large completed week · Weekly coaching call')
            expect(page.locator('#ai-chat-send')).to_be_enabled()
            saved=page.request.get(URL+'/api/ai/conversations/'+size['call_id']).json()
            assert saved['turns'][0]['status']=='complete',saved
            assert saved['evidence']['week_context']['saved_workout_count']==3
            assert saved['evidence']['compact_details']['version']=='weekly-evidence-v2'
            assert len(saved['evidence']['week_context']['actual_workouts'])==3
            assert page.request.get(URL+'/mock/ai-calls').json()['calls']==1, posted
            page.goto(URL+'/training/log')
            expect(page.locator('#weeklyCall')).to_contain_text('Large completed week · Weekly coaching call')
            assert page.request.get(URL+'/mock/ai-calls').json()['calls']==1, posted
            assert not any(plan['active'] for plan in page.request.get(URL+'/training/api/mesocycles').json())
            page.goto(URL+'/')
            expect(notice).to_contain_text('Weekly review ready')
            for width in (390,1280):
                page.set_viewport_size(dict(width=width,height=900))
                notice.screenshot(path=str(OUT/f'ready-{width}.png'))
            notice.get_by_role('link',name='Read weekly review').click()
            expect(page.locator('#ai-chat-messages')).to_contain_text('Recorded sessions')
            assert page.request.get(URL+'/mock/ai-calls').json()['calls']==1, posted
            print(json.dumps(dict(raw_week_chars=size['raw_chars'],frozen_report_chars=len(json.dumps(saved['evidence'],ensure_ascii=False,separators=(',',':'))),provider_calls=1,dashboard='passed',logger='passed',plan_changes=0)))
            browser.close()
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
