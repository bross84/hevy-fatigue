"""Phone-width acceptance against tools.preview_app only; never a live account."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL=os.environ.get('TRAINING_PREVIEW_URL','http://127.0.0.1:18127')
out=Path('artifacts/phase1');out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    # Third-party host chart CDN is unnecessary for this isolated acceptance.
    context.route('https://**/*',lambda route: route.abort())
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(URL+'/')
    # A fresh preview auto-opens the host check-in. Repeated browser checks may
    # reuse that same disposable server after today's check-in is already saved.
    current=page.request.get(URL+'/api/readiness/today').json()
    if not current:
        page.wait_for_selector('#ci-submit',state='visible')
        with page.expect_response(lambda r:r.url.endswith('/api/readiness') and r.request.method=='POST') as checkin:
            page.locator('#ci-submit').click()
        assert checkin.value.ok,checkin.value.text()
    page.goto(URL+'/training/microcycles')
    page.get_by_role('link',name='Start next workout',exact=True).click()
    expect(page.locator('#title')).to_have_value('Mock Workout')
    page.evaluate('navigator.serviceWorker.ready')
    scopes=page.evaluate('(async()=> (await navigator.serviceWorker.getRegistrations()).map(r=>r.scope))()')
    assert scopes==[URL+'/training/'],scopes
    weight=page.get_by_role('textbox',name='Weight in kilograms').first
    weight.tap();expect(page.locator('#numberpad')).to_be_visible()
    for digit in '100': page.locator('[data-pad-key="'+digit+'"]').tap()
    page.locator('[data-pad-key="next"]').tap()
    page.locator('[data-pad-key="1"]').tap()
    page.locator('[data-pad-key="done"]').tap()
    page.get_by_role('button',name='RPE 8. Change RPE',exact=True).tap()
    page.get_by_role('button',name='8',exact=True).tap()
    page.get_by_role('button',name='Mark set done',exact=True).first.tap()
    page.get_by_role('button',name='Mark set done',exact=True).last.tap()
    draft=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")
    assert all(s['done'] for s in draft['exercises'][0]['sets'])
    assert draft['exercises'][0]['sets'][0]['ts']
    assert draft['client_workout_id']
    kg=[s['kg'] for s in draft['exercises'][0]['sets']]
    page.locator('#unitLb').tap()
    assert page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).exercises[0].sets.map(s=>s.kg)")==kg
    timer=page.evaluate("localStorage.getItem('training.restEnd')")
    assert timer and float(timer)>0
    page.screenshot(path=str(out/'logger-phone.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
    page.goto(URL+'/training/progress')
    expect(page.locator('h1')).to_contain_text('Progress')
    page.goto(URL+'/training/log')
    expect(page.locator('#title')).to_have_value('Mock Workout')
    assert page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).client_workout_id")==draft['client_workout_id']
    assert page.evaluate("localStorage.getItem('training.restEnd')")==timer
    page.reload();expect(page.locator('#title')).to_have_value('Mock Workout')
    page.locator('#finish').tap()
    with page.expect_response(lambda r:'/training/hevy/workouts' in r.url and r.request.method=='POST') as saved:
        page.locator('#confirmSave').tap()
    saved_result=saved.value.json()
    assert saved_result['state']=='complete',saved_result
    expect(page.locator('#done')).to_be_visible()
    assert page.evaluate("localStorage.getItem('training.logDraft')")==None
    plans=page.request.get(URL+'/training/api/mesocycles').json()
    assert len(plans[0]['completed'])==1
    page.get_by_role('button',name='Log another workout',exact=True).click()
    expect(page.locator('#plannedStart')).to_contain_text('Next Workout')
    page.goto(URL+'/training/rpe-charts');expect(page.locator('h1')).to_contain_text('RPE')
    page.screenshot(path=str(out/'rpe-phone.png'),full_page=True)
    page.get_by_role('link',name='Settings',exact=True).click()
    expect(page.locator('#tab-settings')).to_have_class('tab-content active')
    assert page.url.endswith('/#settings')
    # Unknown hashes cannot hide or break the host dashboard.
    page.goto(URL+'/#not-a-tab');expect(page.locator('#tab-settings')).to_have_class('tab-content active')
    page.reload();expect(page.locator('#tab-dashboard')).to_have_class('tab-content active')
    page.screenshot(path=str(out/'today-phone.png'),full_page=True)
    assert page.evaluate('navigator.serviceWorker.controller===null'), 'Training worker controls root dashboard'
    # Missing credentials direct users to the host settings, not a second key form.
    context.route('**/training/hevy/workouts?*',lambda route:route.fulfill(status=400,content_type='application/json',body=json.dumps({'detail':'Configure the shared credential in Settings.'})))
    page.goto(URL+'/training/recent')
    expect(page.locator('#keyform')).to_be_visible()
    expect(page.locator('#keyform a')).to_have_attribute('href','/#settings')
    expect(page.locator('#keyform')).to_contain_text('Hevy-Fatigue Settings')
    assert page.locator('#keyinput').is_disabled() and not page.locator('#keyinput').is_visible()
    assert page.locator('#keysave').is_disabled() and not page.locator('#keysave').is_visible()
    # The host uses remote CDN scripts, intentionally blocked above. Report those
    # separately from imported logger errors.
    unexpected=[e for e in errors if not any(x in e for x in ('Chart is not defined','marked is not defined'))]
    assert not unexpected,unexpected
    print(json.dumps({'viewport':'390x844 touch','mocked_save':saved_result['state'],
                      'completion_count':len(plans[0]['completed']),'browser_errors':unexpected,
                      'worker_scope':'/training/','missing_credentials':'host Settings',
                      'screenshots':str(out),'physical_device':'not performed'}))
    browser.close()
