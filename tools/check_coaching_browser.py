"""Self-owned disposable server; real UI, mocked Hevy/OpenRouter, phone and desktop."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/coaching';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:18129'

with (OUT/'preview.log').open('w',encoding='utf-8') as log:
    server=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.coaching_preview:app',
        '--host','127.0.0.1','--port','18129','--no-access-log'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(150):
            if server.poll() is not None: raise RuntimeError('Mock preview startup failed; see preview.log')
            try:
                with urllib.request.urlopen(URL+'/api/ai/conversations',timeout=1): break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Preview did not start.')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            for width,height in [(390,844),(1280,900)]:
                context=browser.new_context(viewport=dict(width=width,height=height))
                # Test the page without CDN/network dependencies; raw provider HTML still exercises sanitizer.
                context.route('https://**/*',lambda route: route.fulfill(content_type='text/javascript',body="window.marked={parse:s=>s}; window.Chart=class {static register(){} constructor(){this.destroy=()=>{};} };"))
                page=context.new_page();errors=[];calls=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:calls.append(r.url) if '/messages' in r.url else None)
                with page.expect_response(lambda r:r.url.endswith('/api/ai/conversations') and r.request.method=='GET'):
                    page.goto(URL+'/#ai')
                expect(page.locator('#ai-training-review')).to_be_enabled()
                page.locator('#ai-training-review').click()
                try:
                    expect(page.locator('#ai-chat-messages')).to_contain_text('Recorded sessions: 12.')
                except AssertionError:
                    print(json.dumps(dict(status=page.locator('#ai-chat-status').inner_text(),errors=errors,calls=calls)))
                    raise
                expect(page.locator('#ai-training-review')).to_be_enabled()
                expect(page.locator('#ai-evidence-date')).to_contain_text('12 sessions')
                assert page.locator('#ai-chat-messages a[href]').count()==1
                assert page.locator('#ai-chat-messages a[href]').get_attribute('href')=='https://pubmed.ncbi.nlm.nih.gov/19204579/'
                assert page.locator('#ai-chat-messages img').count()==0
                assert not page.evaluate('Boolean(window.unsafeAI)')
                expect(page.locator('#ai-chat-messages')).to_contain_text('unverified link')
                identity=page.locator('#ai-conversation-select').input_value()
                evidence=page.request.get(URL+'/api/ai/conversations/'+identity).json()['evidence']
                assert evidence['coverage']['sessions']==12
                assert evidence['exercises'][0]['exposure_count']==12
                page.locator('#ai-chat-input').fill('I want to focus on strength.')
                page.locator('#ai-chat-send').click()
                expect(page.locator('#ai-chat-send')).to_be_enabled()
                expect(page.locator('#ai-chat-messages')).to_contain_text('I want to focus on strength.')
                page.reload()
                expect(page.locator('#ai-chat-messages')).to_contain_text('I want to focus on strength.')
                recorded=page.request.get(URL+'/api/ai/conversations/'+identity).json()
                assert recorded['evidence']==evidence and len(recorded['turns'])==2
                page.locator('#ai-chat-input').fill('Please interrupt this response.')
                page.locator('#ai-chat-send').click()
                expect(page.locator('#ai-chat-status')).to_contain_text('Nothing was automatically retried.')
                count=len(calls)
                page.locator('#ai-review-reload').click()
                expect(page.locator('#ai-chat-messages')).to_contain_text('Recorded response status: interrupted')
                assert len(calls)==count
                page.locator('#ai-chat-context-toggle').click()
                expect(page.locator('#ai-chat-context-preview')).to_contain_text('matched_load_comparisons')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(OUT/f'review-{width}.png'),full_page=True)
                assert not errors,errors
                context.close()
            browser.close()
        print(json.dumps(dict(mocked_coaching='passed',viewports=[390,1280],provider_requests='mocked only',persistence='reload and follow-up',sanitization='verified references only',physical_device='not performed')))
    finally:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired: server.kill();server.wait(timeout=5)
