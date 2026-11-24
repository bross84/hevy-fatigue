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
OUT=ROOT/'artifacts/review-copy';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:18249'

with (OUT/'preview.log').open('w',encoding='utf-8') as log:
    server=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','tools.coaching_preview:app','--host','127.0.0.1','--port','18249','--no-access-log'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
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
            due=dict(source=dict(id='finished',name='KBR1.2'),call_id='review',next=None)
            view=dict(id='review',turns=[dict(id='turn',status='complete',response='Overall: A steady week, with limited evidence for some movements.\n\nTrends:\n• e1RM: Similar across comparable exposures.\n• Volume: No comparable prior-week total is available.\n• Stress: Recent load is elevated; that alone does not prove poor recovery.\n\nNext week: Keep the plan. There is not enough evidence to justify a change.')])
            mutations=[]
            page.on('request',lambda request: mutations.append(request.url) if request.method=='POST' and '/training/' in request.url else None)
            page.route('**/training/api/weekly-call',lambda route:route.fulfill(json=due))
            page.route('**/api/ai/week-reviews',lambda route:route.fulfill(json=view))
            page.route('**/api/ai/conversations/review',lambda route:route.fulfill(json=view))
            for width in (390,1280):
                page.set_viewport_size(dict(width=width,height=900))
                page.goto(URL+'/training/log')
                card=page.locator('#weeklyCall')
                expect(card).to_contain_text('Overall: A steady week')
                expect(card.get_by_role('button',name='Run it back',exact=True)).to_have_count(0)
                expect(card.get_by_role('link',name='Plan next week in builder')).to_have_attribute('href','/training/microcycles')
                expect(card.get_by_role('link',name='Continue in AI Coach')).to_have_attribute('href','/?coaching_conversation=review#ai')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                card.screenshot(path=str(OUT/f'review-{width}.png'))
            page.route('**/api/ai/week-reviews',lambda route:route.fulfill(status=400,json=dict(detail='The week is too large for automatic review; discuss it in AI Coach instead.')))
            for width in (390,1280):
                page.set_viewport_size(dict(width=width,height=900))
                page.reload()
                expect(card).to_contain_text('No next week was created.')
                expect(card.get_by_role('link',name='Start a discussion in AI Coach')).to_have_attribute('href','/#ai')
                expect(card.get_by_role('button',name='Run it back',exact=True)).to_have_count(0)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                card.screenshot(path=str(OUT/f'error-{width}.png'))
            assert not mutations,mutations
            assert not errors,errors
            # Dashboard status lookup is read-only and differentiates a finished reply from a due review.
            page.goto(URL+'/')
            notice=page.locator('#weekly-review-notice')
            expect(notice).to_contain_text('Weekly review ready')
            expect(notice.get_by_role('link',name='Read weekly review')).to_have_attribute('href','/?coaching_conversation=review#ai')
            for width in (390,1280):
                page.set_viewport_size(dict(width=width,height=900))
                notice.screenshot(path=str(OUT/f'dashboard-review-{width}.png'))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.route('**/api/ai/conversations/review',lambda route:route.fulfill(status=404,json=dict(detail='Not found')))
            page.evaluate('loadWeeklyReviewNotice()')
            expect(notice).to_contain_text('Week complete — ready to review')
            expect(notice.get_by_role('link',name='Review this week')).to_have_attribute('href','/?coaching_week=finished&coaching_kind=call#ai')
            page.route('**/api/ai/conversations/review',lambda route:route.fulfill(json=dict(id='review',turns=[dict(status='interrupted',response='Partial')])) )
            page.evaluate('loadWeeklyReviewNotice()')
            expect(notice).to_contain_text('Weekly review needs attention')
            page.route('**/training/api/weekly-call',lambda route:route.fulfill(content_type='application/json',body='null'))
            page.evaluate('loadWeeklyReviewNotice()')
            expect(notice).to_be_hidden()
            assert not mutations,mutations
            browser.close()
        print('Review card: phone/desktop, concise fixture, shortcut absent, read-only navigation and context-error recovery passed. Providers mocked; live model concision not tested.')
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
