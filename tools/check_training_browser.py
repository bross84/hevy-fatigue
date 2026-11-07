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
    expect(page.locator('#motivation-level')).to_have_value('')
    page.get_by_role('button',name='Mark set done',exact=True).first.click()
    expect(page.locator('#msg')).to_contain_text('Confirm your motivation')
    assert not page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).exercises[0].sets[0].done")
    before_motivation=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).exercises")
    page.locator('#motivation-level').select_option('3')
    page.locator('#motivation-note').fill('Same movements since August')
    with page.expect_response(lambda r:r.url.endswith('/session-checkins') and r.request.method=='POST') as confirmed:
        page.locator('#confirmMotivation').click()
    assert confirmed.value.ok,confirmed.value.text()
    assert page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).exercises")==before_motivation
    page.reload()
    expect(page.locator('#motivation-level')).to_have_value('3')
    assert page.locator('#motivation-reason').count()==0
    expect(page.locator('#motivation-note')).to_have_value('Same movements since August')
    motivation=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).motivation")
    assert motivation['timing']=='before_working_sets'
    original_prescription=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).prescription")
    assert original_prescription['source']=='plan'
    assert original_prescription['exercises'][0]['sets'][1]['reps']==5
    advice_box=page.locator('[data-session-advice]').first
    expect(advice_box.locator('summary').first).to_contain_text('Provisional session advice')
    if advice_box.locator('details').first.get_attribute('open') is None:
        advice_box.locator('summary').first.click()
    original_sets=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).exercises[0].sets.map(s=>[s.kg,s.reps,s.rpe])")
    with page.expect_response(lambda r:r.url.endswith('/decisions') and r.request.method=='POST') as deferred:
        advice_box.get_by_role('button',name='Not now',exact=True).click()
    assert deferred.value.ok,deferred.value.text()
    expect(advice_box.locator('summary').first).to_contain_text('not now')
    advice_box.locator('summary').first.click()
    advice_box.get_by_role('button',name='Modify',exact=True).click()
    advice_box.get_by_role('spinbutton',name='Intended working sets for Squat (Barbell)',exact=True).fill('1')
    with page.expect_response(lambda r:r.url.endswith('/decisions') and r.request.method=='POST') as modified:
        advice_box.get_by_role('button',name='Record modification',exact=True).click()
    assert modified.value.ok,modified.value.text()
    modification=modified.value.json()['decision']
    assert modification['action']=='modify' and modification['dose']['working_sets']==1
    assert page.evaluate("JSON.parse(localStorage.getItem('training.logDraft')).exercises[0].sets.map(s=>[s.kg,s.reps,s.rpe])")==original_sets
    if advice_box.locator('details').first.get_attribute('open') is None:
        advice_box.locator('summary').first.click()
    page.screenshot(path=str(out/'session-advice-phone.png'),full_page=True)
    page.evaluate('navigator.serviceWorker.ready')
    scopes=page.evaluate('(async()=> (await navigator.serviceWorker.getRegistrations()).map(r=>r.scope))()')
    assert scopes==[URL+'/training/'],scopes
    weight=page.get_by_role('textbox',name='Weight in kilograms').first
    weight.tap();expect(page.locator('#numberpad')).to_be_visible()
    for digit in '100': page.locator('[data-pad-key="'+digit+'"]').tap()
    page.locator('[data-pad-key="next"]').tap()
    page.locator('[data-pad-key="1"]').tap()
    page.locator('[data-pad-key="done"]').tap()
    page.get_by_role('button',name='RPErx 8. Change RPErx',exact=True).tap()
    page.get_by_role('button',name='8',exact=True).tap()
    page.get_by_role('button',name='Mark set done',exact=True).first.tap()
    page.get_by_role('button',name='RPEact 8. Change RPEact',exact=True).tap()
    page.get_by_role('button',name='7',exact=True).tap()
    expect(page.get_by_role('button',name='RPErx 8. Change RPErx',exact=True)).to_be_visible()
    page.get_by_role('button',name='Mark set done',exact=True).last.tap()
    draft=page.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")
    assert all(s['done'] for s in draft['exercises'][0]['sets'])
    assert draft['exercises'][0]['sets'][0]['ts']
    assert draft['exercises'][0]['sets'][0]['rpe']=='8'
    assert draft['exercises'][0]['sets'][0]['arpe']=='7'
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
    # Desktop direct typing keeps Rx separate and only changes later weights.
    desktop=browser.new_context(viewport={'width':1280,'height':900})
    desktop.route('https://**/*',lambda route:route.abort())
    desk=desktop.new_page();desk.on('pageerror',lambda error:errors.append(str(error)))
    desk.goto(URL+'/training/log')
    desk.evaluate('(d)=>localStorage.setItem("training.logDraft",JSON.stringify(d))',draft)
    desk.reload()
    desk.get_by_role('textbox',name='RPEact',exact=True).first.fill('6.5')
    expect(desk.get_by_role('textbox',name='RPErx',exact=True).first).to_have_value('8')
    updated=desk.evaluate("JSON.parse(localStorage.getItem('training.logDraft'))")
    assert updated['exercises'][0]['sets'][0]['arpe']=='6.5'
    assert updated['exercises'][0]['sets'][0]['kg']==draft['exercises'][0]['sets'][0]['kg']
    assert desk.evaluate('document.documentElement.scrollWidth <= innerWidth')
    desk.screenshot(path=str(out/'logger-desktop.png'),full_page=True)
    with desk.expect_response(lambda r:r.url.endswith('/exercise-refs/sq') and r.request.method=='PUT') as preference:
        desk.get_by_role('button',name='Use e1RM for weights',exact=True).click()
    assert preference.value.ok,preference.value.text()
    expect(desk.get_by_role('button',name='Use e1RM for weights',exact=True)).to_have_attribute('aria-pressed','false')
    expect(desk.get_by_role('button',name='Use TM for weights',exact=True)).to_have_attribute('aria-pressed','false')
    expect(desk.get_by_role('button',name='LSe1RM',exact=True)).to_be_disabled()
    desk.get_by_role('button',name='+ Add set',exact=True).click()
    manual_before=desk.get_by_role('textbox',name='Weight in kilograms',exact=True).last.input_value()
    desk.get_by_role('textbox',name='RPErx',exact=True).last.fill('7')
    expect(desk.get_by_role('textbox',name='Weight in kilograms',exact=True).last).to_have_value(manual_before)
    desk.reload()
    expect(desk.get_by_role('button',name='Use e1RM for weights',exact=True)).to_have_attribute('aria-pressed','false')
    expect(desk.get_by_role('button',name='Use TM for weights',exact=True)).to_have_attribute('aria-pressed','false')
    expect(desk.get_by_role('textbox',name='Weight in kilograms',exact=True).last).to_have_value(manual_before)
    stored=next(r for r in desk.request.get(URL+'/training/exercise-refs').json() if r['exercise_template_id']=='sq')
    assert stored['auto_weights'] is False and stored['ls'] is True,stored
    desk.screenshot(path=str(out/'logger-no-source-desktop.png'),full_page=True)
    fresh=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    fresh.route('https://**/*',lambda route:route.abort())
    fresh_page=fresh.new_page();fresh_page.goto(URL+'/training/log')
    fresh_page.get_by_role('button',name='Load selected workout',exact=True).click()
    expect(fresh_page.get_by_role('button',name='Use e1RM for weights',exact=True)).to_have_attribute('aria-pressed','false')
    expect(fresh_page.get_by_role('button',name='Use TM for weights',exact=True)).to_have_attribute('aria-pressed','false')
    assert fresh_page.get_by_role('textbox',name='Weight in kilograms',exact=True).first.input_value()=='100'
    fresh.close()
    assert desk.request.put(URL+'/training/exercise-refs/sq',data={**stored,'auto_weights':True}).ok
    desktop.close()
    page.reload();expect(page.locator('#title')).to_have_value('Mock Workout')
    expect(page.get_by_role('button',name='RPErx 8. Change RPErx',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='RPEact 7. Change RPEact',exact=True)).to_be_visible()
    page.locator('#finish').tap()
    with page.expect_response(lambda r:'/training/hevy/workouts' in r.url and r.request.method=='POST') as saved:
        page.locator('#confirmSave').tap()
    saved_result=saved.value.json()
    posted=saved.value.request.post_data_json['exercises'][0]['sets'][0]
    assert posted['target_rpe']==8 and posted['rpe']==7,posted
    assert saved_result['state']=='complete',saved_result
    expect(page.locator('#done')).to_be_visible()
    expect(page.locator('#sessionReview')).to_contain_text('Session review')
    expect(page.locator('#sessionReview')).to_contain_text('2 originally planned')
    review=page.request.get(URL+'/training/session-reviews/'+saved_result['id']).json()
    assert review['available'],review
    assert review['prescription']==original_prescription
    assert review['motivation']['level']==3 and review['motivation']['reason'] is None
    assert review['motivation']['timing']=='before_working_sets'
    expect(page.locator('#sessionReview')).to_contain_text('Reluctant')
    expect(page.locator('#sessionReview')).to_contain_text('Same movements since August')
    # Creating evidence alone does not call a provider and must expose the saved context.
    from uuid import uuid4
    training_review=page.request.post(URL+'/api/ai/conversations',data={'id':str(uuid4())})
    assert training_review.ok,training_review.text()
    motivation_rows=training_review.json()['evidence']['motivation_checkins']
    assert len(motivation_rows)==1 and motivation_rows[0]['level']==3 and motivation_rows[0]['note']=='Same movements since August'
    follow=review['advisory_outcomes'][0]
    assert follow['decision']['id']==modification['id']
    assert follow['intended']['working_sets']==1 and follow['actual']['working_sets']==2,follow
    assert follow['matched_intended_sets'] is False
    expect(page.locator('#sessionReview')).to_contain_text('Saved set count differs from recorded intent')
    evidence=review['review']['movements'][0]['sets']
    assert evidence[0]['rpe_source']=='entered' and evidence[1]['rpe_source']=='copied_target',evidence
    page.locator('#sessionReview summary').first.click()
    page.screenshot(path=str(out/'session-review-phone.png'),full_page=True)
    assert page.evaluate("localStorage.getItem('training.logDraft')")==None
    history_page=context.new_page()
    history_page.goto(URL+'/training/recent')
    expect(history_page.locator('#list')).to_contain_text('RPErx 8 · RPEact 7')
    history_page.get_by_role('button',name='Session review',exact=True).first.click()
    expect(history_page.locator('#list')).to_contain_text('2 originally planned')
    history=page.request.get(URL+'/training/hevy/workouts').json()['workouts'][0]['exercises'][0]['sets'][0]
    assert history['target_rpe']==8 and history['rpe']==7,history
    history_page.close()
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
